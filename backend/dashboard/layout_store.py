"""Dashboard — layout persistence (JSON on disk).

Stores the user's Launchpad layout: ordered items where each is either a tool
(referenced by its code-defined key) or a folder grouping several tool keys.
This layer is pure storage — it does NOT know the set of valid tool keys; the
frontend reconciles the layout against the code-defined tool list at render
time (appends new tools, ignores removed keys).
"""
import os
import json
import tempfile
from typing import Any, Dict

_DIR = os.path.dirname(os.path.abspath(__file__))
_LAYOUT_FILE = os.path.join(_DIR, "layout.json")

_EMPTY: Dict[str, Any] = {"items": []}


def load_layout() -> Dict[str, Any]:
    if not os.path.exists(_LAYOUT_FILE):
        return dict(_EMPTY)
    try:
        with open(_LAYOUT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            return dict(_EMPTY)
        return data
    except Exception as exc:  # corrupt file → don't crash, return empty
        print(f"[dashboard] failed to read layout.json ({exc}); using empty layout")
        return dict(_EMPTY)


def save_layout(layout: Dict[str, Any]) -> Dict[str, Any]:
    normalized = _normalize(layout)
    # Atomic write: temp file + replace, so a crash mid-write can't corrupt it.
    fd, tmp = tempfile.mkstemp(dir=_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(normalized, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _LAYOUT_FILE)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return normalized


def _normalize(layout: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only well-formed items. tool needs key; folder needs id/name/keys[]."""
    items = []
    raw_items = (layout or {}).get("items")
    if not isinstance(raw_items, list):
        return dict(_EMPTY)
    for it in raw_items:
        if not isinstance(it, dict):
            continue
        t = it.get("type")
        if t == "tool":
            key = str(it.get("key") or "").strip()
            if key:
                items.append({"type": "tool", "key": key})
        elif t == "folder":
            keys = [str(k).strip() for k in it.get("keys", []) if str(k).strip()]
            fid = str(it.get("id") or "").strip()
            name = str(it.get("name") or "Folder").strip() or "Folder"
            if fid and keys:
                items.append({"type": "folder", "id": fid, "name": name, "keys": keys})
    return {"items": items}
