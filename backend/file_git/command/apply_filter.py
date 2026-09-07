"""
Apply Sync Filter command.

Reconciles the current sync filter state against both local files and the
remote cloud_index. Triggered explicitly by the user via the Apply button.

Algorithm (stateless, idempotent full scan):
    1. hook cleanup
    2. acquire lock
    3. download latest cloud_index from remote
    4. rebuild local_index
    5. for every file in the union of local + cloud:
         mode        | in_local | in_cloud | action
         remote-only |    yes   |   any    | LOCAL_DELETE  (soft: move to local trash)
         remote-only |    no    |   yes    | (no-op, correct state)
         local-only  |   any    |   yes    | REMOTE_TRASH  (soft: move to remote trash)
         local-only  |   yes    |   no     | (no-op, correct state)
         synced      |   yes    |   no     | UPLOAD
         synced      |   no     |   yes    | DOWNLOAD
         synced      |   yes    |   yes    | (no-op, already in sync)
    6. drain queue
    7. update and upload cloud_index
    8. rebuild local_index
    9. release lock
   10. hook cleanup (trash/action retention)
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Optional

from ..repository_manager import RepositoryManager
from ..service import IndexService, LoggerService, QueueService
from ..service import sync_filter_service as SyncFilterService
from ..service.queue_service import ActionType, LockError
from ..service.trash_service import TrashService
from ._consume import ConsumeCounters, ProgressFn, consume_queue
from .context import RepoContext, build_context


@dataclass
class ApplyFilterResult:
    ok: bool
    counters: ConsumeCounters = field(default_factory=ConsumeCounters)
    message: str = ""
    action_folder: Optional[str] = None


def command_apply_filter(
    repo_id: str,
    progress: Optional[ProgressFn] = None,
) -> ApplyFilterResult:
    ctx = build_context(repo_id)

    if progress:
        progress("lock", 0, 0, "acquiring lock")
    try:
        state = QueueService.acquire(ctx.repo_root, "apply_filter")
    except LockError as exc:
        return ApplyFilterResult(ok=False, message=str(exc))
    action_folder = state.action_folder or ""

    try:
        RepositoryManager.update_status(ctx.repo_id, "syncing")

        # Step 3: download latest cloud_index
        if progress:
            progress("cloud_index", 0, 0, "fetching cloud_index from remote")
        cloud_index = _download_cloud_index(ctx)
        IndexService.save_cloud_index(ctx.repo_root, cloud_index)

        # Step 4: rebuild local_index
        if progress:
            progress("scan", 0, 0, "scanning local files")
        local_index = IndexService.scan_local_files(ctx.repo_root, key=ctx.key)
        IndexService.save_local_index(ctx.repo_root, local_index)

        filt = SyncFilterService.load(ctx.repo_root)

        local_mp = {e.get("middle_path", ""): e for e in local_index.values() if e.get("middle_path")}
        cloud_mp = {e.get("middle_path", ""): e for e in cloud_index.values() if e.get("middle_path")}
        all_paths = set(local_mp) | set(cloud_mp)

        state = QueueService.load(ctx.repo_root)

        for mp in sorted(all_paths):
            in_local = mp in local_mp
            in_cloud = mp in cloud_mp
            mode = SyncFilterService.get_mode(filt, mp)
            status = SyncFilterService.get_status(filt, mp, in_local, in_cloud)
            entry = cloud_mp.get(mp) or local_mp.get(mp)
            encoded_path = entry.get("encoded_path", mp) if entry else mp
            size = entry.get("size", 0) if entry else 0
            key_hash = _key_for(mp)

            if mode == "remote-only" and in_local:
                QueueService.enqueue(state, key_hash, {
                    "middle_path": mp,
                    "encoded_path": encoded_path,
                    "size": size,
                    "action": ActionType.LOCAL_DELETE.value,
                })
                LoggerService.log_file_state(
                    ctx.repo_root, action_folder, mp,
                    mode, status, in_local, in_cloud, ActionType.LOCAL_DELETE.value,
                )
            elif mode == "local-only" and in_cloud:
                QueueService.enqueue(state, key_hash, {
                    "middle_path": mp,
                    "encoded_path": encoded_path,
                    "size": size,
                    "action": ActionType.REMOTE_TRASH.value,
                })
                LoggerService.log_file_state(
                    ctx.repo_root, action_folder, mp,
                    mode, status, in_local, in_cloud, ActionType.REMOTE_TRASH.value,
                )
            elif mode == "synced" and in_local and not in_cloud:
                QueueService.enqueue(state, key_hash, {
                    "middle_path": mp,
                    "encoded_path": local_mp[mp].get("encoded_path", mp),
                    "size": local_mp[mp].get("size", 0),
                    "action": ActionType.UPLOAD.value,
                })
                LoggerService.log_file_state(
                    ctx.repo_root, action_folder, mp,
                    mode, status, True, False, ActionType.UPLOAD.value,
                )
            elif mode == "synced" and not in_local and in_cloud:
                QueueService.enqueue(state, key_hash, {
                    "middle_path": mp,
                    "encoded_path": cloud_mp[mp].get("encoded_path", mp),
                    "size": cloud_mp[mp].get("size", 0),
                    "action": ActionType.DOWNLOAD.value,
                })
                LoggerService.log_file_state(
                    ctx.repo_root, action_folder, mp,
                    mode, status, False, True, ActionType.DOWNLOAD.value,
                )
            else:
                LoggerService.log_file_state(
                    ctx.repo_root, action_folder, mp,
                    mode, status, in_local, in_cloud, "skip", "ok", "no action needed",
                )

        QueueService.save(ctx.repo_root, state)

        if not state.queue:
            _upload_cloud_index(ctx, cloud_index)
            QueueService.release(ctx.repo_root)
            RepositoryManager.update_status(ctx.repo_id, "ready")
            _run_hook(ctx, progress)
            return ApplyFilterResult(
                ok=True,
                message="Sync filter already consistent — nothing to do",
                action_folder=action_folder,
            )

        # Step 6: drain queue
        counters = consume_queue(ctx, progress=progress)

        # Step 7: rebuild local_index (reflects downloads + deletions)
        final_local = IndexService.scan_local_files(ctx.repo_root, key=ctx.key)
        IndexService.save_local_index(ctx.repo_root, final_local)

        # Step 8: rebuild cloud_index using updated local state
        new_cloud_index = _rebuild_cloud_index_after_apply(
            ctx, final_local, cloud_index, filt,
        )
        IndexService.save_cloud_index(ctx.repo_root, new_cloud_index)

        if progress:
            progress("cloud_index", 0, 0, "uploading cloud_index")
        _upload_cloud_index(ctx, new_cloud_index)

        QueueService.release(ctx.repo_root)
        RepositoryManager.update_status(ctx.repo_id, "ready")
        RepositoryManager.update_last_updated(ctx.repo_id)
        _run_hook(ctx, progress)

        summary = (
            f"Apply complete: {counters.uploaded} uploaded, "
            f"{counters.downloaded} downloaded, "
            f"{counters.local_deleted} trashed locally, "
            f"{counters.remote_deleted} trashed remotely, "
            f"{counters.errors} errors"
        )
        return ApplyFilterResult(
            ok=counters.errors == 0,
            counters=counters,
            message=summary,
            action_folder=action_folder,
        )

    except Exception as exc:
        QueueService.release(ctx.repo_root)
        RepositoryManager.update_status(ctx.repo_id, "error")
        LoggerService.log_error(
            ctx.repo_root, action_folder, "APPLY_FILTER", "-", f"aborted: {exc}"
        )
        return ApplyFilterResult(
            ok=False,
            message=f"Apply aborted: {exc}",
            action_folder=action_folder,
        )


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def _key_for(middle_path: str) -> str:
    import hashlib
    return hashlib.md5(middle_path.encode("utf-8")).hexdigest()


def _download_cloud_index(ctx: RepoContext) -> dict:
    remote = ctx.cloud_index_remote_path()
    if not ctx.storage.exists(remote):
        return {}
    buf = io.BytesIO()
    ctx.storage.download(remote, buf)
    return IndexService.deserialize_cloud_index_after_download(buf.getvalue(), key=ctx.key)


def _upload_cloud_index(ctx: RepoContext, cloud_index: dict) -> None:
    payload = IndexService.serialize_cloud_index_for_upload(cloud_index, key=ctx.key)
    stream = io.BytesIO(payload)
    ctx.storage.upload(stream, ctx.cloud_index_remote_path(), len(payload))
    IndexService.touch_cloud_index_synced_at(ctx.repo_root)


def _rebuild_cloud_index_after_apply(
    ctx: RepoContext,
    local_index: dict,
    old_cloud_index: dict,
    filt: dict,
) -> dict:
    """Compute cloud_index after apply:
    - synced files: use local_index (source of truth for uploads)
    - remote-only files: keep from old cloud_index (we didn't touch them)
    - local-only files: remove from cloud_index (they were REMOTE_TRASHed)
    """
    state = QueueService.load(ctx.repo_root)
    unfinished_keys = set(state.queue.keys())

    new_cloud = {}

    # Keep remote-only files from old cloud_index
    for k, entry in old_cloud_index.items():
        mp = entry.get("middle_path", "")
        mode = SyncFilterService.get_mode(filt, mp)
        if mode == "remote-only":
            new_cloud[k] = entry

    # Add synced files from local_index (reflects uploads)
    for k, entry in local_index.items():
        mp = entry.get("middle_path", "")
        mode = SyncFilterService.get_mode(filt, mp)
        if mode == "synced":
            if k in unfinished_keys and k in old_cloud_index:
                new_cloud[k] = old_cloud_index[k]
            else:
                new_cloud[k] = entry

    return new_cloud


def _run_hook(ctx: RepoContext, progress: Optional[ProgressFn]) -> None:
    retention = int(ctx.config.get("hook_retention_days", 7))
    if progress:
        progress("hook", 0, 0, f"cleaning trash/action older than {retention}d")
    TrashService.cleanup_old(ctx.repo_root, retention)
    LoggerService.cleanup_old_actions(ctx.repo_root, retention)
