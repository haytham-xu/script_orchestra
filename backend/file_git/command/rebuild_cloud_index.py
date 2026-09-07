"""
Rebuild cloud_index command (REQUIREMENTS §3.7, §3.13, §S8).

Full traversal of the cloud remote_root via ``storage.list_files``.
This is the "authoritative-source" refresh — invoked when the user
knows manual changes happened on cloud that ``cloud_index.json``
doesn't reflect.

Because it hits the cloud API for every file, it can be expensive.
The UI is expected to invoke ``estimate_rebuild_cloud_index`` first
and prompt the user for confirmation.

Steps:
    1. Traverse cloud remote_root
    2. For each file:
        * ORIGINAL: middle_path = remote path relative to remote_root
        * ENCRYPTED: middle_path recovered from prior cloud_index if
          possible, otherwise stored as ``UNKNOWN_<hash>`` for later
          manual reconciliation
    3. Skip the ``cloud_index.json`` blob itself
    4. Save the new cloud_index locally AND upload it (encrypted if
       ENCRYPTED repo)
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass, field
from typing import List

from ..service import IndexService
from .context import RepoContext, build_context


@dataclass
class RebuildEstimate:
    ok: bool
    remote_root: str
    approximate_file_count: int
    message: str = ""


@dataclass
class RebuildCloudIndexResult:
    ok: bool
    message: str = ""
    count: int = 0
    unknown: List[str] = field(default_factory=list)


def estimate_rebuild_cloud_index(repo_id: str) -> RebuildEstimate:
    """List cloud files to give the UI a count for a confirmation prompt.

    This itself counts against API quota, so it's still a real
    traversal. In practice a "quick" list_files vs a "full" rebuild
    have similar cost — the value here is user visibility before
    committing to the disruptive `POST` action.
    """
    ctx = build_context(repo_id)
    count = 0
    for _ in ctx.storage.list_files(ctx.remote_root):
        count += 1
    return RebuildEstimate(
        ok=True,
        remote_root=ctx.remote_root,
        approximate_file_count=count,
        message=(
            f"Rebuilding cloud_index will traverse {count} entries under "
            f"{ctx.remote_root}. This calls the cloud API {count} times."
        ),
    )


def command_rebuild_cloud_index(repo_id: str) -> RebuildCloudIndexResult:
    ctx = build_context(repo_id)

    old_index = IndexService.load_cloud_index(ctx.repo_root)
    reverse = {v["encoded_path"]: v["middle_path"] for v in old_index.values()}

    new_index: dict = {}
    unknown: List[str] = []

    for meta in ctx.storage.list_files(ctx.remote_root):
        remote_path = meta["remote_path"]
        # Strip remote_root prefix + optional leading / (normalize both sides
        # to avoid mismatches when storage returns paths with a leading "/" but
        # ctx.remote_root was stored without one).
        # Use to_listing_key so root_prefix-stripping backends (Baidu) are
        # handled the same way as the listing output.
        norm_path = remote_path.lstrip("/")
        norm_root = ctx.storage.to_listing_key(ctx.remote_root).rstrip("/")
        relative = norm_path[len(norm_root):].lstrip("/") if norm_root and norm_path.startswith(norm_root) else norm_path
        if not relative or relative.startswith(".fgit/"):
            continue

        encoded_path = relative

        if ctx.mode == "ENCRYPTED":
            middle_path = reverse.get(relative)
            if middle_path is None:
                middle_path = f"UNKNOWN_{hashlib.md5(relative.encode()).hexdigest()[:8]}"
                unknown.append(relative)
            # Use the plaintext size from old_index if available; the cloud
            # stores ciphertext so meta["size"] would be the encrypted size,
            # not the plaintext size we compare against local_index.
            old_entry = old_index.get(hashlib.md5(middle_path.encode("utf-8")).hexdigest())
            size = old_entry["size"] if old_entry else meta["size"]
        else:
            middle_path = relative
            size = meta["size"]

        key = hashlib.md5(middle_path.encode("utf-8")).hexdigest()
        new_index[key] = {
            "middle_path": middle_path,
            "encoded_path": encoded_path,
            "size": size,
        }

    # Save + upload
    IndexService.save_cloud_index(ctx.repo_root, new_index)
    _upload_cloud_index(ctx, new_index)

    msg = f"Rebuilt cloud_index with {len(new_index)} entries"
    if unknown:
        msg += f", {len(unknown)} unmapped (see UNKNOWN_* middle_paths)"

    return RebuildCloudIndexResult(
        ok=True,
        message=msg,
        count=len(new_index),
        unknown=unknown,
    )


def _upload_cloud_index(ctx: RepoContext, cloud_index: dict) -> None:
    payload = IndexService.serialize_cloud_index_for_upload(cloud_index, key=ctx.key)
    ctx.storage.upload(io.BytesIO(payload), ctx.cloud_index_remote_path(), len(payload))
    IndexService.touch_cloud_index_synced_at(ctx.repo_root)
