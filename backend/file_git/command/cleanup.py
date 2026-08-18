"""
Cleanup command (REQUIREMENTS §3.7, §3.12, §3.13).

Manually clear ``.fgit/trash/`` and ``.fgit/action/`` folders.

Two modes:
    * ``dry_run=True``   → report what *would* be deleted, don't touch disk
    * ``dry_run=False``  → really delete

Two scopes:
    * ``mode='expired'`` → only date folders older than
      ``config.hook_retention_days`` (default 7)
    * ``mode='all'``     → wipe everything under trash/ and action/

Unlike the automatic hook that runs before push/pull, this command is
user-driven and can be invoked at any time (even while the repo is
locked — it never touches queue.json or buffer).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List

from ..service import LoggerService, TrashService
from .context import build_context


CleanupMode = str  # "expired" | "all"


@dataclass
class CleanupResult:
    ok: bool
    message: str = ""
    trash_removed: int = 0
    action_removed: int = 0
    trash_candidates: List[str] = field(default_factory=list)
    action_candidates: List[str] = field(default_factory=list)


def command_cleanup(
    repo_id: str,
    mode: CleanupMode = "expired",
    dry_run: bool = False,
) -> CleanupResult:
    if mode not in ("expired", "all"):
        raise ValueError(f"mode must be 'expired' or 'all', got {mode!r}")

    ctx = build_context(repo_id)
    retention = int(ctx.config.get("hook_retention_days", 7))

    trash_root = os.path.join(ctx.repo_root, ".fgit", "trash")
    action_root = os.path.join(ctx.repo_root, ".fgit", "action")

    trash_candidates = _list_candidates(trash_root, retention, mode, kind="trash")
    action_candidates = _list_candidates(action_root, retention, mode, kind="action")

    if dry_run:
        return CleanupResult(
            ok=True,
            message=(
                f"[dry-run] Would remove {len(trash_candidates)} trash folders "
                f"and {len(action_candidates)} action folders "
                f"({mode}, retention={retention}d)"
            ),
            trash_candidates=trash_candidates,
            action_candidates=action_candidates,
        )

    # Real removal — reuse existing helpers so semantics stay identical
    # to the automatic hook.
    if mode == "all":
        trash_removed = TrashService.cleanup_all(ctx.repo_root)
        action_removed = LoggerService.cleanup_all_actions(ctx.repo_root)
    else:
        trash_removed = TrashService.cleanup_old(ctx.repo_root, retention)
        action_removed = LoggerService.cleanup_old_actions(ctx.repo_root, retention)

    return CleanupResult(
        ok=True,
        message=(
            f"Cleanup complete: removed {trash_removed} trash folders "
            f"and {action_removed} action folders ({mode}, retention={retention}d)"
        ),
        trash_removed=trash_removed,
        action_removed=action_removed,
    )


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def _list_candidates(
    root: str,
    retention_days: int,
    mode: str,
    *,
    kind: str,
) -> List[str]:
    if not os.path.isdir(root):
        return []
    if mode == "all":
        return [d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))]

    cutoff = datetime.now() - timedelta(days=retention_days)
    out: List[str] = []
    for entry in os.listdir(root):
        entry_path = os.path.join(root, entry)
        if not os.path.isdir(entry_path):
            continue
        try:
            if kind == "trash":
                stamp = entry
                folder_date = datetime.strptime(stamp, "%Y%m%d")
            else:  # action folder: yyyymmdd_hhmm_<type>[_N]
                stamp = "_".join(entry.split("_")[:2])
                folder_date = datetime.strptime(stamp, "%Y%m%d_%H%M")
        except ValueError:
            continue
        if folder_date < cutoff:
            out.append(entry)
    return out
