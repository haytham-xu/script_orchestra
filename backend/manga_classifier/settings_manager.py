"""
Manga Classifier Settings Manager

Manages persistent user settings (paths, scan extensions, category buttons)
stored in settings.json.
"""
import os
import json
import copy
from typing import Any, Dict, List

SETTINGS_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")

DEFAULT_SETTINGS: Dict[str, Any] = {
    "rootPath": "",
    "targetPath": "",
    "deletePath": "",
    "imageExts": [".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"],
    "videoExts": [".mp4", ".webm", ".mov", ".avi", ".mkv"],
    "categoty": {
        "left":  {"name": "Left",  "mainButtons": [], "subButtons": []},
        "right": {"name": "Right", "mainButtons": [], "subButtons": []},
    },
}


def _ensure_settings_file_exists() -> None:
    if not os.path.exists(SETTINGS_FILE):
        try:
            save_settings(copy.deepcopy(DEFAULT_SETTINGS))
            print(f"✓ Created default manga_classifier settings.json at {SETTINGS_FILE}")
        except Exception as e:
            print(f"⚠️ Failed to create manga_classifier settings.json: {e}")


def load_settings() -> Dict[str, Any]:
    _ensure_settings_file_exists()
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = copy.deepcopy(DEFAULT_SETTINGS)
        merged.update(data or {})
        return merged
    except Exception as e:
        print(f"⚠️ Failed to load manga_classifier settings.json: {e}")
        return copy.deepcopy(DEFAULT_SETTINGS)


def save_settings(settings: Dict[str, Any]) -> None:
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Failed to save manga_classifier settings.json: {e}")
        raise


def normalize_ext_list(values: Any) -> List[str]:
    if not isinstance(values, list):
        raise ValueError("extensions must be a list of strings")
    out: List[str] = []
    for v in values:
        if not isinstance(v, str):
            raise ValueError("each extension must be a string")
        s = v.strip().lower()
        if not s:
            continue
        if not s.startswith("."):
            s = "." + s
        if s not in out:
            out.append(s)
    return out


def validate_button_config(cfg: Any) -> Dict[str, Any]:
    if not isinstance(cfg, dict):
        raise ValueError("categoty must be an object")
    result: Dict[str, Any] = {}
    for side in ("left", "right"):
        side_val = cfg.get(side)
        if not isinstance(side_val, dict):
            raise ValueError(f"categoty.{side} must be an object")
        name = side_val.get("name", "")
        if not isinstance(name, str):
            raise ValueError(f"categoty.{side}.name must be a string")
        card: Dict[str, Any] = {"name": name}
        for group in ("mainButtons", "subButtons"):
            raw = side_val.get(group, [])
            if not isinstance(raw, list):
                raise ValueError(f"categoty.{side}.{group} must be a list")
            buttons = []
            for i, btn in enumerate(raw):
                if not isinstance(btn, dict):
                    raise ValueError(f"categoty.{side}.{group}[{i}] must be an object")
                label = btn.get("label", "")
                folder = btn.get("folderPath", "")
                if not isinstance(label, str) or not isinstance(folder, str):
                    raise ValueError(
                        f"categoty.{side}.{group}[{i}] label/folderPath must be strings"
                    )
                if not label.strip():
                    raise ValueError(f"categoty.{side}.{group}[{i}].label is required")
                buttons.append({"label": label, "folderPath": folder})
            card[group] = buttons
        result[side] = card
    return result
