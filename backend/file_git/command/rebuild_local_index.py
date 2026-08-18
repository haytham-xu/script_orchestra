"""
Rebuild local_index command (REQUIREMENTS §3.7, §3.13, §S9).

Independently triggered by the user (or by push automatically).
Scans the local file tree from scratch and overwrites
``.fgit/local_index.json``.

No lock is acquired — this is a purely local, additive operation
that overwrites a single file the user owns.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..service import IndexService
from .context import build_context


@dataclass
class RebuildLocalIndexResult:
    ok: bool
    message: str = ""
    count: int = 0


def command_rebuild_local_index(repo_id: str) -> RebuildLocalIndexResult:
    ctx = build_context(repo_id)
    index = IndexService.scan_local_files(ctx.repo_root, key=ctx.key)
    IndexService.save_local_index(ctx.repo_root, index)
    return RebuildLocalIndexResult(
        ok=True,
        message=f"Scanned {len(index)} local files",
        count=len(index),
    )
