"""
In-memory store for Settings-page operation state (rebuild index, cleanup).

Lets the frontend restore the last/current operation state after navigating
away and returning — without requiring a database write or restart persistence.

Keys are repo_id strings. State is intentionally volatile (lost on server
restart) since it only drives the UI progress panel.
"""
from __future__ import annotations

import time
from typing import Dict, Optional


_states: Dict[str, dict] = {}


def set_op_state(
    repo_id: str,
    operation: str,
    status: str,
    message: str = "",
    count: int = 0,
) -> None:
    """Record an operation's current state for a repo.

    Args:
        repo_id:   repository identifier
        operation: e.g. "rebuild_local_index", "rebuild_cloud_index",
                   "cleanup_expired", "cleanup_all"
        status:    "running" | "done" | "error"
        message:   human-readable detail (shown in the UI panel)
        count:     file/item count (0 when not applicable)
    """
    _states[repo_id] = {
        "operation": operation,
        "status": status,
        "message": message,
        "count": count,
        "updated_at": time.time(),
    }


def get_op_state(repo_id: str) -> Optional[dict]:
    """Return the last recorded state for ``repo_id``, or None."""
    return _states.get(repo_id)


def clear_op_state(repo_id: str) -> None:
    _states.pop(repo_id, None)
