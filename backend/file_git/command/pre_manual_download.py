"""
Pre Manual Download — Step 1 (REQUIREMENTS §3.7.5, §S5).

Acquires the lock and downloads the remote cloud_index so that
post_manual_download can map encoded_path → middle_path for decryption.
User then downloads files from the cloud APP:
    * ENCRYPTED: into ``.fgit/buffer/`` preserving the encoded structure
    * ORIGINAL:  directly into the repo at the correct middle_path
"""
from __future__ import annotations

import io
import os
from dataclasses import dataclass
from typing import Optional

from ..repository_manager import RepositoryManager
from ..service import IndexService, LoggerService, QueueService
from ..service.queue_service import LockError
from .context import build_context


@dataclass
class PreManualDownloadResult:
    ok: bool
    message: str = ""
    buffer_dir: Optional[str] = None
    action_folder: Optional[str] = None


def command_pre_manual_download(repo_id: str) -> PreManualDownloadResult:
    ctx = build_context(repo_id)

    try:
        state = QueueService.acquire(ctx.repo_root, "manual_download")
    except LockError as exc:
        return PreManualDownloadResult(ok=False, message=str(exc))

    action_folder = state.action_folder or ""
    buffer_root = os.path.join(ctx.repo_root, ".fgit", "buffer")

    RepositoryManager.update_status(ctx.repo_id, "locked")

    # Download cloud_index from remote so post_manual_download can resolve
    # encoded_path → middle_path (ENCRYPTED) or know what files exist (ORIGINAL).
    remote_ci_path = ctx.cloud_index_remote_path()
    if ctx.storage.exists(remote_ci_path):
        buf = io.BytesIO()
        ctx.storage.download(remote_ci_path, buf)
        cloud_index = IndexService.deserialize_cloud_index_after_download(
            buf.getvalue(), key=ctx.key,
        )
        IndexService.save_cloud_index(ctx.repo_root, cloud_index)

    LoggerService.log_success(
        ctx.repo_root, action_folder, "MANUAL_DOWNLOAD_PREPARE",
        "-", f"lock acquired for repo mode={ctx.mode}",
    )

    if ctx.mode == "ENCRYPTED":
        msg = (
            f"Ready. Download the encrypted files from the cloud APP into "
            f".fgit/buffer/ preserving the encoded directory structure. "
            f"Then click 'Post Manual Download'."
        )
        buffer_dir = buffer_root
    else:
        msg = (
            "Ready. Download the files from the cloud APP directly into "
            "the repo at their original paths. Then click 'Post Manual "
            "Download'."
        )
        buffer_dir = None

    return PreManualDownloadResult(
        ok=True,
        message=msg,
        buffer_dir=buffer_dir,
        action_folder=action_folder,
    )
