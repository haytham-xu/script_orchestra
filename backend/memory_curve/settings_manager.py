"""Memory Curve — settings (JSON), mirrors manga_classifier pattern."""
import os
import json
import copy
from typing import Any, Dict

SETTINGS_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")

DEFAULT_SETTINGS: Dict[str, Any] = {
    "card_mode": "qa",        # "qa" (front/back) or "single" (one free field)
    "daily_new_limit": 20,    # max brand-new cards introduced per day (0 = no limit)
}


def _ensure() -> None:
    if not os.path.exists(SETTINGS_FILE):
        try:
            save_settings(copy.deepcopy(DEFAULT_SETTINGS))
            print(f"✓ Created default memory_curve settings.json at {SETTINGS_FILE}")
        except Exception as e:
            print(f"⚠️ Failed to create memory_curve settings.json: {e}")


def load_settings() -> Dict[str, Any]:
    _ensure()
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = copy.deepcopy(DEFAULT_SETTINGS)
        merged.update(data or {})
        return merged
    except Exception as e:
        print(f"⚠️ Failed to load memory_curve settings.json: {e}")
        return copy.deepcopy(DEFAULT_SETTINGS)


def save_settings(settings: Dict[str, Any]) -> None:
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


def validate_and_normalize(patch: dict, current: dict) -> dict:
    merged = dict(current)
    if "card_mode" in patch:
        v = patch["card_mode"]
        if v not in ("qa", "single"):
            raise ValueError("card_mode must be 'qa' or 'single'")
        merged["card_mode"] = v
    if "daily_new_limit" in patch:
        try:
            merged["daily_new_limit"] = max(0, min(int(patch["daily_new_limit"]), 1000))
        except (TypeError, ValueError):
            raise ValueError("daily_new_limit must be an integer")
    return merged


def get_db_path() -> str:
    return os.path.join(SETTINGS_DIR, "memory_curve.db")
