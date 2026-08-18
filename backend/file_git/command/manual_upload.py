"""
Manual Upload — Step 1 (REQUIREMENTS §3.7.3, §S4).

ENCRYPTED repo:
    * Lock the repo
    * Scan the user-selected subpath
    * For each file: encrypt into ``.fgit/buffer/<encoded_path>`` and
      append an entry to ``.fgit/pending_upload.json``
    * User then drags the buffer files into the cloud APP by hand

ORIGINAL repo:
    * Just Lock. The user drags source files directly.
    * pending_upload.json still records the subpath scan so
      post_manual_upload knows what to reconcile.
"""
from __future__ import annotations

import io
import json
import os
import shutil
from dataclasses import dataclass, field
from typing import List, Optional

from ..crypto import AesGcmEncryptStream, encode_middle_path
from ..repository_manager import RepositoryManager
from ..service import IndexService, LoggerService, QueueService
from ..service.queue_service import LockError
from .context import RepoContext, build_context

PENDING_FILENAME = "pending_upload.json"


@dataclass
class ManualUploadResult:
    ok: bool
    message: str = ""
    buffer_dir: Optional[str] = None
    file_count: int = 0
    entries: List[dict] = field(default_factory=list)
    action_folder: Optional[str] = None


def command_manual_upload(
    repo_id: str,
    subpath: str = "",
) -> ManualUploadResult:
    """Prepare a manual upload batch.

    ``subpath`` is a relative path inside the repo (e.g. ``photos/2024``).
    Empty string = the whole repo. Absolute paths and paths trying to
    escape the repo root are rejected.
    """
    ctx = build_context(repo_id)

    try:
        subpath = _normalize_subpath(subpath, ctx.repo_root)
    except ValueError as exc:
        return ManualUploadResult(ok=False, message=str(exc))

    try:
        state = QueueService.acquire(ctx.repo_root, "manual_upload")
    except LockError as exc:
        return ManualUploadResult(ok=False, message=str(exc))

    action_folder = state.action_folder or ""

    try:
        RepositoryManager.update_status(ctx.repo_id, "locked")

        scan_root = os.path.join(ctx.repo_root, *subpath.split("/")) if subpath else ctx.repo_root
        if not os.path.isdir(scan_root):
            raise ValueError(f"subpath not found: {subpath!r}")

        entries: List[dict] = []
        buffer_root = os.path.join(ctx.repo_root, ".fgit", "buffer")

        # Full-repo scan restricted to the subpath. IndexService knows how
        # to skip hidden files (.fgit/, .DS_Store, etc.).
        full_scan = IndexService.scan_local_files(ctx.repo_root, key=ctx.key)
        for entry in full_scan.values():
            middle_path = entry["middle_path"]
            if subpath and not (middle_path == subpath or middle_path.startswith(subpath + "/")):
                continue

            record = {
                "middle_path": middle_path,
                "encoded_path": entry["encoded_path"],
                "size": entry["size"],
            }

            if ctx.mode == "ENCRYPTED":
                # Encrypt source → buffer/<encoded_path>
                src_full = os.path.join(ctx.repo_root, *middle_path.split("/"))
                buf_full = os.path.join(buffer_root, *entry["encoded_path"].split("/"))
                os.makedirs(os.path.dirname(buf_full), exist_ok=True)
                with open(src_full, "rb") as src, open(buf_full, "wb") as dst:
                    enc = AesGcmEncryptStream(src, ctx.key)  # type: ignore[arg-type]
                    shutil.copyfileobj(enc, dst)
                record["buffer_path"] = os.path.relpath(buf_full, ctx.repo_root)

            entries.append(record)

        # Persist pending_upload.json for post_manual_upload to consume
        pending_path = os.path.join(ctx.repo_root, ".fgit", PENDING_FILENAME)
        with open(pending_path, "w", encoding="utf-8") as f:
            json.dump({
                "subpath": subpath,
                "mode": ctx.mode,
                "entries": entries,
            }, f, indent=2, ensure_ascii=False)

        # Snapshot local_index into action folder for audit
        QueueService.snapshot_index_into_action(
            ctx.repo_root, action_folder, "local_index.json",
            IndexService.load_local_index(ctx.repo_root),
        )

        LoggerService.log_success(
            ctx.repo_root, action_folder, "MANUAL_UPLOAD_PREPARE",
            subpath or "(root)",
            f"prepared {len(entries)} files"
            + (f" in {buffer_root}" if ctx.mode == "ENCRYPTED" else ""),
        )

        if ctx.mode == "ENCRYPTED":
            msg = (
                f"Prepared {len(entries)} encrypted files in "
                f".fgit/buffer/. Drag them to the cloud APP under "
                f"{ctx.remote_root}/, then click 'Post Manual Upload'."
            )
        else:
            msg = (
                f"Ready for {len(entries)} files under {subpath or 'repo root'}. "
                f"Drag the source files to the cloud APP, then click "
                f"'Post Manual Upload'."
            )

        return ManualUploadResult(
            ok=True,
            message=msg,
            buffer_dir=(buffer_root if ctx.mode == "ENCRYPTED" else None),
            file_count=len(entries),
            entries=entries,
            action_folder=action_folder,
        )

    except Exception as exc:
        LoggerService.log_error(
            ctx.repo_root, action_folder, "MANUAL_UPLOAD_PREPARE",
            subpath or "(root)", f"aborted: {exc}",
        )
        # Release the lock — the user needs to be able to try again
        QueueService.release(ctx.repo_root)
        RepositoryManager.update_status(ctx.repo_id, "error")
        return ManualUploadResult(ok=False, message=f"Manual upload aborted: {exc}")


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def _normalize_subpath(subpath: str, repo_root: str) -> str:
    """Turn user-supplied subpath into a safe POSIX-style relative path.

    Rejects:
        * absolute paths
        * paths with ``..`` segments
        * paths that escape ``repo_root`` after normalization
    """
    if not subpath:
        return ""
    if os.path.isabs(subpath):
        raise ValueError(f"subpath must be relative to the repo: {subpath!r}")
    normalized = subpath.replace("\\", "/").strip("/")
    if not normalized:
        return ""
    if any(seg == ".." for seg in normalized.split("/")):
        raise ValueError(f"subpath must not contain '..': {subpath!r}")
    # Resolve against repo_root and verify containment
    resolved = os.path.realpath(os.path.join(repo_root, *normalized.split("/")))
    repo_real = os.path.realpath(repo_root)
    if not (resolved == repo_real or resolved.startswith(repo_real + os.sep)):
        raise ValueError(f"subpath escapes repo root: {subpath!r}")
    return normalized
