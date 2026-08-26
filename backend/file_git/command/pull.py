"""
Pull command (REQUIREMENTS §3.7.2) — API-driven full-auto download.

Flow (symmetric to push):
    1. hook cleanup
    2. acquire lock
    3. download remote cloud_index blob → decrypt → update local mirror
    4. rebuild local_index (so LOCAL_DELETE knows which files exist)
    5. diff (remote is authoritative for pull):
         - only_in_cloud → DOWNLOAD
         - only_in_local → LOCAL_DELETE
         - both_diff → DOWNLOAD (overwrite local)
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
from ._consume import ConsumeCounters, ProgressFn, consume_queue
from .context import RepoContext, build_context


class UnsyncedNoBackupError(Exception):
    """A file was un-checked but has no remote backup — refuse to move it."""


@dataclass
class PullResult:
    ok: bool
    counters: ConsumeCounters = field(default_factory=ConsumeCounters)
    message: str = ""
    action_folder: Optional[str] = None


def command_pull(repo_id: str, progress: Optional[ProgressFn] = None) -> PullResult:
    ctx = build_context(repo_id)

    _run_hook(ctx, progress)

    if progress:
        progress("lock", 0, 0, "acquiring lock")
    try:
        state = QueueService.acquire(ctx.repo_root, "pull")
    except LockError as exc:
        return PullResult(ok=False, message=str(exc))
    action_folder = state.action_folder or ""

    try:
        RepositoryManager.update_status(ctx.repo_id, "syncing")

        # Step 0: apply sync-filter un-checks — move now-excluded local files
        # to the unsynced buffer (never delete). Refuses to move a file that
        # has no remote backup (that would leave only the buffer copy).
        _apply_unchecks(ctx, progress)

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

        # Step 5: diff (cloud authoritative). Note the argument order —
        # we compare cloud→local, so "added" here means "in cloud but
        # not local" → needs DOWNLOAD.
        diff = IndexService.diff(cloud_index, local_index)

        # Sync filter: only pull folders the user has checked.
        filt = SyncFilterService.load(ctx.repo_root)

        state = QueueService.load(ctx.repo_root)
        for entry in diff.added + diff.modified:
            # Only download files under checked subtrees; never pull back
            # folders the user chose to keep remote-only.
            if not SyncFilterService.is_synced(filt, entry["middle_path"]):
                continue
            key_hash = _key_for(entry)
            QueueService.enqueue(state, key_hash, {
                "middle_path": entry["middle_path"],
                "encoded_path": entry["encoded_path"],
                "size": entry.get("size", 0),
                "action": ActionType.DOWNLOAD.value,
            })
        for entry in diff.deleted:
            # In local but not cloud. Only trash it when the path is still
            # synced (i.e. cloud-authoritative deletion). Un-checked local
            # files are handled by the move-to-buffer step below, not here.
            if not SyncFilterService.is_synced(filt, entry["middle_path"]):
                continue
            key_hash = _key_for(entry)
            QueueService.enqueue(state, key_hash, {
                "middle_path": entry["middle_path"],
                "encoded_path": entry["encoded_path"],
                "size": entry.get("size", 0),
                "action": ActionType.LOCAL_DELETE.value,
            })
        QueueService.save(ctx.repo_root, state)

        if not state.queue:
            QueueService.release(ctx.repo_root)
            RepositoryManager.update_status(ctx.repo_id, "ready")
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

    except UnsyncedNoBackupError as exc:
        # Safety refusal: don't leave the repo locked.
        QueueService.release(ctx.repo_root)
        RepositoryManager.update_status(ctx.repo_id, "ready")
        LoggerService.log_error(
            ctx.repo_root, action_folder, "PULL", "-", f"refused: {exc}"
        )
        return PullResult(
            ok=False,
            message=str(exc),
            action_folder=action_folder,
        )

    except Exception as exc:
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

def _apply_unchecks(ctx: RepoContext, progress: Optional[ProgressFn]) -> None:
    """Move local files that are no longer synced into the unsynced buffer.

    Runs before scanning, so the fresh local_index reflects the moves.
    Refuses (raises UnsyncedNoBackupError) if a file has no remote backup —
    moving it would leave only the buffer copy, defeating the point.
    """
    # First scan the current local index so the filter sees real files.
    local_index = IndexService.scan_local_files(ctx.repo_root, key=ctx.key)
    IndexService.save_local_index(ctx.repo_root, local_index)

    to_move = SyncFilterService.unsynced_local_files(ctx.repo_root)
    if not to_move:
        return

    no_backup = [m["middle_path"] for m in to_move if not m["has_remote_backup"]]
    if no_backup:
        preview = ", ".join(no_backup[:5])
        more = "" if len(no_backup) <= 5 else f" (+{len(no_backup) - 5} more)"
        raise UnsyncedNoBackupError(
            f"Refusing to move {len(no_backup)} un-checked file(s) with no remote "
            f"backup: {preview}{more}. Push them first, or re-check the folder."
        )

    buffer_root = os.path.join(ctx.repo_root, ".fgit", "buffer", "_unsynced")
    moved = 0
    for m in to_move:
        mp = m["middle_path"]
        src = os.path.join(ctx.repo_root, *mp.split("/"))
        if not os.path.exists(src):
            continue
        dst = os.path.join(buffer_root, *mp.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        moved += 1
    if progress:
        progress("unsync", moved, len(to_move), f"moved {moved} unsynced file(s) to buffer")


def _key_for(entry: dict) -> str:
    import hashlib
    return hashlib.md5(entry["middle_path"].encode("utf-8")).hexdigest()


def _download_cloud_index(ctx: RepoContext) -> dict:
    remote = ctx.cloud_index_remote_path()
    if not ctx.storage.exists(remote):
        # First-ever pull — no remote index exists, treat as empty
        return {}
    buf = io.BytesIO()
    ctx.storage.download(remote, buf)
    return IndexService.deserialize_cloud_index_after_download(buf.getvalue(), key=ctx.key)


def _run_hook(ctx: RepoContext, progress: Optional[ProgressFn]) -> None:
    from ..service import TrashService
    retention = int(ctx.config.get("hook_retention_days", 7))
    if progress:
        progress("hook", 0, 0, f"cleaning trash/action older than {retention}d")
    TrashService.cleanup_old(ctx.repo_root, retention)
    LoggerService.cleanup_old_actions(ctx.repo_root, retention)
