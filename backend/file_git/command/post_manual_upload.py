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
        remote_scan_prefix = _cloud_prefix(ctx, subpath)
        cloud_listing = {
            m["remote_path"]: m for m in ctx.storage.list_files(remote_scan_prefix)
        }

        # Step 3: match pending entries against actual cloud state
        confirmed_entries: List[dict] = []
        missing: List[str] = []
        for entry in entries:
            expected_remote = _remote_full_for(ctx, entry["encoded_path"])
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

        # Step 4: upload cloud_index.json
        _upload_cloud_index(ctx, new_cloud_index)

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
    """Replace the subtree under ``subpath`` in the cloud_index with the
    just-confirmed entries.

    Entries outside the subpath are left untouched (they weren't part of
    this manual upload).
    """
    import hashlib

    def _in_subpath(mp: str) -> bool:
        if not subpath:
            return True
        return mp == subpath or mp.startswith(subpath + "/")

    new_index = {
        k: v for k, v in current.items()
        if not _in_subpath(v["middle_path"])
    }
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
