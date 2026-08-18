"""
Post Manual Download — Step 4 (REQUIREMENTS §3.7.6, §S5).

Called after the user finishes downloading files from the cloud APP.

Flow (ENCRYPTED):
    1. Verify locked by prior manual_download
    2. Walk .fgit/buffer/ → each file is ciphertext at encoded_path
    3. For each: look up middle_path via cloud_index → decrypt to
       repo/<middle_path> → remove buffer file
    4. Rebuild local_index
    5. Fetch cloud listing, update cloud_index (+ upload it)
    6. Archive + release lock

Flow (ORIGINAL):
    1. Verify locked by prior manual_download
    2. Rebuild local_index (files already at final positions)
    3. Fetch cloud listing, update cloud_index (+ upload it)
    4. Archive + release lock
"""
from __future__ import annotations

import io
import os
import shutil
from dataclasses import dataclass, field
from typing import List, Optional

from ..crypto import AesGcmDecryptStream
from ..repository_manager import RepositoryManager
from ..service import IndexService, LoggerService, QueueService
from .context import RepoContext, build_context


@dataclass
class PostManualDownloadResult:
    ok: bool
    message: str = ""
    decrypted: int = 0
    unmapped: List[str] = field(default_factory=list)
    action_folder: Optional[str] = None


def command_post_manual_download(repo_id: str) -> PostManualDownloadResult:
    ctx = build_context(repo_id)

    state = QueueService.load(ctx.repo_root)
    if not state.lock or state.action_type != "manual_download":
        return PostManualDownloadResult(
            ok=False,
            message="No manual download in progress. Trigger 'Pre Manual "
                    "Download' first.",
        )
    action_folder = state.action_folder or ""

    try:
        decrypted_count = 0
        unmapped: List[str] = []

        if ctx.mode == "ENCRYPTED":
            decrypted_count, unmapped = _decrypt_buffer_to_local(ctx, action_folder)

        # Step 4: rebuild local_index
        local_index = IndexService.scan_local_files(ctx.repo_root, key=ctx.key)
        IndexService.save_local_index(ctx.repo_root, local_index)
        QueueService.snapshot_index_into_action(
            ctx.repo_root, action_folder, "local_index.json", local_index,
        )

        # Step 5: refresh cloud_index by scanning the cloud
        # (REQUIREMENTS §3.7.6: 拉远端对应路径 API 列表 → 更新 cloud_index)
        # Since Manual Download doesn't have a subpath scope, we do a
        # full scan under remote_root. This is the same cost as
        # rebuild_cloud_index; users invoke it only after they finished
        # a manual batch, so the frequency is low.
        cloud_index = _rebuild_cloud_index_from_scan(ctx)
        IndexService.save_cloud_index(ctx.repo_root, cloud_index)
        QueueService.snapshot_index_into_action(
            ctx.repo_root, action_folder, "cloud_index.json", cloud_index,
        )
        _upload_cloud_index(ctx, cloud_index)

        # Step 6: archive + unlock
        QueueService.release(ctx.repo_root)
        RepositoryManager.update_status(ctx.repo_id, "ready")
        RepositoryManager.update_last_updated(ctx.repo_id)

        LoggerService.log_success(
            ctx.repo_root, action_folder, "MANUAL_DOWNLOAD_CONFIRM",
            "-",
            f"decrypted {decrypted_count} files, local_index={len(local_index)}, "
            f"cloud_index={len(cloud_index)}, unmapped={len(unmapped)}",
        )

        if ctx.mode == "ENCRYPTED":
            msg = (
                f"Manual download confirmed: {decrypted_count} files decrypted"
            )
        else:
            msg = (
                f"Manual download confirmed: {len(local_index)} local files, "
                f"{len(cloud_index)} cloud files"
            )
        if unmapped:
            msg += f", {len(unmapped)} unmapped (see error.log)"

        return PostManualDownloadResult(
            ok=len(unmapped) == 0,
            message=msg,
            decrypted=decrypted_count,
            unmapped=unmapped,
            action_folder=action_folder,
        )

    except Exception as exc:
        LoggerService.log_error(
            ctx.repo_root, action_folder, "MANUAL_DOWNLOAD_CONFIRM", "-",
            f"aborted: {exc}",
        )
        RepositoryManager.update_status(ctx.repo_id, "error")
        return PostManualDownloadResult(
            ok=False,
            message=f"Post manual download aborted: {exc}",
            action_folder=action_folder,
        )


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def _decrypt_buffer_to_local(ctx: RepoContext, action_folder: str) -> tuple:
    """Walk .fgit/buffer/, decrypt each ciphertext file to its middle_path.

    Returns (decrypted_count, list_of_unmapped_encoded_paths).
    """
    buffer_root = os.path.join(ctx.repo_root, ".fgit", "buffer")
    if not os.path.isdir(buffer_root):
        return 0, []

    cloud_index = IndexService.load_cloud_index(ctx.repo_root)
    # Build reverse mapping: encoded_path → middle_path
    reverse = {v["encoded_path"]: v["middle_path"] for v in cloud_index.values()}

    decrypted = 0
    unmapped: List[str] = []

    for cur_dir, _dirs, files in os.walk(buffer_root):
        for fname in files:
            buf_full = os.path.join(cur_dir, fname)
            encoded_rel = os.path.relpath(buf_full, buffer_root).replace("\\", "/")

            middle_path = reverse.get(encoded_rel)
            if middle_path is None:
                unmapped.append(encoded_rel)
                LoggerService.log_error(
                    ctx.repo_root, action_folder, "MANUAL_DOWNLOAD_DECRYPT",
                    encoded_rel,
                    "no cloud_index entry maps this encoded_path — cannot "
                    "recover original filename",
                )
                continue

            target = os.path.join(ctx.repo_root, *middle_path.split("/"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(buf_full, "rb") as src, open(target, "wb") as dst:
                dec = AesGcmDecryptStream(src, ctx.key)  # type: ignore[arg-type]
                shutil.copyfileobj(dec, dst)
            os.remove(buf_full)
            decrypted += 1

    # Prune empty buffer subdirs
    for cur_dir, _dirs, _files in os.walk(buffer_root, topdown=False):
        if cur_dir == buffer_root:
            continue
        try:
            os.rmdir(cur_dir)
        except OSError:
            pass

    return decrypted, unmapped


def _rebuild_cloud_index_from_scan(ctx: RepoContext) -> dict:
    """Walk the cloud remote_root and rebuild a fresh cloud_index.

    ENCRYPTED repos: each file has an opaque encoded_path; the
    middle_path is recovered from the old cloud_index if present, or
    left as "UNKNOWN_<hash>" for user to manually resolve.
    """
    import hashlib

    old_index = IndexService.load_cloud_index(ctx.repo_root)
    reverse = {v["encoded_path"]: v["middle_path"] for v in old_index.values()}

    new_index: dict = {}
    for meta in ctx.storage.list_files(ctx.remote_root):
        remote_path = meta["remote_path"]
        # Strip remote_root prefix + optional leading /
        relative = remote_path[len(ctx.remote_root):].lstrip("/")
        if not relative or relative == "cloud_index.json":
            continue

        if ctx.mode == "ENCRYPTED":
            middle_path = reverse.get(relative)
            if middle_path is None:
                middle_path = f"UNKNOWN_{hashlib.md5(relative.encode()).hexdigest()[:8]}"
        else:
            middle_path = relative

        encoded_path = relative
        key = hashlib.md5(middle_path.encode("utf-8")).hexdigest()
        new_index[key] = {
            "middle_path": middle_path,
            "encoded_path": encoded_path,
            "size": meta["size"],
        }

    return new_index


def _upload_cloud_index(ctx: RepoContext, cloud_index: dict) -> None:
    payload = IndexService.serialize_cloud_index_for_upload(cloud_index, key=ctx.key)
    ctx.storage.upload(io.BytesIO(payload), ctx.cloud_index_remote_path(), len(payload))
