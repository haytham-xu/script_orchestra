"""Knowledge Vault — settings (JSON)."""
import os
import json
import copy
from typing import Any, Dict

SETTINGS_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")

DEFAULT_SETTINGS: Dict[str, Any] = {
    "auto_build": False,          # auto-build knowledge network after new fragments
    "embed_model": "",            # vector embed model — set in Settings (no baked-in name)
    "ai_model": "",               # model for build/query AI calls — set in Settings
    "relate_top_k": 5,            # candidates considered for auto-relate/dedup
    "stale_days": 90,             # a fragment unused this long → flagged for review
    "link_check_enabled": False,  # opt-in: probe url fragments over HTTP (leaves the machine — off by default)
}


def _ensure() -> None:
    if not os.path.exists(SETTINGS_FILE):
        try:
            save_settings(copy.deepcopy(DEFAULT_SETTINGS))
            print(f"✓ Created default knowledge_vault settings.json at {SETTINGS_FILE}")
        except Exception as e:
            print(f"⚠️ Failed to create knowledge_vault settings.json: {e}")


def load_settings() -> Dict[str, Any]:
    _ensure()
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = copy.deepcopy(DEFAULT_SETTINGS)
        merged.update(data or {})
        return merged
    except Exception as e:
        print(f"⚠️ Failed to load knowledge_vault settings.json: {e}")
        return copy.deepcopy(DEFAULT_SETTINGS)


def save_settings(settings: Dict[str, Any]) -> None:
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


def validate_and_normalize(patch: dict, current: dict) -> dict:
    merged = dict(current)
    if "auto_build" in patch:
        merged["auto_build"] = bool(patch["auto_build"])
    if "embed_model" in patch:
        v = patch["embed_model"]
        if not isinstance(v, str) or not v.strip():
            raise ValueError("embed_model must be a non-empty string")
        merged["embed_model"] = v.strip()
    if "ai_model" in patch:
        v = patch["ai_model"]
        if not isinstance(v, str) or not v.strip():
            raise ValueError("ai_model must be a non-empty string")
        merged["ai_model"] = v.strip()
    if "relate_top_k" in patch:
        try:
            merged["relate_top_k"] = max(1, min(int(patch["relate_top_k"]), 50))
        except (TypeError, ValueError):
            raise ValueError("relate_top_k must be an integer")
    if "stale_days" in patch:
        try:
            merged["stale_days"] = max(1, min(int(patch["stale_days"]), 3650))
        except (TypeError, ValueError):
            raise ValueError("stale_days must be an integer")
    if "link_check_enabled" in patch:
        merged["link_check_enabled"] = bool(patch["link_check_enabled"])
    return merged


def get_db_path() -> str:
    return os.path.join(SETTINGS_DIR, "knowledge_vault.db")
