"""
Push command — API-driven full-auto upload.

Flow:
    1. hook: clean expired trash / action folders
    2. acquire lock (or fail if already locked)
    3. rebuild local_index
    4. download latest cloud_index from remote (so two machines can push safely)
    5. diff local_index vs cloud_index — only synced paths; skip local-only/remote-only
    6. enqueue UPLOAD / REMOTE_TRASH items
    7. drain queue via consume_queue
    8. update cloud_index (remove trashed, upsert modified/added)
    9. upload cloud_index blob (encrypted when repo is ENCRYPTED)
   10. archive queue.json into action_folder, release lock
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


def command_push(repo_id: str, progress: Optional[ProgressFn] = None,
                  upload_only: bool = False) -> PushResult:
    """Push local changes to remote.

    upload_only=True skips REMOTE_TRASH for files not in local_index —
    useful for "merge upload" scenarios where the caller intentionally
    has only a subset of remote files locally and must not delete the rest.
    """
    ctx = build_context(repo_id)

    # Step 1: acquire lock
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

        # Step 4: download latest cloud_index from remote, then diff
        if progress:
            progress("cloud_index", 0, 0, "fetching cloud_index from remote")
        cloud_index = _download_cloud_index(ctx)
        IndexService.save_cloud_index(ctx.repo_root, cloud_index)
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
        cloud_mp_set = {e.get("middle_path", "") for e in cloud_index.values()}
        for entry in diff.added + diff.modified:
            mp = entry["middle_path"]
            mode = SyncFilterService.get_mode(filt, mp)
            in_remote = mp in cloud_mp_set
            status = SyncFilterService.get_status(filt, mp, True, in_remote)
            action = ActionType.UPLOAD.value
            if mode != "synced":
                LoggerService.log_file_state(
                    ctx.repo_root, action_folder, mp,
                    mode, status, True, in_remote, "skip", "ok", "skipped by sync filter",
                )
                continue
            key_hash = _key_for(entry)
            QueueService.enqueue(state, key_hash, {
                "middle_path": mp,
                "encoded_path": entry["encoded_path"],
                "size": entry.get("size", 0),
                "action": action,
            })
            LoggerService.log_file_state(
                ctx.repo_root, action_folder, mp,
                mode, status, True, in_remote, action,
            )
        local_mp_set = {e.get("middle_path", "") for e in local_index.values()}
        for entry in diff.deleted:
            mp = entry["middle_path"]
            if upload_only:
                # Caller asked for upload-only mode: skip REMOTE_TRASH entirely.
                continue
            mode = SyncFilterService.get_mode(filt, mp)
            in_local = mp in local_mp_set
            status = SyncFilterService.get_status(filt, mp, in_local, True)
            action = ActionType.REMOTE_TRASH.value
            if mode != "synced":
                LoggerService.log_file_state(
                    ctx.repo_root, action_folder, mp,
                    mode, status, in_local, True, "skip", "ok", "skipped by sync filter",
                )
                continue
            key_hash = _key_for(entry)
            QueueService.enqueue(state, key_hash, {
                "middle_path": mp,
                "encoded_path": entry["encoded_path"],
                "size": entry.get("size", 0),
                "action": action,
            })
            LoggerService.log_file_state(
                ctx.repo_root, action_folder, mp,
                mode, status, in_local, True, action,
            )
        QueueService.save(ctx.repo_root, state)

        if not state.queue:
            _upload_cloud_index(ctx, cloud_index)
            QueueService.release(ctx.repo_root)
            RepositoryManager.update_status(ctx.repo_id, "ready")
            _run_hook(ctx, progress)
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
            ctx, local_index, cloud_index, upload_only=upload_only,
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
        _run_hook(ctx, progress)

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
    upload_only: bool = False,
) -> dict:
    """Compute the new cloud_index after a push.

    Normal mode: start from ``local_index`` entries that are synced (skip
    local-only — their bytes were never uploaded so they must not appear in
    cloud_index, which would confuse other machines into trying to download
    them). Failed queue items revert to old_cloud_index values.

    upload_only mode: start from ``old_cloud_index`` (preserve existing
    remote files) and merge in only the local_index entries that were
    successfully uploaded. This prevents losing remote-only entries when
    only a subset of remote files is held locally.
    """
    from ..service.queue_service import QueueService
    from ..service import sync_filter_service as SyncFilterService
    filt = SyncFilterService.load(ctx.repo_root)
    state = QueueService.load(ctx.repo_root)
    unfinished_keys = {k for k, v in state.queue.items()}

    if upload_only:
        # Base = old cloud state; layer on top whatever local has (uploaded files)
        new_cloud_index = dict(old_cloud_index)
        for k, entry in local_index.items():
            if k not in unfinished_keys:
                new_cloud_index[k] = entry
    else:
        new_cloud_index = {}
        for k, entry in local_index.items():
            mp = entry.get("middle_path", "")
            if SyncFilterService.get_mode(filt, mp) == "local-only":
                continue  # never expose local-only files in cloud_index
            if k in unfinished_keys:
                if k in old_cloud_index:
                    new_cloud_index[k] = old_cloud_index[k]
                # else: new file that failed to upload — omit from cloud_index
            else:
                new_cloud_index[k] = entry
    return new_cloud_index


def _download_cloud_index(ctx: RepoContext) -> dict:
    remote = ctx.cloud_index_remote_path()
    if not ctx.storage.exists(remote):
        return {}
    buf = io.BytesIO()
    ctx.storage.download(remote, buf)
    return IndexService.deserialize_cloud_index_after_download(buf.getvalue(), key=ctx.key)


def _upload_cloud_index(ctx: RepoContext, cloud_index: dict) -> None:
    """Serialize cloud_index (encrypting for ENCRYPTED repos) and upload."""
    payload = IndexService.serialize_cloud_index_for_upload(cloud_index, key=ctx.key)
    stream = io.BytesIO(payload)
    ctx.storage.upload(stream, ctx.cloud_index_remote_path(), len(payload))
    IndexService.touch_cloud_index_synced_at(ctx.repo_root)


def _run_hook(ctx: RepoContext, progress: Optional[ProgressFn]) -> None:
    from ..service import TrashService
    retention = int(ctx.config.get("hook_retention_days", 7))
    if progress:
        progress("hook", 0, 0, f"cleaning trash/action older than {retention}d")
    TrashService.cleanup_old(ctx.repo_root, retention)
    LoggerService.cleanup_old_actions(ctx.repo_root, retention)
