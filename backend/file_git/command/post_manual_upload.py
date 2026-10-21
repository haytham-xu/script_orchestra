"""
Post Manual Upload — Step 4 (REQUIREMENTS §3.7.4, §S4).

Called after the user finishes dragging the buffer files (ENCRYPTED)
or the source files (ORIGINAL) into the cloud APP.

Flow:
    1. Verify the repo is locked by a prior manual_upload
    2. Fetch the cloud API listing under the pending subpath
    3. Reconcile local pending_upload.json with what actually landed
       on the cloud → update cloud_index accordingly
    4. Encrypt (if ENCRYPTED) and upload cloud_index.json
    5. Clear buffer entries and pending_upload.json
    6. Archive queue.json into action_folder, release lock
"""
from __future__ import annotations

import io
import json
import os
from dataclasses import dataclass, field
from typing import List, Optional

from ..repository_manager import RepositoryManager
from ..service import IndexService, LoggerService, QueueService
from ..websocket_service import emit_progress
from .context import RepoContext, build_context
from .manual_upload import PENDING_FILENAME


@dataclass
class PostManualUploadResult:
    ok: bool
    message: str = ""
    confirmed: int = 0
    missing: List[str] = field(default_factory=list)
    action_folder: Optional[str] = None


def command_post_manual_upload(repo_id: str) -> PostManualUploadResult:
    ctx = build_context(repo_id)

    state = QueueService.load(ctx.repo_root)
    if not state.lock or state.action_type != "manual_upload":
        return PostManualUploadResult(
            ok=False,
            message=(
                "No manual upload in progress. Trigger 'Manual Upload' first."
            ),
        )
    action_folder = state.action_folder or ""

    pending_path = os.path.join(ctx.repo_root, ".fgit", PENDING_FILENAME)
    if not os.path.isfile(pending_path):
        return PostManualUploadResult(
            ok=False,
            message="pending_upload.json missing — nothing to confirm.",
            action_folder=action_folder,
        )

    try:
        with open(pending_path, "r", encoding="utf-8") as f:
            pending = json.load(f)
        entries = pending.get("entries", [])
        subpath = pending.get("subpath", "")

        # Step 2: fetch cloud listing scoped to remote_root/<encoded_subpath>
        # Normalize remote_path to strip leading "/" for consistent key lookup
        # (MockCloudStorage returns paths with a leading "/" while BaiduStorage
        # may or may not, depending on whether root_prefix has a leading "/").
        remote_scan_prefix = _cloud_prefix(ctx, subpath)
        emit_progress(repo_id, "post_manual_upload", "list", 0, 4, "Fetching cloud listing...")
        cloud_listing = {
            m["remote_path"].lstrip("/"): m
            for m in ctx.storage.list_files(remote_scan_prefix)
        }

        # Safety guard: a manual upload confirm should find the files the user
        # just dragged to the cloud. If the live listing comes back EMPTY while
        # we still have pending entries, the listing almost certainly failed
        # (rate limit / timeout / wrong backend) OR the user has not actually
        # uploaded yet. Either way, proceeding would feed 0 confirmed entries
        # into the reconcile and (historically) wipe real cloud_index data.
        # Abort WITHOUT touching cloud_index and keep the lock so the user can
        # retry after fixing the upload. (See _reconcile_cloud_index note.)
        if entries and not cloud_listing:
            msg = (
                f"Cloud listing under {remote_scan_prefix!r} is empty but "
                f"{len(entries)} file(s) are pending confirmation. Nothing was "
                "changed. Make sure the files were dragged into the cloud app "
                "(and the correct cloud backend is configured), then retry Confirm."
            )
            LoggerService.log_error(
                ctx.repo_root, action_folder, "MANUAL_UPLOAD_CONFIRM", "-", msg,
            )
            return PostManualUploadResult(
                ok=False, message=msg, confirmed=0,
                missing=[e["middle_path"] for e in entries],
                action_folder=action_folder,
            )

        emit_progress(repo_id, "post_manual_upload", "reconcile", 1, 4,
                      f"Reconciling {len(entries)} files against {len(cloud_listing)} cloud entries...")

        # Step 3: match pending entries against actual cloud state
        confirmed_entries: List[dict] = []
        missing: List[str] = []
        for entry in entries:
            expected_remote = ctx.storage.to_listing_key(
                _remote_full_for(ctx, entry["encoded_path"])
            )
            if expected_remote in cloud_listing:
                cloud_meta = cloud_listing[expected_remote]
                confirmed_entries.append({
                    **entry,
                    "cloud_size": cloud_meta["size"],
                })
            else:
                missing.append(entry["middle_path"])

        # Step 3b: merge into cloud_index (subpath is authoritative for
        # the touched region — replace all entries under this subpath
        # with what's now actually on cloud)
        current_cloud_index = IndexService.load_cloud_index(ctx.repo_root)
        new_cloud_index = _reconcile_cloud_index(
            current_cloud_index, confirmed_entries, subpath,
        )
        IndexService.save_cloud_index(ctx.repo_root, new_cloud_index)

        QueueService.snapshot_index_into_action(
            ctx.repo_root, action_folder, "cloud_index.json", new_cloud_index,
        )

        # Step 3c: rebuild local_index to reflect current disk state
        emit_progress(repo_id, "post_manual_upload", "local_index", 2, 4, "Rebuilding local index...")
        new_local_index = IndexService.scan_local_files(ctx.repo_root, key=ctx.key)
        IndexService.save_local_index(ctx.repo_root, new_local_index)
        QueueService.snapshot_index_into_action(
            ctx.repo_root, action_folder, "local_index.json", new_local_index,
        )

        # Step 4: upload cloud_index.json
        emit_progress(repo_id, "post_manual_upload", "upload_index", 3, 4, "Uploading cloud index...")
        _upload_cloud_index(ctx, new_cloud_index)
        emit_progress(repo_id, "post_manual_upload", "done", 4, 4,
                      f"Done: {len(confirmed_entries)} confirmed"
                      + (f", {len(missing)} missing" if missing else ""))

        # Step 5: clean up buffer + pending file
        if ctx.mode == "ENCRYPTED":
            _clear_buffer_entries(ctx.repo_root, confirmed_entries)
        os.remove(pending_path)

        # Log outcomes
        for e in confirmed_entries:
            LoggerService.log_success(
                ctx.repo_root, action_folder, "MANUAL_UPLOAD_CONFIRM",
                e["middle_path"], f"cloud size {e.get('cloud_size', '?')}",
            )
        for m_path in missing:
            LoggerService.log_error(
                ctx.repo_root, action_folder, "MANUAL_UPLOAD_CONFIRM",
                m_path, "not found on cloud after manual upload",
            )

        # Step 6: archive + unlock
        QueueService.release(ctx.repo_root)
        RepositoryManager.update_status(ctx.repo_id, "ready")
        RepositoryManager.update_last_updated(ctx.repo_id)

        msg = f"Manual upload confirmed: {len(confirmed_entries)} files"
        if missing:
            msg += f", {len(missing)} still missing on cloud"

        return PostManualUploadResult(
            ok=len(missing) == 0,
            message=msg,
            confirmed=len(confirmed_entries),
            missing=missing,
            action_folder=action_folder,
        )

    except Exception as exc:
        LoggerService.log_error(
            ctx.repo_root, action_folder, "MANUAL_UPLOAD_CONFIRM", "-",
            f"aborted: {exc}",
        )
        RepositoryManager.update_status(ctx.repo_id, "error")
        # Preserve lock — user can inspect and retry
        return PostManualUploadResult(
            ok=False,
            message=f"Post manual upload aborted: {exc}",
            action_folder=action_folder,
        )


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def _remote_full_for(ctx: RepoContext, encoded_path: str) -> str:
    return f"{ctx.remote_root.rstrip('/')}/{encoded_path.lstrip('/')}"


