"""Dashboard — per-tool metadata persistence (JSON on disk).

Stores user annotations for each tool: status, last_opened, comment.
Keyed by tool key (e.g. 'caffeinate').  Unknown keys are kept as-is so
metadata survives tool renames in the frontend.
"""
import os
import json
import tempfile
from typing import Any, Dict

_DIR = os.path.dirname(os.path.abspath(__file__))
_META_FILE = os.path.join(_DIR, "tool_meta.json")

VALID_STATUSES = {"normal", "needs_improvement", "pending_verification", "deprecated"}


def load_meta() -> Dict[str, Any]:
    if not os.path.exists(_META_FILE):
        return {}
    try:
        with open(_META_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return data
    except Exception as exc:
        print(f"[dashboard] failed to read tool_meta.json ({exc}); using empty meta")
        return {}


def save_meta(meta: Dict[str, Any]) -> Dict[str, Any]:
    normalized = _normalize(meta)
    fd, tmp = tempfile.mkstemp(dir=_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(normalized, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _META_FILE)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
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
