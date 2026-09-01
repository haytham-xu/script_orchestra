"""Command bridge between the web UI and the Chrome extension.

Web UI → REST endpoint on this backend → enqueue a command → extension polls
`/browser-agent/agent/commands`, executes it in Chrome, POSTs the result to
`/browser-agent/agent/results/<id>`. The original UI request unblocks and
returns the result. All state lives in-process; no persistence — a restart
drops in-flight requests (which is fine; the UI just retries).
"""

import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple


_lock = threading.Lock()
_pending_commands: List[Dict[str, Any]] = []
_awaiting_results: Dict[str, Dict[str, Any]] = {}
_last_extension_seen_at: float = 0.0


def enqueue_and_wait(cmd_type: str, params: Optional[dict] = None,
                    timeout: float = 15.0) -> Tuple[Optional[Any], Optional[str]]:
    """Enqueue a command for the extension, block until result or timeout.

    Returns (result, error). error is None on success.
    """
    cmd_id = str(uuid.uuid4())
    event = threading.Event()
    entry = {"event": event, "result": None, "error": None}
    with _lock:
        _pending_commands.append({"id": cmd_id, "type": cmd_type,
                                  "params": params or {}})
        _awaiting_results[cmd_id] = entry
    ok = event.wait(timeout)
    with _lock:
        _awaiting_results.pop(cmd_id, None)
        # Also drop the queued command if it hasn't been fetched yet, so a
        # timed-out request doesn't get executed by a later poll and leak.
        for i, c in enumerate(_pending_commands):
            if c["id"] == cmd_id:
                del _pending_commands[i]
                break
    if not ok:
        if _last_extension_seen_at == 0:
            return None, "extension never connected — is it installed and enabled?"
        idle = time.time() - _last_extension_seen_at
        if idle > 10:
            return None, f"extension idle for {int(idle)}s — its service worker may be asleep"
        return None, "timeout waiting for extension"
    if entry["error"]:
        return None, entry["error"]
    return entry["result"], None


def drain_pending() -> List[Dict[str, Any]]:
    global _last_extension_seen_at
    with _lock:
        _last_extension_seen_at = time.time()
        out = list(_pending_commands)
        _pending_commands.clear()
    return out


def submit_result(cmd_id: str, result: Any = None, error: Optional[str] = None) -> bool:
    with _lock:
        entry = _awaiting_results.get(cmd_id)
        if entry is None:
            return False
        entry["result"] = result
        entry["error"] = error
        entry["event"].set()
    return True


def extension_status() -> Dict[str, Any]:
    with _lock:
        return {
            "last_seen_at": _last_extension_seen_at,
            "seconds_since_seen": (time.time() - _last_extension_seen_at) if _last_extension_seen_at else None,
            "pending_commands": len(_pending_commands),
        }
