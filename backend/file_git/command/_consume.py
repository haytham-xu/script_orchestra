"""
Shared queue-consumption loop used by push / pull / queue commands.

Given a RepoContext with a locked ``queue.json``, run each pending
QueueItem through ActionExecutor, logging outcomes.

Returns aggregate counters so the caller can report to the user.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from ..service import (
    ActionExecutor,
    LoggerService,
    QueueService,
    Status,
)
from ..service.queue_service import QueueState
from .context import RepoContext


@dataclass
class ConsumeCounters:
    uploaded: int = 0
    downloaded: int = 0
    local_deleted: int = 0
    remote_deleted: int = 0
    errors: int = 0


ProgressFn = Callable[[str, int, int, str], None]
"""Optional progress callback: (phase, current, total, detail)."""


def consume_queue(
    ctx: RepoContext,
    *,
    progress: Optional[ProgressFn] = None,
) -> ConsumeCounters:
    """Drain the queue currently on disk. Failures are logged, not raised."""
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
    total = len(pending)

    for idx, (item_key, item) in enumerate(pending, 1):
        middle_path = item.get("middle_path", "?")
        action = item.get("action", "?")
        if progress:
            progress("queue", idx, total, f"{action} {middle_path}")

        # Mark IN_PROGRESS so crashes leave a breadcrumb
        state = QueueService.load(ctx.repo_root)
        QueueService.mark_in_progress(ctx.repo_root, state, item_key)

        outcome = executor.execute(item)

        # Reload after execute (executor may not touch queue.json, but
        # we want fresh state before mutating again)
        state = QueueService.load(ctx.repo_root)

        if outcome.ok:
            QueueService.mark_done(ctx.repo_root, state, item_key)
            LoggerService.log_success(
                ctx.repo_root, action_folder,
                action, middle_path, outcome.detail,
            )
            if action == "UPLOAD":
                counters.uploaded += 1
            elif action == "DOWNLOAD":
                counters.downloaded += 1
            elif action == "LOCAL_DELETE":
                counters.local_deleted += 1
            elif action == "REMOTE_DELETE":
                counters.remote_deleted += 1
        else:
            QueueService.mark_error(ctx.repo_root, state, item_key, outcome.detail)
            LoggerService.log_error(
                ctx.repo_root, action_folder,
                action, middle_path, outcome.detail,
            )
            counters.errors += 1

    return counters
