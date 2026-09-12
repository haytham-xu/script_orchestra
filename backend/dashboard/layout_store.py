"""Dashboard — layout persistence.

Reads/writes the 'layout' key inside the shared settings.json.
"""
import os
import json
import tempfile
from typing import Any, Dict

_DIR = os.path.dirname(os.path.abspath(__file__))
_SETTINGS_FILE = os.path.join(_DIR, "settings.json")

_EMPTY: Dict[str, Any] = {"items": []}


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


def load_layout() -> Dict[str, Any]:
    data = _load_settings().get("layout")
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return dict(_EMPTY)
    return data


def save_layout(layout: Dict[str, Any]) -> Dict[str, Any]:
    normalized = _normalize(layout)
    settings = _load_settings()
    settings["layout"] = normalized
    _save_settings(settings)
    return normalized


def _normalize(layout: Dict[str, Any]) -> Dict[str, Any]:
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
