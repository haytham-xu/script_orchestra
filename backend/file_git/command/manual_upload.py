"""
Manual Upload — Step 1 (REQUIREMENTS §3.7.3, §S4).

ENCRYPTED repo:
    * Lock the repo
    * Scan the user-selected subpath
    * For each missing subdir batch: encrypt into ``.fgit/buffer/<encoded_path>`` and
      append an entry to ``.fgit/pending_upload.json``
    * User then drags the buffer files into the cloud APP by hand

ORIGINAL repo:
    * Just Lock. The user drags source files directly.
    * pending_upload.json still records the subpath scan so
      post_manual_upload knows what to reconcile.

Scan granularity: files are grouped by their first-level subdirectory under
``subpath``. A group is skipped entirely if ANY of its files already exist on
the cloud (fill-gaps mode). Files sitting directly in ``subpath`` (not
inside any subfolder) are excluded — only subfolder-grouped batches are produced.

Examples:
  subpath = "photos"   → batch keys: "photos/2024", "photos/2025", ...
  subpath = "" (root)  → batch keys: "photos", "docs", "music", ...
"""
from __future__ import annotations

import io
import json
import os
import shutil
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..crypto import AesGcmEncryptStream, encode_middle_path
from ..repository_manager import RepositoryManager
from ..service import IndexService, LoggerService, QueueService
from ..service.queue_service import LockError
from ..websocket_service import emit_progress
from .context import build_context

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
    """Prepare a manual upload batch (fill-gaps mode).

    ``subpath`` is a relative path inside the repo (e.g. ``photos/2024``).
    Empty string or "/" = the whole repo root. Absolute paths and paths
    trying to escape the repo root are rejected.

    Files are grouped by their immediate subdirectory under ``subpath``.
    A group is skipped if any of its files already exist on the cloud.
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

        # Scan all local files and group by first-level subdir under subpath.
        full_scan = IndexService.scan_local_files(ctx.repo_root, key=ctx.key)
        batch_groups: Dict[str, List[dict]] = {}
        for entry in full_scan.values():
            bkey = _batch_key(entry["middle_path"], subpath)
            if bkey is not None:
                batch_groups.setdefault(bkey, []).append(entry)

        # Use cloud_index to identify which batches are already uploaded.
        # The cloud_index is updated by post_manual_upload/push/pull, so it
        # reliably reflects what has been confirmed on cloud without requiring
        # a live Baidu listing (which can time-out or be rate-limited for large
        # directories, and silently returns an empty set on failure).
        cloud_index = IndexService.load_cloud_index(ctx.repo_root)
        cloud_encoded_paths: set = {
            entry.get("encoded_path", "")
            for entry in cloud_index.values()
            if entry.get("encoded_path")
        }

        # Skip a batch if ANY of its files are already in the cloud_index.
        to_upload: List[dict] = []
        skipped_dirs = 0
        for bkey in sorted(batch_groups):
            batch_entries = batch_groups[bkey]
            on_cloud = any(
                e["encoded_path"] in cloud_encoded_paths
                for e in batch_entries
            )
            if on_cloud:
                skipped_dirs += 1
            else:
                to_upload.extend(batch_entries)

        total = len(to_upload)

        for i, entry in enumerate(to_upload):
            middle_path = entry["middle_path"]
            record = {
                "middle_path": middle_path,
                "encoded_path": entry["encoded_path"],
                "size": entry["size"],
            }

            if ctx.mode == "ENCRYPTED":
                src_full = os.path.join(ctx.repo_root, *middle_path.split("/"))
                buf_full = os.path.join(buffer_root, *entry["encoded_path"].split("/"))
                os.makedirs(os.path.dirname(buf_full), exist_ok=True)
                with open(src_full, "rb") as src, open(buf_full, "wb") as dst:
                    enc = AesGcmEncryptStream(src, ctx.key)  # type: ignore[arg-type]
                    shutil.copyfileobj(enc, dst)
                record["buffer_path"] = os.path.relpath(buf_full, ctx.repo_root).replace("\\", "/")

            entries.append(record)
            emit_progress(ctx.repo_id, "manual_upload", "queue", i + 1, total, f"ENCRYPT {middle_path}")

        # Persist pending_upload.json for post_manual_upload to consume.
        pending_path = os.path.join(ctx.repo_root, ".fgit", PENDING_FILENAME)
        with open(pending_path, "w", encoding="utf-8") as f:
            json.dump({
                "subpath": subpath,
                "mode": ctx.mode,
                "entries": entries,
            }, f, indent=2, ensure_ascii=False)

        # Snapshot local_index into action folder for audit.
        QueueService.snapshot_index_into_action(
            ctx.repo_root, action_folder, "local_index.json",
            IndexService.load_local_index(ctx.repo_root),
        )

        total_dirs = len(batch_groups)
        upload_dirs = total_dirs - skipped_dirs
        skip_note = f" ({skipped_dirs} dirs already on cloud, skipped)" if skipped_dirs else ""
        LoggerService.log_success(
            ctx.repo_root, action_folder, "MANUAL_UPLOAD_PREPARE",
            subpath or "(root)",
            f"prepared {len(entries)} files from {upload_dirs} dirs"
            + (f" in {buffer_root}" if ctx.mode == "ENCRYPTED" else ""),
        )

        if ctx.mode == "ENCRYPTED":
            msg = (
                f"Prepared {len(entries)} encrypted files from {upload_dirs} dirs{skip_note}. "
                f"Drag them to the cloud APP under {ctx.remote_root}/, then click 'Confirm'."
            )
        else:
            msg = (
                f"Ready for {len(entries)} files from {upload_dirs} dirs{skip_note}. "
                f"Drag the source files to the cloud APP, then click 'Confirm'."
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
        QueueService.release(ctx.repo_root)
        RepositoryManager.update_status(ctx.repo_id, "error")
        return ManualUploadResult(ok=False, message=f"Manual upload aborted: {exc}")


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def _batch_key(middle_path: str, subpath: str) -> Optional[str]:
    """Return the first-level subdir of middle_path under subpath.

    Files sitting directly in subpath (no subfolder) return None and are
    excluded from the batch — only subfolder groups are produced.
    """
    if subpath:
        prefix = subpath.rstrip("/") + "/"
        if not middle_path.startswith(prefix):
            return None
        rest = middle_path[len(prefix):]
    else:
        rest = middle_path

    if "/" not in rest:
        return None  # file directly in subpath, not in any subdir

    first_seg = rest.split("/")[0]
    return f"{subpath}/{first_seg}" if subpath else first_seg


def _normalize_subpath(subpath: str, repo_root: str) -> str:
    """Turn user-supplied subpath into a safe POSIX-style relative path.

    Accepts "/" or empty as root. Rejects absolute paths (other than bare "/"),
    paths with ``..`` segments, and paths that escape ``repo_root``.
    """
    if not subpath:
        return ""
    # Normalise slashes and strip leading/trailing separators first.
    # A bare "/" (or "\\") after stripping becomes "" → root.
    normalized = subpath.replace("\\", "/").strip("/")
    if not normalized:
        return ""
    if os.path.isabs(normalized):
        raise ValueError(f"subpath must be relative to the repo: {subpath!r}")
    if any(seg == ".." for seg in normalized.split("/")):
        raise ValueError(f"subpath must not contain '..': {subpath!r}")
    resolved = os.path.realpath(os.path.join(repo_root, *normalized.split("/")))
    repo_real = os.path.realpath(repo_root)
    if not (resolved == repo_real or resolved.startswith(repo_real + os.sep)):
        raise ValueError(f"subpath escapes repo root: {subpath!r}")
    return normalized
