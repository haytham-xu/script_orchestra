"""Assistant — model settings (JSON).

The concrete model IDs live here (user-configured, persisted), never hardcoded
in source. Empty by default; the user sets them in Settings. Four slots:
  - router: the tiny model for complexity classification + summarization
  - simple / medium / hard: complexity tiers the router maps to
"""
import os
import json
import copy
from pathlib import Path
from typing import Any, Dict

SETTINGS_FILE = Path(__file__).resolve().parent / "settings.json"

DEFAULT_SETTINGS: Dict[str, Any] = {
    "models": {
        "router": "",   # tiny classifier / summarizer model
        "simple": "",   # complexity: simple
        "medium": "",   # complexity: medium
        "hard": "",     # complexity: hard
    },
}


def _ensure() -> None:
    if not SETTINGS_FILE.exists():
        try:
            save_settings(copy.deepcopy(DEFAULT_SETTINGS))
        except Exception as e:
            print(f"⚠️ Failed to create assistant settings.json: {e}")


def load_settings() -> Dict[str, Any]:
    _ensure()
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        merged = copy.deepcopy(DEFAULT_SETTINGS)
        merged.update(data or {})
        # merge nested models dict so new slots pick up defaults
        m = copy.deepcopy(DEFAULT_SETTINGS["models"])
        m.update((data or {}).get("models") or {})
        merged["models"] = m
        return merged
    except Exception as e:
        print(f"⚠️ Failed to load assistant settings.json: {e}")
        return copy.deepcopy(DEFAULT_SETTINGS)


def save_settings(settings: Dict[str, Any]) -> None:
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")


def get_models() -> Dict[str, str]:
    return load_settings().get("models", {})


def model_for(slot: str) -> str:
    """Return the configured model id for a slot, or raise if unset."""
    mid = (get_models().get(slot) or "").strip()
    if not mid:
        raise RuntimeError(
            f"No assistant model configured for '{slot}'. Set it in Assistant → Settings.")
    return mid
