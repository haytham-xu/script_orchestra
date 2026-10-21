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
from ..settings_op_store import set_op_state
from ..websocket_service import emit_progress
from .context import build_context


@dataclass
class RebuildLocalIndexResult:
    ok: bool
    message: str = ""
    count: int = 0


def command_rebuild_local_index(repo_id: str) -> RebuildLocalIndexResult:
    ctx = build_context(repo_id)
    set_op_state(repo_id, "rebuild_local_index", "running", "Scanning local files...", 0)
    try:
        emit_progress(ctx.repo_id, "rebuild_local_index", "scan", 0, 1, "Scanning local files...")
        index = IndexService.scan_local_files(ctx.repo_root, key=ctx.key)
        IndexService.save_local_index(ctx.repo_root, index)
        n = len(index)
        emit_progress(ctx.repo_id, "rebuild_local_index", "scan", n, n, f"DONE {n} files")
        msg = f"Scanned {n} local files"
        set_op_state(repo_id, "rebuild_local_index", "done", msg, n)
        return RebuildLocalIndexResult(ok=True, message=msg, count=n)
    except Exception as exc:
        set_op_state(repo_id, "rebuild_local_index", "error", str(exc), 0)
        raise
