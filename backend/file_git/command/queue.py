"""
Queue command (REQUIREMENTS §3.7, §3.13) — resume a previously
interrupted push or pull.

When ``queue.json`` has ``lock=true``, the last push/pull crashed or
was aborted mid-flight. Running this command:

    1. Loads the existing queue state (does NOT create a new action_folder)
    2. Continues the interrupted action_folder for logs
    3. Drains the remaining queue items via consume_queue
    4. On completion, uploads cloud_index if this was a push
    5. Archives + releases lock

The command detects push-vs-pull from ``state.action_type``.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Optional

from ..repository_manager import RepositoryManager
from ..service import IndexService, LoggerService, QueueService
from ._consume import ConsumeCounters, ProgressFn, consume_queue
from .context import RepoContext, build_context


@dataclass
class QueueResult:
    ok: bool
    counters: ConsumeCounters = field(default_factory=ConsumeCounters)
    message: str = ""
    action_folder: Optional[str] = None


def command_queue(repo_id: str, progress: Optional[ProgressFn] = None) -> QueueResult:
    ctx = build_context(repo_id)

    state = QueueService.load(ctx.repo_root)
    if not state.lock:
        return QueueResult(
            ok=True,
            message="Nothing to resume — queue is empty and unlocked.",
        )
    if not state.action_folder or not state.action_type:
        return QueueResult(
            ok=False,
            message="Lock is held but action_folder/action_type is missing. "
                    "Inspect .fgit/queue.json manually.",
        )

    action_folder = state.action_folder
    action_type = state.action_type

    try:
        RepositoryManager.update_status(ctx.repo_id, "syncing")
        counters = consume_queue(ctx, progress=progress)

        # For push, we need to refresh cloud_index blob after successful drain
        if action_type == "push":
            # Recompute cloud_index from local (respecting still-pending items)
            local_index = IndexService.load_local_index(ctx.repo_root)
            old_cloud_index = IndexService.load_cloud_index(ctx.repo_root)
            new_cloud_index = _cloud_index_after_resume(
                ctx, local_index, old_cloud_index,
            )
            IndexService.save_cloud_index(ctx.repo_root, new_cloud_index)
            if progress:
                progress("cloud_index", 0, 0, "uploading cloud_index")
            _upload_cloud_index(ctx, new_cloud_index)

        elif action_type == "pull":
            # Rebuild local_index after downloads/deletes
            new_local = IndexService.scan_local_files(ctx.repo_root, key=ctx.key)
            IndexService.save_local_index(ctx.repo_root, new_local)

        # Release only if the queue is now empty; otherwise leave locked
        # so the user can resume again.
        final_state = QueueService.load(ctx.repo_root)
        if not final_state.queue:
            QueueService.release(ctx.repo_root)
            RepositoryManager.update_status(ctx.repo_id, "ready")
            RepositoryManager.update_last_updated(ctx.repo_id)
            summary = _summarize(action_type, counters, resumed=True)
        else:
            RepositoryManager.update_status(ctx.repo_id, "error")
            summary = (
                f"Resumed {action_type}, but {len(final_state.queue)} items "
                f"still failing. Fix underlying issue and try again."
            )

        return QueueResult(
            ok=counters.errors == 0 and not final_state.queue,
            counters=counters,
            message=summary,
            action_folder=action_folder,
        )

    except Exception as exc:
        RepositoryManager.update_status(ctx.repo_id, "error")
        LoggerService.log_error(
            ctx.repo_root, action_folder, "QUEUE", "-", f"aborted: {exc}"
        )
        return QueueResult(
            ok=False,
            message=f"Queue resume aborted: {exc}",
            action_folder=action_folder,
        )


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def _cloud_index_after_resume(
    ctx: RepoContext,
    local_index: dict,
    old_cloud_index: dict,
) -> dict:
    unfinished_keys = set(QueueService.load(ctx.repo_root).queue.keys())
    new_cloud_index = dict(local_index)
    for k in unfinished_keys:
        if k in old_cloud_index:
            new_cloud_index[k] = old_cloud_index[k]
        else:
            new_cloud_index.pop(k, None)
    return new_cloud_index


def _upload_cloud_index(ctx: RepoContext, cloud_index: dict) -> None:
    payload = IndexService.serialize_cloud_index_for_upload(cloud_index, key=ctx.key)
    ctx.storage.upload(io.BytesIO(payload), ctx.cloud_index_remote_path(), len(payload))


def _summarize(action_type: str, counters: ConsumeCounters, resumed: bool) -> str:
    parts = []
    if counters.uploaded:
        parts.append(f"{counters.uploaded} uploaded")
    if counters.downloaded:
        parts.append(f"{counters.downloaded} downloaded")
    if counters.local_deleted:
        parts.append(f"{counters.local_deleted} trashed locally")
    if counters.remote_deleted:
        parts.append(f"{counters.remote_deleted} removed on cloud")
    if counters.errors:
        parts.append(f"{counters.errors} errors")
    body = ", ".join(parts) if parts else "no items processed"
    prefix = "Resumed" if resumed else "Completed"
    return f"{prefix} {action_type}: {body}"
