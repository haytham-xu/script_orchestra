"""
QueueService — persistent queue with lock and action-folder management
(REQUIREMENTS §3.6, §3.7, §3.8).

The queue lives at ``.fgit/queue.json`` and drives resumable sync:

    * Acquire lock at command start (Push/Pull/Manual Upload/Pre Manual DL)
    * Enqueue items with ``status=TODO``
    * ActionExecutor consumes each item, marks IN_PROGRESS → DONE / ERROR
    * When empty, release lock and archive the final queue snapshot into
      ``.fgit/action/<timestamp>_<cmd>/queue.json``

Only one action holds the lock at a time. See REQUIREMENTS §3.8 for
which commands are permitted while locked.
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, TypedDict

from ._fsutil import atomic_write_json


QUEUE_FILENAME = "queue.json"
CONTROL_FILENAME = "queue_control.json"
ACTION_DIRNAME = "action"


class ActionType(str, Enum):
    UPLOAD = "UPLOAD"
    DOWNLOAD = "DOWNLOAD"
    LOCAL_DELETE = "LOCAL_DELETE"
    REMOTE_DELETE = "REMOTE_DELETE"
    REMOTE_TRASH = "REMOTE_TRASH"


class Status(str, Enum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    ERROR = "ERROR"


class QueueItem(TypedDict, total=False):
    middle_path: str
    encoded_path: str
    action: str          # ActionType value
    status: str          # Status value
    size: int
    retry_count: int
    last_error: Optional[str]


@dataclass
class QueueState:
    lock: bool
    action_folder: Optional[str]
    action_type: Optional[str]
    queue: Dict[str, QueueItem]
    paused: bool = False
    rate_limited_until: Optional[float] = None
    done_count: int = 0

    def to_dict(self) -> dict:
        return {
            "lock": self.lock,
            "action_folder": self.action_folder,
            "action_type": self.action_type,
            "queue": self.queue,
            "paused": self.paused,
            "rate_limited_until": self.rate_limited_until,
            "done_count": self.done_count,
        }

    @classmethod
    def empty(cls) -> "QueueState":
        return cls(lock=False, action_folder=None, action_type=None, queue={})

    @classmethod
    def from_dict(cls, data: dict) -> "QueueState":
        return cls(
            lock=data.get("lock", False),
            action_folder=data.get("action_folder"),
            action_type=data.get("action_type"),
            queue=data.get("queue") or {},
            paused=data.get("paused", False),
            rate_limited_until=data.get("rate_limited_until"),
            done_count=data.get("done_count", 0),
        )


class LockError(Exception):
    """Raised when a command tries to acquire an already-held lock."""


class QueueService:
    """Stateless helpers over ``.fgit/queue.json``."""

    # ---- path helpers -------------------------------------------------

    @staticmethod
    def _queue_path(repo_root: str) -> str:
        return os.path.join(repo_root, ".fgit", QUEUE_FILENAME)

    @staticmethod
    def _control_path(repo_root: str) -> str:
        return os.path.join(repo_root, ".fgit", CONTROL_FILENAME)

    @staticmethod
    def _action_root(repo_root: str) -> str:
        return os.path.join(repo_root, ".fgit", ACTION_DIRNAME)

    # ---- control file (tiny: paused / rate_limited_until) ------------
    #
    # The drain loop (consume_queue) owns queue.json in memory for the
    # duration of an action and only persists it periodically. A separate
    # request may want to pause it mid-drain. Routing the pause signal
    # through the big queue.json would force the loop to re-read a
    # 100MB+ file per item just to check one bool. Instead pause state
    # lives in this tiny sidecar, which both sides read/write cheaply.

    @staticmethod
    def read_control(repo_root: str) -> dict:
        """Read {paused, rate_limited_until, stopped}; defaults when the file is absent."""
        path = QueueService._control_path(repo_root)
        if not os.path.exists(path):
            return {"paused": False, "rate_limited_until": None, "stopped": False}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                "paused": bool(data.get("paused", False)),
                "rate_limited_until": data.get("rate_limited_until"),
                "stopped": bool(data.get("stopped", False)),
            }
        except Exception:
            return {"paused": False, "rate_limited_until": None, "stopped": False}

    @staticmethod
    def write_control(repo_root: str, paused: bool,
                      rate_limited_until: Optional[float]) -> None:
        atomic_write_json(
            QueueService._control_path(repo_root),
            {"paused": paused, "rate_limited_until": rate_limited_until},
        )

    @staticmethod
    def stop(repo_root: str) -> None:
        """Signal the drain loop to stop cleanly after the current item.

        The loop breaks on the next item boundary; push/pull handlers then
        run their normal index reconciliation and release the lock.
        """
        ctrl = QueueService.read_control(repo_root)
        atomic_write_json(
            QueueService._control_path(repo_root),
            {
                "paused": ctrl["paused"],
                "rate_limited_until": ctrl["rate_limited_until"],
                "stopped": True,
            },
        )

    @staticmethod
    def clear_control(repo_root: str) -> None:
        """Reset pause/rate-limit state (new action or release)."""
        path = QueueService._control_path(repo_root)
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            # best-effort; a stale control file is harmless after acquire resets it
            QueueService.write_control(repo_root, False, None)

    # ---- read/write ---------------------------------------------------

    @staticmethod
    def load(repo_root: str) -> QueueState:
        path = QueueService._queue_path(repo_root)
        if not os.path.exists(path):
            state = QueueState.empty()
        else:
            with open(path, "r", encoding="utf-8") as f:
                state = QueueState.from_dict(json.load(f))
        # Pause / rate-limit live in the tiny control sidecar and win over
        # whatever is (or isn't) baked into queue.json. If the sidecar does
        # not exist yet (e.g. a queue written by an older build, mid-flight
        # across this upgrade), keep the values already parsed from queue.json
        # so an in-progress pause is not silently lost.
        if os.path.exists(QueueService._control_path(repo_root)):
            ctrl = QueueService.read_control(repo_root)
            state.paused = ctrl["paused"]
            state.rate_limited_until = ctrl["rate_limited_until"]
        return state

    @staticmethod
    def save(repo_root: str, state: QueueState) -> None:
        atomic_write_json(QueueService._queue_path(repo_root), state.to_dict(), indent=2)

    # ---- lock / action lifecycle -------------------------------------

    @staticmethod
    def acquire(
        repo_root: str,
        action_type: str,
        *,
        allow_when_locked_by_same_action: bool = False,
    ) -> QueueState:
        """Grab the lock for a new action.

        Returns the fresh QueueState (empty queue) with lock=true and
        a newly-created action_folder. If already locked, raises
        ``LockError`` unless the caller opts into resuming.
        """
        state = QueueService.load(repo_root)
        if state.lock:
            if not allow_when_locked_by_same_action:
                raise LockError(
                    f"Repository is locked by a prior '{state.action_type}' operation. "
                    f"Use resume/queue to continue or clear the lock manually."
                )
            # Resume path — caller must handle continuing an existing queue
            return state

        action_folder = QueueService._make_action_folder(repo_root, action_type)
        state = QueueState(
            lock=True,
            action_folder=action_folder,
            action_type=action_type,
            queue={},
        )
        QueueService.clear_control(repo_root)
        QueueService.save(repo_root, state)
        return state

    @staticmethod
    def release(repo_root: str, *, archive: bool = True) -> None:
        """Archive the current queue to action_folder and unlock.

        ``archive=True`` copies the current queue.json into the action
        folder before clearing. Set to False if the archive already
        happened (e.g. on error-only exit).
        """
        state = QueueService.load(repo_root)
        if archive and state.action_folder:
            dest = os.path.join(
                QueueService._action_root(repo_root),
                state.action_folder,
                QUEUE_FILENAME,
            )
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8") as f:
                json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)

        QueueService.clear_control(repo_root)
        QueueService.save(repo_root, QueueState.empty())

    @staticmethod
    def is_locked(repo_root: str) -> bool:
        return QueueService.load(repo_root).lock

    @staticmethod
    def pause(repo_root: str) -> None:
        ctrl = QueueService.read_control(repo_root)
        QueueService.write_control(repo_root, True, ctrl["rate_limited_until"])

    @staticmethod
    def unpause(repo_root: str) -> None:
        QueueService.write_control(repo_root, False, None)

    @staticmethod
    def set_rate_limited(repo_root: str, until: float) -> None:
        QueueService.write_control(repo_root, True, until)

    @staticmethod
    def _make_action_folder(repo_root: str, action_type: str) -> str:
        """Create ``.fgit/action/<yyyymmdd_hhmm>_<action_type>/`` and return its
        basename (relative to ``.fgit/action/``)."""
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        # Ensure uniqueness even within the same minute
        suffix = 0
        while True:
            candidate = f"{stamp}_{action_type}" + (f"_{suffix}" if suffix else "")
            full = os.path.join(QueueService._action_root(repo_root), candidate)
            if not os.path.exists(full):
                os.makedirs(full, exist_ok=True)
                os.makedirs(os.path.join(full, "log"), exist_ok=True)
                return candidate
            suffix += 1

    @staticmethod
    def action_folder_path(repo_root: str, action_folder: str) -> str:
        return os.path.join(QueueService._action_root(repo_root), action_folder)

    # ---- queue item manipulation -------------------------------------

    @staticmethod
    def enqueue(
        state: QueueState,
        key: str,
        item: QueueItem,
    ) -> None:
        """Add ``item`` to ``state.queue`` under ``key``. Mutates in place."""
        item.setdefault("status", Status.TODO.value)
        item.setdefault("retry_count", 0)
        item.setdefault("last_error", None)
        state.queue[key] = item

    @staticmethod
    def pending_items(state: QueueState) -> List[tuple]:
        """Return [(key, item), …] for items not yet DONE.

        Includes TODO, IN_PROGRESS (crash-recovery) and ERROR (retryable).
        DONE items are already removed by ``mark_done``.
        """
        return [
            (k, v) for k, v in state.queue.items()
            if v.get("status") != Status.DONE.value
        ]

    @staticmethod
    def mark_in_progress(
        repo_root: str,
        state: QueueState,
        key: str,
        *,
        persist: bool = True,
    ) -> None:
        state.queue[key]["status"] = Status.IN_PROGRESS.value
        if persist:
            QueueService.save(repo_root, state)

    @staticmethod
    def mark_done(
        repo_root: str,
        state: QueueState,
        key: str,
        *,
        persist: bool = True,
    ) -> None:
        """Remove the item from the queue, increment done_count, and persist.

        With ``persist=False`` the mutation stays in-memory; the caller is
        responsible for a later ``QueueService.save`` (used by the drain loop
        to avoid rewriting a large queue.json on every item)."""
        state.queue.pop(key, None)
        state.done_count += 1
        if persist:
            QueueService.save(repo_root, state)

    @staticmethod
    def mark_error(
        repo_root: str,
        state: QueueState,
        key: str,
        error: str,
        *,
        persist: bool = True,
    ) -> None:
        item = state.queue[key]
        item["status"] = Status.ERROR.value
        item["retry_count"] = item.get("retry_count", 0) + 1
        item["last_error"] = error
        if persist:
            QueueService.save(repo_root, state)

    # ---- action-folder side files ------------------------------------

    @staticmethod
    def snapshot_index_into_action(
        repo_root: str,
        action_folder: str,
        filename: str,
        data: dict,
    ) -> None:
        """Write ``local_index.json`` / ``cloud_index.json`` snapshots into
        the action folder for audit."""
        dest_dir = QueueService.action_folder_path(repo_root, action_folder)
        os.makedirs(dest_dir, exist_ok=True)
        atomic_write_json(os.path.join(dest_dir, filename), data, indent=2)

    @staticmethod
    def build_payload(repo_root: str, qstate: Optional["QueueState"] = None) -> dict:
        """Build the queue status dict used by both the REST endpoint and WS emitter."""
        from . import upload_progress  # local import to avoid top-level cycle
        if qstate is None:
            qstate = QueueService.load(repo_root)
        items = list(qstate.queue.values())
        done = qstate.done_count
        total = len(items) + done
        error_count = sum(1 for i in items if i.get("status") == Status.ERROR.value)
        todo = sum(1 for i in items if i.get("status") == Status.TODO.value)
        in_progress_list = [i for i in items if i.get("status") == Status.IN_PROGRESS.value]
        current_item = in_progress_list[0] if in_progress_list else None
        current = {
            "path": current_item.get("middle_path", current_item.get("encoded_path", "")),
            "action": current_item.get("action", ""),
            "size": current_item.get("size", 0),
        } if current_item else None
        prog = upload_progress.get(repo_root)
        return {
            "lock": qstate.lock,
            "action_type": qstate.action_type,
            "action_folder": qstate.action_folder,
            "paused": qstate.paused,
            "rate_limited_until": qstate.rate_limited_until,
            "total": total,
            "done": done,
            "error": error_count,
            "todo": todo,
            "in_progress": len(in_progress_list),
            "current": current,
            "bytes_done": prog["bytes_done"] if prog else 0,
            "bytes_total": prog["bytes_total"] if prog else 0,
            "upload_phase": prog["phase"] if prog else "uploading",
            "error_items": [
                {
                    "path": i.get("middle_path", ""),
                    "action": i.get("action", ""),
                    "error": i.get("last_error", ""),
                }
                for i in items if i.get("status") == Status.ERROR.value
            ][-5:],
        }