def _cloud_prefix(ctx: RepoContext, subpath: str) -> str:
    """Compute the cloud prefix to list based on the local subpath.

    For ENCRYPTED repos we encode each segment of ``subpath`` to hmac16
    so we ask the API only for that sub-tree, not the whole remote_root.
    """
    if not subpath:
        return ctx.remote_root
    from ..crypto import hmac16_segment
    if ctx.mode == "ENCRYPTED":
        encoded_subpath = "/".join(
            hmac16_segment(ctx.key, seg)  # type: ignore[arg-type]
            for seg in subpath.split("/")
            if seg
        )
    else:
        encoded_subpath = subpath
    return f"{ctx.remote_root.rstrip('/')}/{encoded_subpath}"


def _reconcile_cloud_index(
    current: dict,
    confirmed_entries: list,
    subpath: str,
) -> dict:
    """Merge just-confirmed entries into the cloud_index (additive).

    Manual upload is a *fill-gaps* operation: ``confirmed_entries`` only ever
    contains the files this batch uploaded (the gaps), never the full subtree.
    We therefore MERGE — add/update the confirmed entries and leave every other
    entry untouched.

    IMPORTANT — do NOT delete entries under ``subpath``. An earlier version
    removed the whole subtree and re-added only the confirmed entries; combined
    with an empty/partial cloud listing that silently wiped thousands of real,
    already-synced entries (e.g. the entire ``tr/`` tree). Manual upload can
    only ever add: it cannot enumerate pre-existing cloud files by middle_path
    (encoding is one-way), so it has no authority to prune. Deletions are the
    job of push / rebuild_cloud_index, not confirm.
    """
    import hashlib

    new_index = dict(current)
    for e in confirmed_entries:
        key = hashlib.md5(e["middle_path"].encode("utf-8")).hexdigest()
        new_index[key] = {
            "middle_path": e["middle_path"],
            "encoded_path": e["encoded_path"],
            "size": e["size"],
        }
    return new_index


def _upload_cloud_index(ctx: RepoContext, cloud_index: dict) -> None:
    payload = IndexService.serialize_cloud_index_for_upload(cloud_index, key=ctx.key)
    ctx.storage.upload(io.BytesIO(payload), ctx.cloud_index_remote_path(), len(payload))
    IndexService.touch_cloud_index_synced_at(ctx.repo_root)


def _clear_buffer_entries(repo_root: str, entries: list) -> None:
    buffer_root = os.path.join(repo_root, ".fgit", "buffer")
    for e in entries:
        buf_full = os.path.join(buffer_root, *e["encoded_path"].split("/"))
        if os.path.isfile(buf_full):
            try:
                os.remove(buf_full)
            except OSError as exc:
                print(f"[post_manual_upload] failed to remove {buf_full}: {exc}")
    # Prune empty subdirs under buffer_root
    for cur_dir, dirs, files in os.walk(buffer_root, topdown=False):
        if cur_dir == buffer_root:
            continue
        if not os.listdir(cur_dir):
            try:
                os.rmdir(cur_dir)
            except OSError:
                pass
