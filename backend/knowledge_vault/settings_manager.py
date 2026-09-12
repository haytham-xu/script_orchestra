"""Knowledge Vault — settings (JSON)."""
import os
import json
import copy
from typing import Any, Dict

SETTINGS_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")

DEFAULT_SETTINGS: Dict[str, Any] = {
    "embed_model": "",   # sentence-transformers model name — set in Settings
    "ai_model": "",      # model for AI query calls — set in Settings
}


def _ensure() -> None:
    if not os.path.exists(SETTINGS_FILE):
        try:
            save_settings(copy.deepcopy(DEFAULT_SETTINGS))
            print(f"Created default knowledge_vault settings.json at {SETTINGS_FILE}")
        except Exception as e:
            print(f"Failed to create knowledge_vault settings.json: {e}")


def load_settings() -> Dict[str, Any]:
    _ensure()
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = copy.deepcopy(DEFAULT_SETTINGS)
        merged.update(data or {})
        return merged
    except Exception as e:
        print(f"Failed to load knowledge_vault settings.json: {e}")
        return copy.deepcopy(DEFAULT_SETTINGS)


def save_settings(settings: Dict[str, Any]) -> None:
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


def validate_and_normalize(patch: dict, current: dict) -> dict:
    merged = dict(current)
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
    return merged


def get_db_path() -> str:
    return os.path.join(SETTINGS_DIR, "knowledge_vault.db")
