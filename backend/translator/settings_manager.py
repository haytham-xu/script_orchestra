"""Translator — settings (JSON).

Each scene owns its own system prompt + model, independently (per DESIGN.md:
the two scenes are decoupled and will evolve separately). Prompts are authored
by the user in the settings UI — no built-in prompt text is shipped.
cleanup_days is the default retention used by the one-click cleanup.
"""
import os
import json
import copy
from typing import Any, Dict

SETTINGS_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")

DEFAULT_SETTINGS: Dict[str, Any] = {
    # learning_prompt: optional user preference appended to the fixed
    # learning-point instruction (zh2en only; en2zh has no learning points).
    "zh2en": {"system_prompt": "", "model": "auto", "learning_prompt": ""},
    "en2zh": {"system_prompt": "", "model": "auto"},
    "cleanup_days": 30,   # default retention for one-click cleanup
}


def _ensure() -> None:
    if not os.path.exists(SETTINGS_FILE):
        try:
            save_settings(copy.deepcopy(DEFAULT_SETTINGS))
            print(f"✓ Created default translator settings.json at {SETTINGS_FILE}")
        except Exception as e:
            print(f"⚠️ Failed to create translator settings.json: {e}")


def load_settings() -> Dict[str, Any]:
    _ensure()
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = copy.deepcopy(DEFAULT_SETTINGS)
        # shallow merge, but keep per-scene sub-keys defaulted
        for scene in ("zh2en", "en2zh"):
            if isinstance(data.get(scene), dict):
                merged[scene] = {**merged[scene], **data[scene]}
        if "cleanup_days" in (data or {}):
            merged["cleanup_days"] = data["cleanup_days"]
        return merged
    except Exception as e:
        print(f"⚠️ Failed to load translator settings.json: {e}")
        return copy.deepcopy(DEFAULT_SETTINGS)


def save_settings(settings: Dict[str, Any]) -> None:
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


def _normalize_scene(patch_scene: dict, current_scene: dict) -> dict:
    merged = dict(current_scene)
    if "system_prompt" in patch_scene:
        v = patch_scene["system_prompt"]
        if not isinstance(v, str):
            raise ValueError("system_prompt must be a string")
        merged["system_prompt"] = v
    if "model" in patch_scene:
        v = patch_scene["model"]
        if not isinstance(v, str) or not v.strip():
            raise ValueError("model must be a non-empty string")
        merged["model"] = v.strip()
    if "learning_prompt" in patch_scene:
        v = patch_scene["learning_prompt"]
        if not isinstance(v, str):
            raise ValueError("learning_prompt must be a string")
        merged["learning_prompt"] = v
    return merged


def validate_and_normalize(patch: dict, current: dict) -> dict:
    merged = copy.deepcopy(current)
    for scene in ("zh2en", "en2zh"):
        if isinstance(patch.get(scene), dict):
            merged[scene] = _normalize_scene(patch[scene], current.get(scene, {}))
    if "cleanup_days" in patch:
        try:
            merged["cleanup_days"] = max(1, min(int(patch["cleanup_days"]), 3650))
        except (TypeError, ValueError):
            raise ValueError("cleanup_days must be an integer")
    return merged


def get_scene_config(scene: str) -> Dict[str, Any]:
    """Convenience: return {system_prompt, model} for a scene."""
    s = load_settings()
    return s.get(scene, {"system_prompt": "", "model": "auto"})


def get_db_path() -> str:
    return os.path.join(SETTINGS_DIR, "translator.db")
