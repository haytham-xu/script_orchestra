"""File Tracker — settings (JSON file per module dir)."""
import os
import json
import copy
from typing import Any, Dict

SETTINGS_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(SETTINGS_DIR, 'settings.json')

DEFAULT_SETTINGS: Dict[str, Any] = {
    'scan_paths': [],
    'ignore_patterns': [
        'node_modules', '.git', '__pycache__', '*.pyc', 'venv', '.venv',
        '.DS_Store', 'Thumbs.db', '*.class', 'target', 'dist', 'build',
        '.cache', '.npm', '.gradle', '.idea', '.pytest_cache', '*.egg-info',
        '.tox', 'coverage', '.nyc_output', '.next', '.nuxt', 'vendor',
    ],
    'stale_thresholds_days': {
        'archive': 90,
        'warn': 180,
        'danger': 365,
    },
    # Ordered rules: first matching extension wins; '*' is the catch-all.
    # source values: 'last_used' (kMDItemLastUsedDate, fallback mtime), 'mtime'
    'timestamp_rules': [
        {
            'extensions': ['.jpg', '.jpeg', '.png', '.gif', '.heic', '.webp',
                           '.bmp', '.tiff', '.tif', '.svg', '.ico', '.avif'],
            'source': 'last_used',
        },
        {
            'extensions': ['.mp4', '.mov', '.mkv', '.avi', '.wmv', '.flv',
                           '.m4v', '.webm', '.mpg', '.mpeg'],
            'source': 'last_used',
        },
        {
            'extensions': ['.mp3', '.flac', '.aac', '.wav', '.ogg', '.m4a',
                           '.wma', '.opus'],
            'source': 'last_used',
        },
        {
            'extensions': ['.pdf', '.epub', '.mobi'],
            'source': 'last_used',
        },
        {
            'extensions': ['*'],
            'source': 'mtime',
        },
    ],
}


def _ensure() -> None:
    if not os.path.exists(SETTINGS_FILE):
        save_settings(copy.deepcopy(DEFAULT_SETTINGS))


def load_settings() -> Dict[str, Any]:
    _ensure()
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        merged = copy.deepcopy(DEFAULT_SETTINGS)
        merged.update(data or {})
        return merged
    except Exception:
        return copy.deepcopy(DEFAULT_SETTINGS)


def save_settings(s: Dict[str, Any]) -> None:
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(s, f, indent=2, ensure_ascii=False)


def get_db_path() -> str:
    return os.path.join(SETTINGS_DIR, 'file_tracker.db')
