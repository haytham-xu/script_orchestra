"""
File Duplicate — Settings manager
"""
import json
import os

_SETTINGS_FILE = os.path.join(os.path.dirname(__file__), 'settings.json')

DEFAULT_SETTINGS = {
    # List of {id, name, path, priority} dicts — priority 1 = highest (keep these)
    'scan_roots': [],
    # Glob-style dir names to always skip
    'exclude_patterns': ['.git', '__pycache__', 'node_modules', '.DS_Store'],
    # File extensions to include; empty list = all files
    'include_extensions': [],
    # Where to move "deleted" files (soft-delete)
    'trash_path': '',
    # Batch sizes for hashing workers
    'hash_batch_size': 200,
    # Max worker processes for hashing
    'max_workers': 4,
    # Pagination
    'page_size': 20,
}


def load() -> dict:
    if not os.path.exists(_SETTINGS_FILE):
        return dict(DEFAULT_SETTINGS)
    try:
        with open(_SETTINGS_FILE, 'r') as f:
            data = json.load(f)
        # fill in any missing keys from defaults
        for k, v in DEFAULT_SETTINGS.items():
            if k not in data:
                data[k] = v
        return data
    except Exception:
        return dict(DEFAULT_SETTINGS)


def save(settings: dict) -> None:
    with open(_SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)


def get_scan_roots() -> list:
    return load().get('scan_roots', [])


def get_trash_path() -> str:
    return load().get('trash_path', '')


def get_include_extensions() -> list:
    return load().get('include_extensions', [])


def get_exclude_patterns() -> list:
    return load().get('exclude_patterns', DEFAULT_SETTINGS['exclude_patterns'])


def get_max_workers() -> int:
    return int(load().get('max_workers', DEFAULT_SETTINGS['max_workers']))


def get_hash_batch_size() -> int:
    return int(load().get('hash_batch_size', DEFAULT_SETTINGS['hash_batch_size']))


def get_page_size() -> int:
    return int(load().get('page_size', DEFAULT_SETTINGS['page_size']))
