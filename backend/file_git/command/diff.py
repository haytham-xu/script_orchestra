"""
Diff command (REQUIREMENTS §3.7, §3.13, §S7).

Read-only view of what would happen on the next push:
    * scan local files (does NOT persist to local_index.json)
    * compare against the local cloud_index mirror
    * return a structured diff for the UI to render

No lock, no side effects — safe to invoke while another operation
holds the lock (e.g. during a manual upload window).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ..service import IndexService
from .context import build_context


@dataclass
class DiffCommandResult:
    ok: bool
    message: str = ""
    added: List[dict] = field(default_factory=list)       # local only
    modified: List[dict] = field(default_factory=list)    # both, size differs
    deleted: List[dict] = field(default_factory=list)     # cloud only
    total_local: int = 0
    total_cloud: int = 0


def command_diff(repo_id: str) -> DiffCommandResult:
    ctx = build_context(repo_id)

    # Scan local, compare against the current local mirror of cloud_index
    local_index = IndexService.scan_local_files(ctx.repo_root, key=ctx.key)
    cloud_index = IndexService.load_cloud_index(ctx.repo_root)
    diff = IndexService.diff(local_index, cloud_index)

    return DiffCommandResult(
        ok=True,
        message=(
            f"Local={len(local_index)}, cloud={len(cloud_index)}: "
            f"{len(diff.added)} added, "
            f"{len(diff.modified)} modified, "
            f"{len(diff.deleted)} deleted"
        ),
        added=[_shrink(e) for e in diff.added],
        modified=[_shrink(e) for e in diff.modified],
        deleted=[_shrink(e) for e in diff.deleted],
        total_local=len(local_index),
        total_cloud=len(cloud_index),
    )


def _shrink(entry: dict) -> dict:
    """Return a UI-friendly subset (drop encoded_path from responses to
    keep payloads compact — the UI shows middle_path + size)."""
    return {
        "middle_path": entry.get("middle_path", ""),
        "size": entry.get("size", 0),
    }
