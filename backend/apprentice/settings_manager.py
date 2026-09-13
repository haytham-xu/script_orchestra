"""Apprentice — settings (JSON file colocated with module)."""
import os
import json
import copy
from typing import Any, Dict

SETTINGS_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")

DEFAULT_SETTINGS: Dict[str, Any] = {
    "commander_model": "claude-opus-4-5",
    "soldier_model": "claude-sonnet-4-6",
    "commander_max_turns": 50,
    "max_cost_usd": 0,
    "github_token": "",
    "jenkins_url": "",
    "jenkins_user": "",
    "jenkins_token": "",
    "distillation_threshold": 10,
    "distillation_model": "claude-sonnet-4-6",
}


def _ensure() -> None:
    if not os.path.exists(SETTINGS_FILE):
        try:
            save_settings(copy.deepcopy(DEFAULT_SETTINGS))
        except Exception as e:
            print(f"[apprentice] Failed to create settings.json: {e}")


def load_settings() -> Dict[str, Any]:
    _ensure()
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = copy.deepcopy(DEFAULT_SETTINGS)
        merged.update(data or {})
        return merged
    except Exception as e:
        print(f"[apprentice] Failed to load settings.json: {e}")
        return copy.deepcopy(DEFAULT_SETTINGS)


def save_settings(settings: Dict[str, Any]) -> None:
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


def validate_and_normalize(patch: dict, current: dict) -> dict:
    merged = dict(current)
    int_fields = {"commander_max_turns", "distillation_threshold"}
    float_fields = {"max_cost_usd"}
    str_fields = {"commander_model", "soldier_model", "distillation_model",
                  "github_token", "jenkins_url", "jenkins_user", "jenkins_token"}
    for key, value in patch.items():
        if key in int_fields:
            try:
                merged[key] = max(1, int(value))
            except (TypeError, ValueError):
                raise ValueError(f"{key} must be an integer")
        elif key in float_fields:
            try:
                merged[key] = max(0.0, float(value))
            except (TypeError, ValueError):
                raise ValueError(f"{key} must be a number")
        elif key in str_fields:
            merged[key] = str(value or "")
    return merged


def get_db_path() -> str:
    return os.path.join(SETTINGS_DIR, "apprentice.db")
