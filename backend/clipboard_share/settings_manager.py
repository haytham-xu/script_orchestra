"""
Clipboard Share Settings Manager
"""
import json
import os

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), 'settings.json')

DEFAULT_SETTINGS = {
    "lan_port": 50002,
    "auto_start": False
}


def load_settings() -> dict:
    if not os.path.exists(SETTINGS_FILE):
        return DEFAULT_SETTINGS.copy()
    try:
        with open(SETTINGS_FILE, 'r') as f:
            data = json.load(f)
        settings = DEFAULT_SETTINGS.copy()
        settings.update(data)
        return settings
    except Exception:
        return DEFAULT_SETTINGS.copy()


def save_settings(settings: dict) -> None:
    merged = DEFAULT_SETTINGS.copy()
    merged.update(settings)
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(merged, f, indent=2)
