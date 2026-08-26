"""
Push command (REQUIREMENTS §3.7.1) — API-driven full-auto upload.

Flow:
    1. hook: clean expired trash / action folders
    2. acquire lock (or fail if already locked)
    3. rebuild local_index
    4. diff local_index vs cloud_index (local mirror)
    5. enqueue UPLOAD / REMOTE_DELETE items (local is authoritative)
    6. drain queue via consume_queue
    7. update cloud_index (remove deleted, upsert modified/added)
    8. upload cloud_index blob (encrypted when repo is ENCRYPTED)
    9. archive queue.json into action_folder, release lock
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Optional

from ..service import IndexService, LoggerService, QueueService
from ..service import sync_filter_service as SyncFilterService
from ..service.action_executor import ActionExecutor  # noqa: F401 (docs)
from ..service.queue_service import ActionType, LockError
from ..repository_manager import RepositoryManager
from ._consume import ConsumeCounters, ProgressFn, consume_queue
from .context import RepoContext, build_context


@dataclass
class PushResult:
    ok: bool
    counters: ConsumeCounters = field(default_factory=ConsumeCounters)
    message: str = ""
    action_folder: Optional[str] = None


def command_push(repo_id: str, progress: Optional[ProgressFn] = None) -> PushResult:
    ctx = build_context(repo_id)

    # Step 1: hook cleanup
    _run_hook(ctx, progress)

    # Step 2: acquire lock
    if progress:
        progress("lock", 0, 0, "acquiring lock")
    try:
        state = QueueService.acquire(ctx.repo_root, "push")
    except LockError as exc:
        return PushResult(ok=False, message=str(exc))
    action_folder = state.action_folder or ""

    try:
        RepositoryManager.update_status(ctx.repo_id, "syncing")

        # Step 3: rebuild local_index
        if progress:
            progress("scan", 0, 0, "scanning local files")
        local_index = IndexService.scan_local_files(ctx.repo_root, key=ctx.key)
        IndexService.save_local_index(ctx.repo_root, local_index)
        QueueService.snapshot_index_into_action(
            ctx.repo_root, action_folder, "local_index.json", local_index,
        )

        # Step 4: diff vs cloud_index mirror (local is authoritative for push)
        cloud_index = IndexService.load_cloud_index(ctx.repo_root)
        QueueService.snapshot_index_into_action(
            ctx.repo_root, action_folder, "cloud_index.json", cloud_index,
        )
        diff = IndexService.diff(local_index, cloud_index)

        # Sync filter: only act on folders the user has checked. Unchecked
        # subtrees are invisible to push — crucially, a local file missing
        # under an unchecked subtree never becomes a REMOTE_DELETE, so the
        # remote archive is never trimmed by local absence.
        filt = SyncFilterService.load(ctx.repo_root)

        # Step 5: enqueue
        state = QueueService.load(ctx.repo_root)
        for entry in diff.added + diff.modified:
            if not SyncFilterService.is_synced(filt, entry["middle_path"]):
                continue
            key_hash = _key_for(entry)
            QueueService.enqueue(state, key_hash, {
                "middle_path": entry["middle_path"],
                "encoded_path": entry["encoded_path"],
                "size": entry.get("size", 0),
                "action": ActionType.UPLOAD.value,
            })
        for entry in diff.deleted:
            if not SyncFilterService.is_synced(filt, entry["middle_path"]):
                continue
            key_hash = _key_for(entry)
            QueueService.enqueue(state, key_hash, {
                "middle_path": entry["middle_path"],
                "encoded_path": entry["encoded_path"],
                "size": entry.get("size", 0),
                "action": ActionType.REMOTE_DELETE.value,
            })
        QueueService.save(ctx.repo_root, state)

        if not state.queue:
            # Nothing to do — still refresh cloud_index blob upload so
            # the remote is a byte-identical mirror of local intention.
            _upload_cloud_index(ctx, cloud_index)
            QueueService.release(ctx.repo_root)
            RepositoryManager.update_status(ctx.repo_id, "ready")
            return PushResult(
                ok=True,
                message="No changes to push",
                action_folder=action_folder,
            )

        # Step 6: drain queue
        counters = consume_queue(ctx, progress=progress)

        # Step 7: update cloud_index in-memory
        # (only reflect entries that actually succeeded — but our
        # consume loop already marks failed items as ERROR and leaves
        # them in the queue for retry; here we rebuild cloud_index
        # from local_index minus still-pending deletes.)
        new_cloud_index = _rebuild_cloud_index_after_push(
            ctx, local_index, cloud_index,
        )
        IndexService.save_cloud_index(ctx.repo_root, new_cloud_index)

        # Step 8: upload cloud_index blob (encrypted for ENCRYPTED repos)
        if progress:
            progress("cloud_index", 0, 0, "uploading cloud_index")
        _upload_cloud_index(ctx, new_cloud_index)

        # Step 9: archive + release
        QueueService.release(ctx.repo_root)
        RepositoryManager.update_status(ctx.repo_id, "ready")
        RepositoryManager.update_last_updated(ctx.repo_id)

        summary = (
            f"Push complete: {counters.uploaded} uploaded, "
            f"{counters.remote_deleted} removed, {counters.errors} errors"
        )
        return PushResult(
            ok=counters.errors == 0,
            counters=counters,
            message=summary,
            action_folder=action_folder,
        )

    except Exception as exc:
        RepositoryManager.update_status(ctx.repo_id, "error")
        LoggerService.log_error(
            ctx.repo_root, action_folder, "PUSH", "-", f"aborted: {exc}"
        )
        # Preserve the lock so the user can inspect / resume
        return PushResult(
            ok=False,
            message=f"Push aborted: {exc}",
            action_folder=action_folder,
        )


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def _key_for(entry: dict) -> str:
    """Use the same md5 hash IndexService uses so queue items match
    index entries deterministically."""
    import hashlib
    return hashlib.md5(entry["middle_path"].encode("utf-8")).hexdigest()


def _rebuild_cloud_index_after_push(
    ctx: RepoContext,
    local_index: dict,
    old_cloud_index: dict,
) -> dict:
    """Compute the new cloud_index after a push.

    Strategy: start from ``local_index`` (which represents what the
    user *intends* to have in the cloud after this push). Anything
    still stuck in the queue (retry_count > 0) means the corresponding
    UPLOAD/REMOTE_DELETE didn't succeed — for those we fall back to
    the ``old_cloud_index`` value to keep cloud_index in sync with
    what's actually on the cloud.
    """
    from ..service.queue_service import QueueService
    state = QueueService.load(ctx.repo_root)
    unfinished_keys = {k for k, v in state.queue.items()}

    new_cloud_index = dict(local_index)  # start from intent
    for k in unfinished_keys:
        # For unfinished items, revert to old cloud state
        if k in old_cloud_index:
            new_cloud_index[k] = old_cloud_index[k]
        else:
            new_cloud_index.pop(k, None)
    return new_cloud_index


def _upload_cloud_index(ctx: RepoContext, cloud_index: dict) -> None:
    """Serialize cloud_index (encrypting for ENCRYPTED repos) and upload."""
    payload = IndexService.serialize_cloud_index_for_upload(cloud_index, key=ctx.key)
    stream = io.BytesIO(payload)
    ctx.storage.upload(stream, ctx.cloud_index_remote_path(), len(payload))


def _run_hook(ctx: RepoContext, progress: Optional[ProgressFn]) -> None:
    from ..service import TrashService
    retention = int(ctx.config.get("hook_retention_days", 7))
    if progress:
        progress("hook", 0, 0, f"cleaning trash/action older than {retention}d")
    TrashService.cleanup_old(ctx.repo_root, retention)
    LoggerService.cleanup_old_actions(ctx.repo_root, retention)
