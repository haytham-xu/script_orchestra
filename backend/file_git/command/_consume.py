"""
Shared queue-consumption loop used by push / pull / queue commands.

Given a RepoContext with a locked ``queue.json``, run each pending
QueueItem through ActionExecutor, logging outcomes.

Returns aggregate counters so the caller can report to the user.

Performance note: the queue is owned **in memory** for the whole drain.
``queue.json`` (which can be 100MB+ for very large repos) is persisted only
periodically (every ``PERSIST_EVERY_N`` items or ``PERSIST_EVERY_S`` seconds)
plus once at the end and on pause/rate-limit breaks — never once per item.
The pause signal is read from the tiny ``queue_control.json`` sidecar so a
pause request never forces a re-read of the big file. A single background
thread emits throttled WebSocket progress built from in-memory primitive
counters (no ``queue.json`` reads, no ``state.queue`` iteration).
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

from ..cloud import RateLimitError
from ..service import (
    ActionExecutor,
    LoggerService,
    QueueService,
    Status,
)
from ..service.queue_service import QueueState
from ..service import upload_progress
from .context import RepoContext


# Throttling knobs for queue.json persistence and WS emits.
PERSIST_EVERY_N = 200
PERSIST_EVERY_S = 3.0
EMIT_EVERY_S = 0.6


# In-process guard so two drains can never run on the same repo at once.
# The on-disk lock (queue.json) marks "an action is in progress", but a
# Resume on a locked repo would otherwise start a SECOND consume_queue while
# a Push is still draining — two writers racing on queue.json / the indexes.
# This serialises drains within the single backend process.
_DRAIN_LOCKS: dict = {}
_DRAIN_GUARD = threading.Lock()


def _acquire_drain_lock(repo_root: str):
    with _DRAIN_GUARD:
        lk = _DRAIN_LOCKS.get(repo_root)
        if lk is None:
            lk = threading.Lock()
            _DRAIN_LOCKS[repo_root] = lk
    return lk if lk.acquire(blocking=False) else None


def _release_drain_lock(lk) -> None:
    try:
        lk.release()
    except RuntimeError:
        pass


@dataclass
class ConsumeCounters:
    uploaded: int = 0
    downloaded: int = 0
    local_deleted: int = 0
    remote_deleted: int = 0
    errors: int = 0


ProgressFn = Callable[[str, int, int, str], None]
"""Optional progress callback: (phase, current, total, detail)."""


class _Live:
    """Primitive, O(1) progress snapshot shared with the emitter thread.

    Only plain ints / a dict reference are mutated by the drain loop and read
    by the emitter. CPython's GIL makes those reads/writes atomic, and the
    emitter never iterates ``state.queue`` (which the loop mutates), so no lock
    is needed."""

    def __init__(self, repo_root: str, lock: bool, action_type, action_folder,
                 total: int, done: int) -> None:
        self.repo_root = repo_root
        self.lock = lock
        self.action_type = action_type
        self.action_folder = action_folder
        self.total = total
        self.done = done
        self.error = 0
        self.in_progress = 0
        self.current: Optional[dict] = None
        self.error_items: List[dict] = []


def _live_payload(live: _Live) -> dict:
    """Build the exact shape ``QueueService.build_payload`` returns, from the
    in-memory primitives (cheap + thread-safe)."""
    prog = upload_progress.get(live.repo_root)
    done = live.done
    error = live.error
    in_progress = live.in_progress
    todo = live.total - done - error - in_progress
    if todo < 0:
        todo = 0
    return {
        "lock": live.lock,
        "action_type": live.action_type,
        "action_folder": live.action_folder,
        "paused": False,
        "rate_limited_until": None,
        "total": live.total,
        "done": done,
        "error": error,
        "todo": todo,
        "in_progress": in_progress,
        "current": live.current,
        "bytes_done": prog["bytes_done"] if prog else 0,
        "bytes_total": prog["bytes_total"] if prog else 0,
        "upload_phase": prog["phase"] if prog else "uploading",
        "error_items": live.error_items[-5:],
    }


class _LiveEmitter:
    """Background thread that emits throttled queue progress for the whole
    drain, built from the in-memory ``_Live`` snapshot."""

    def __init__(self, repo_id: str, live: _Live, interval: float = 0.5) -> None:
        self._repo_id = repo_id
        self._live = live
        self._interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            self._thread.join(timeout=1.0)
        except Exception:
            pass

    def emit_now(self) -> None:
        self._emit()

    def _emit(self) -> None:
        try:
            from ..websocket_service import emit_queue_update
            emit_queue_update(self._repo_id, _live_payload(self._live))
        except Exception:
            pass

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            self._emit()


def consume_queue(
    ctx: RepoContext,
    *,
    progress: Optional[ProgressFn] = None,
) -> ConsumeCounters:
    """Drain the queue currently on disk. Failures are logged, not raised."""
    drain_lock = _acquire_drain_lock(ctx.repo_root)
    if drain_lock is None:
        raise RuntimeError(
            "A sync is already running for this repository — wait for it to "
            "finish before pushing/pulling/resuming again."
        )
    try:
        state: QueueState = QueueService.load(ctx.repo_root)
        if not state.lock or state.action_folder is None:
            raise RuntimeError("consume_queue called without an active lock")

        executor = ActionExecutor(
            repo_root=ctx.repo_root,
            mode=ctx.mode,
            storage=ctx.storage,
            remote_root=ctx.remote_root,
            key=ctx.key,
        )

        counters = ConsumeCounters()
        action_folder = state.action_folder
        pending = QueueService.pending_items(state)
        total = len(pending) + state.done_count

        live = _Live(
            repo_root=ctx.repo_root,
            lock=state.lock,
            action_type=state.action_type,
            action_folder=action_folder,
            total=total,
            done=state.done_count,
        )
        emitter = _LiveEmitter(ctx.repo_id, live)
        batch = LoggerService.open_batch(ctx.repo_root, action_folder)

        last_persist = time.monotonic()
        since_persist = 0

        def _persist() -> None:
            nonlocal last_persist, since_persist
            QueueService.save(ctx.repo_root, state)
            last_persist = time.monotonic()
            since_persist = 0

        emitter.start()
        try:
            for idx, (item_key, item) in enumerate(pending, 1):
                # Pause / stop check via the tiny control sidecar (no big-file read).
                ctrl = QueueService.read_control(ctx.repo_root)
                if ctrl["paused"] or ctrl.get("stopped"):
                    break

                middle_path = item.get("middle_path", "?")
                action = item.get("action", "?")
                if progress:
                    progress("queue", idx, total, f"{action} {middle_path}")

                # In-memory breadcrumb (persisted on the next throttled save).
                QueueService.mark_in_progress(ctx.repo_root, state, item_key, persist=False)
                live.current = {
                    "path": middle_path,
                    "action": action,
                    "size": item.get("size", 0),
                }
                live.in_progress = 1

                # Per-file byte progress (in-memory; the emitter reads it).
                bytes_total = item.get("size", 0) if action == "UPLOAD" else 0
                upload_progress.set_current(
                    ctx.repo_root, item_key, middle_path, action, bytes_total,
                )
                try:
                    outcome = executor.execute(item)
                except RateLimitError:
                    # Reset current item to TODO so it retries on resume, persist now.
                    if item_key in state.queue:
                        state.queue[item_key]["status"] = Status.TODO.value
                    live.in_progress = 0
                    _persist()
                    retry_at = time.time() + 3600
                    QueueService.set_rate_limited(ctx.repo_root, retry_at)
                    batch.error(
                        action, middle_path,
                        "Baidu rate limit hit — paused for 1 hour, will auto-resume",
                    )
                    _schedule_auto_resume(ctx.repo_id, ctx.repo_root, 3600)
                    break
                finally:
                    upload_progress.clear(ctx.repo_root)
                    live.in_progress = 0

                if outcome.ok:
                    QueueService.mark_done(ctx.repo_root, state, item_key, persist=False)
                    live.done += 1
                    batch.success(action, middle_path, outcome.detail)
                    batch.file_state(
                        middle_path, item.get("mode", "synced"), item.get("status", ""),
                        item.get("in_local", True), item.get("in_remote", False),
                        action, "ok", outcome.detail or "",
                    )
                    if action == "UPLOAD":
                        counters.uploaded += 1
                    elif action == "DOWNLOAD":
                        counters.downloaded += 1
                    elif action == "LOCAL_DELETE":
                        counters.local_deleted += 1
                    elif action in ("REMOTE_DELETE", "REMOTE_TRASH"):
                        counters.remote_deleted += 1
                else:
                    QueueService.mark_error(
                        ctx.repo_root, state, item_key, outcome.detail, persist=False,
                    )
                    live.error += 1
                    live.error_items.append({
                        "path": middle_path, "action": action,
                        "error": outcome.detail or "",
                    })
                    batch.error(action, middle_path, outcome.detail)
                    batch.file_state(
                        middle_path, item.get("mode", "synced"), item.get("status", ""),
                        item.get("in_local", True), item.get("in_remote", False),
                        action, "error", outcome.detail or "",
                    )
                    counters.errors += 1

                since_persist += 1
                if since_persist >= PERSIST_EVERY_N or (time.monotonic() - last_persist) >= PERSIST_EVERY_S:
                    _persist()
        finally:
            live.current = None
            live.in_progress = 0
            # Final authoritative persist of whatever we processed.
            QueueService.save(ctx.repo_root, state)
            batch.close()
            emitter.stop()
            emitter.emit_now()

        return counters
    finally:
        _release_drain_lock(drain_lock)


def _schedule_auto_resume(repo_id: str, repo_root: str, delay: float) -> None:
    """Fire command_queue after ``delay`` seconds if still rate-limited."""
    def _do_resume():
        from .queue import command_queue
        state = QueueService.load(repo_root)
        if not state.paused:
            return  # user already unpaused manually
        QueueService.unpause(repo_root)
        try:
            command_queue(repo_id)
        except Exception:
            pass

    t = threading.Timer(delay, _do_resume)
    t.daemon = True
    t.start()
