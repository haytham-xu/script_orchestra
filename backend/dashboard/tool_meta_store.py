"""Dashboard — per-tool metadata persistence.

Reads/writes the 'tool_meta' key inside the shared settings.json.
Stores user annotations for each tool: status, last_opened, comment.
"""
import os
import json
import tempfile
from typing import Any, Dict

_DIR = os.path.dirname(os.path.abspath(__file__))
_SETTINGS_FILE = os.path.join(_DIR, "settings.json")

VALID_STATUSES = {"normal", "needs_improvement", "pending_verification", "deprecated", "in_progress"}


def _load_settings() -> Dict[str, Any]:
    if not os.path.exists(_SETTINGS_FILE):
        return {}
    try:
        with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_settings(data: Dict[str, Any]) -> None:
    fd, tmp = tempfile.mkstemp(dir=_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _SETTINGS_FILE)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def load_meta() -> Dict[str, Any]:
    data = _load_settings().get("tool_meta")
    return data if isinstance(data, dict) else {}


def save_meta(meta: Dict[str, Any]) -> Dict[str, Any]:
    normalized = _normalize(meta)
    settings = _load_settings()
    settings["tool_meta"] = normalized
    _save_settings(settings)
    return normalized


def patch_tool(key: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    meta = load_meta()
    entry = dict(meta.get(key) or {})
    if "status" in patch:
        entry["status"] = patch["status"]
    if "last_opened" in patch:
        entry["last_opened"] = patch["last_opened"]
    if "comment" in patch:
        entry["comment"] = str(patch["comment"] or "")
    meta[key] = entry
    return save_meta(meta)


def _normalize(meta: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for key, val in (meta or {}).items():
        if not isinstance(val, dict):
            continue
        entry: Dict[str, Any] = {}
        status = str(val.get("status") or "").strip()
        if status in VALID_STATUSES:
            entry["status"] = status
        lo = val.get("last_opened")
        if lo:
            entry["last_opened"] = str(lo)
        comment = val.get("comment")
        if comment:
            entry["comment"] = str(comment)
        out[str(key)] = entry
    return out
