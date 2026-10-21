"""
Abandon Manual Upload — emergency unlock for stuck manual_upload state.

Called when the user wants to cancel a pending manual_upload operation,
e.g. after a backend restart left the repo locked with an empty buffer.

Steps:
    1. Verify the repo is locked by manual_upload
    2. Clear .fgit/buffer/ directory
    3. Remove pending_upload.json if it exists
    4. Release the lock and reset repo status
"""
from __future__ import annotations

import os
import shutil

from ..repository_manager import RepositoryManager
from ..service import LoggerService, QueueService
from .context import build_context
from .manual_upload import PENDING_FILENAME


def command_abandon_manual_upload(repo_id: str) -> dict:
    ctx = build_context(repo_id)
    state = QueueService.load(ctx.repo_root)

    if not state.lock:
        return {"ok": False, "message": "Repo is not locked."}
    if state.action_type != "manual_upload":
        return {
            "ok": False,
            "message": f"Repo is locked by '{state.action_type}', not manual_upload.",
        }

    action_folder = state.action_folder or ""

    # Clear buffer directory.
    buffer_root = os.path.join(ctx.repo_root, ".fgit", "buffer")
    if os.path.isdir(buffer_root):
        shutil.rmtree(buffer_root, ignore_errors=True)

    # Remove pending_upload.json.
    pending_path = os.path.join(ctx.repo_root, ".fgit", PENDING_FILENAME)
    if os.path.isfile(pending_path):
        try:
            os.remove(pending_path)
        except OSError:
            pass

    QueueService.release(ctx.repo_root)
    RepositoryManager.update_status(ctx.repo_id, "ready")

    LoggerService.log_error(
        ctx.repo_root, action_folder, "MANUAL_UPLOAD_PREPARE",
        "-", "abandoned by user",
    )

    return {"ok": True, "message": "Manual upload abandoned. Repo unlocked."}
