"""
Photo Classifier Settings Manager

Manages persistent user settings (like root path) stored in user_settings.json
"""
import os
import json
from typing import Dict, Any

# Settings file path (in photo_classifier directory)
SETTINGS_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(SETTINGS_DIR, 'user_settings.json')

DEFAULT_SETTINGS = {
    'rootPath': ''
}


def _ensure_settings_file_exists() -> None:
    """Ensure user_settings.json exists, create if not"""
    if not os.path.exists(SETTINGS_FILE):
        try:
            save_settings(DEFAULT_SETTINGS.copy())
            print(f"✓ Created default user_settings.json at {SETTINGS_FILE}")
        except Exception as e:
            print(f"⚠️ Failed to create user_settings.json: {e}")


def load_settings() -> Dict[str, Any]:
    """Load settings from user_settings.json"""
    _ensure_settings_file_exists()

    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Failed to load user_settings.json: {e}")
        return DEFAULT_SETTINGS.copy()


def save_settings(settings: Dict[str, Any]) -> None:
    """Save settings to user_settings.json"""
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Failed to save user_settings.json: {e}")
        raise


def get_root_path() -> str:
    """Get root path from settings"""
    settings = load_settings()
    return settings.get('rootPath', '')


def set_root_path(path: str) -> None:
    """Set root path in settings"""
    settings = load_settings()
    settings['rootPath'] = path
    save_settings(settings)
