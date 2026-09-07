"""
Pull command (REQUIREMENTS §3.7.2) — API-driven full-auto download.

Flow (symmetric to push):
    1. hook cleanup
    2. acquire lock
    3. download remote cloud_index blob → decrypt → update local mirror
    4. rebuild local_index (so LOCAL_DELETE knows which files exist)
    5. diff (remote is authoritative for pull):
         - only_in_cloud + mode=synced → DOWNLOAD
         - only_in_local + mode=synced → LOCAL_DELETE (cloud-authoritative delete)
         - both_diff + mode=synced → DOWNLOAD (overwrite local, move old to trash)
         - remote-only + local copy present → move local to trash (conflict clean-up)
         - local-only or remote-only (no local) → skip
    6. drain queue
    7. rebuild local_index after pull
    8. archive + release lock
"""
from __future__ import annotations

import io
import os
import shutil
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
class PullResult:
    ok: bool
    counters: ConsumeCounters = field(default_factory=ConsumeCounters)
    message: str = ""
    action_folder: Optional[str] = None


def command_pull(repo_id: str, progress: Optional[ProgressFn] = None) -> PullResult:
    ctx = build_context(repo_id)

    if progress:
        progress("lock", 0, 0, "acquiring lock")
    try:
        state = QueueService.acquire(ctx.repo_root, "pull")
    except LockError as exc:
        return PullResult(ok=False, message=str(exc))
    action_folder = state.action_folder or ""

    try:
        RepositoryManager.update_status(ctx.repo_id, "syncing")

        # Step 3: download & decrypt cloud_index blob
        if progress:
            progress("cloud_index", 0, 0, "fetching cloud_index")
        cloud_index = _download_cloud_index(ctx)
        IndexService.save_cloud_index(ctx.repo_root, cloud_index)
        QueueService.snapshot_index_into_action(
            ctx.repo_root, action_folder, "cloud_index.json", cloud_index,
        )

        # Step 4: rebuild local_index
        if progress:
            progress("scan", 0, 0, "scanning local files")
        local_index = IndexService.scan_local_files(ctx.repo_root, key=ctx.key)
        IndexService.save_local_index(ctx.repo_root, local_index)
        QueueService.snapshot_index_into_action(
            ctx.repo_root, action_folder, "local_index.json", local_index,
        )

        # Step 5: diff (cloud authoritative). "added" = in cloud but not local.
        diff = IndexService.diff(cloud_index, local_index)

        filt = SyncFilterService.load(ctx.repo_root)

        # Move remote-only local copies to trash before enqueueing (conflict resolution)
        _move_remote_only_locals_to_trash(ctx, filt, local_index, cloud_index, action_folder, progress)

        local_mp_set = {e.get("middle_path", "") for e in local_index.values()}
        cloud_mp_set = {e.get("middle_path", "") for e in cloud_index.values()}

        state = QueueService.load(ctx.repo_root)
        for entry in diff.added + diff.modified:
            mp = entry["middle_path"]
            mode = SyncFilterService.get_mode(filt, mp)
            in_local = mp in local_mp_set
            status = SyncFilterService.get_status(filt, mp, in_local, True)
            action = ActionType.DOWNLOAD.value
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
        for entry in diff.deleted:
            # In local but not cloud. Only trash it when synced (cloud-authoritative).
            mp = entry["middle_path"]
            mode = SyncFilterService.get_mode(filt, mp)
            in_remote = mp in cloud_mp_set
            status = SyncFilterService.get_status(filt, mp, True, in_remote)
            action = ActionType.LOCAL_DELETE.value
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
        QueueService.save(ctx.repo_root, state)

        if not state.queue:
            QueueService.release(ctx.repo_root)
            RepositoryManager.update_status(ctx.repo_id, "ready")
            IndexService.touch_cloud_index_synced_at(ctx.repo_root)
            _run_hook(ctx, progress)
            return PullResult(
                ok=True,
                message="No changes to pull",
                action_folder=action_folder,
            )

        counters = consume_queue(ctx, progress=progress)

        # Step 7: rebuild local_index (files/paths may have changed)
        final_local = IndexService.scan_local_files(ctx.repo_root, key=ctx.key)
        IndexService.save_local_index(ctx.repo_root, final_local)

        QueueService.release(ctx.repo_root)
        RepositoryManager.update_status(ctx.repo_id, "ready")
        RepositoryManager.update_last_updated(ctx.repo_id)
        IndexService.touch_cloud_index_synced_at(ctx.repo_root)
        _run_hook(ctx, progress)

        summary = (
            f"Pull complete: {counters.downloaded} downloaded, "
            f"{counters.local_deleted} trashed locally, "
            f"{counters.errors} errors"
        )
        return PullResult(
            ok=counters.errors == 0,
            counters=counters,
            message=summary,
            action_folder=action_folder,
        )

    except Exception as exc:
        QueueService.release(ctx.repo_root)
        RepositoryManager.update_status(ctx.repo_id, "error")
        LoggerService.log_error(
            ctx.repo_root, action_folder, "PULL", "-", f"aborted: {exc}"
        )
        return PullResult(
            ok=False,
            message=f"Pull aborted: {exc}",
            action_folder=action_folder,
        )


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def _move_remote_only_locals_to_trash(
    ctx: RepoContext,
    filt: dict,
    local_index: dict,
    cloud_index: dict,
    action_folder: str,
    progress: Optional[ProgressFn],
) -> None:
    """Move local files that are in a remote-only folder to local trash.

    remote-only means the user wants these files to live in the cloud only.
    If a local copy exists, it's a conflict — we resolve by trashing the
    local copy (non-destructive). The remote copy is untouched.
    """
    cloud_middle_paths = {
        e.get("middle_path", "") for e in cloud_index.values()
    }
    moved = 0
    for entry in local_index.values():
        mp = entry.get("middle_path", "")
        if not mp:
            continue
        mode = SyncFilterService.get_mode(filt, mp)
        if mode == "remote-only":
            in_remote = mp in cloud_middle_paths
            local_path = os.path.join(ctx.repo_root, *mp.split("/"))
            status = SyncFilterService.get_status(filt, mp, True, in_remote)
            if os.path.exists(local_path):
                if not in_remote:
                    # No remote copy exists — trashing the only copy would cause
                    # data loss.  Skip and leave the user to decide.
                    LoggerService.log_file_state(
                        ctx.repo_root, action_folder, mp,
                        mode, status, True, False,
                        "skip", "ok", "remote-only but no remote backup — skipped to prevent data loss",
                    )
                    continue
                TrashService.move_to_trash(ctx.repo_root, mp)
                LoggerService.log_file_state(
                    ctx.repo_root, action_folder, mp,
                    mode, status, True, in_remote,
                    "move-local-to-trash", "ok", "conflict: remote-only with local copy",
                )
                moved += 1
            else:
                LoggerService.log_file_state(
                    ctx.repo_root, action_folder, mp,
                    mode, status, False, in_remote,
                    "skip", "ok", "remote-only, no local copy",
                )
    if progress and moved:
        progress("conflict", moved, moved, f"moved {moved} remote-only local file(s) to trash")


def _key_for(entry: dict) -> str:
    import hashlib
    return hashlib.md5(entry["middle_path"].encode("utf-8")).hexdigest()


def _download_cloud_index(ctx: RepoContext) -> dict:
    remote = ctx.cloud_index_remote_path()
    if not ctx.storage.exists(remote):
        return {}
    buf = io.BytesIO()
    ctx.storage.download(remote, buf)
    return IndexService.deserialize_cloud_index_after_download(buf.getvalue(), key=ctx.key)


def _run_hook(ctx: RepoContext, progress: Optional[ProgressFn]) -> None:
    retention = int(ctx.config.get("hook_retention_days", 7))
    if progress:
        progress("hook", 0, 0, f"cleaning trash/action older than {retention}d")
    TrashService.cleanup_old(ctx.repo_root, retention)
    LoggerService.cleanup_old_actions(ctx.repo_root, retention)

