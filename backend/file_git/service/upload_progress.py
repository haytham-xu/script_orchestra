"""Thread-safe in-memory tracker for the file currently being processed."""
from __future__ import annotations

import threading
from typing import Optional

_lock = threading.Lock()
_state: dict[str, dict] = {}


def set_current(repo_root: str, key: str, path: str, action: str, bytes_total: int) -> None:
    with _lock:
        _state[repo_root] = {
            "key": key,
            "path": path,
            "action": action,
            "bytes_done": 0,
            "bytes_total": bytes_total,
            "phase": "uploading",
        }


def set_phase(repo_root: str, phase: str) -> None:
    with _lock:
        s = _state.get(repo_root)
        if s:
            s["phase"] = phase


def update_bytes(repo_root: str, delta: int) -> None:
    with _lock:
        s = _state.get(repo_root)
        if s:
            s["bytes_done"] = min(s["bytes_done"] + delta, s["bytes_total"])


def clear(repo_root: str) -> None:
    with _lock:
        _state.pop(repo_root, None)


def get(repo_root: str) -> Optional[dict]:
    with _lock:
        s = _state.get(repo_root)
        return dict(s) if s else None
