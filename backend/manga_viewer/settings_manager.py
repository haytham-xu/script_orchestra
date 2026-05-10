import json
import os
from pathlib import Path

class SettingsManager:
    """Manage manga viewer settings - stateless, always reads from JSON file."""

    def __init__(self, settings_file: str = None):
        if settings_file is None:
            # Default settings file location
            self.settings_file = os.path.join(
                os.path.dirname(__file__),
                'manga_viewer_settings.json'
            )
        else:
            self.settings_file = settings_file

        # Ensure settings file exists on initialization
        if not os.path.exists(self.settings_file):
            print(f"Settings file not found. Creating default settings at {self.settings_file}")
            self._save_settings(self._get_default_settings())

    def _get_default_settings(self) -> dict:
        """Get default settings structure with empty values."""
        return {
            "random": {
                "count": 10,
                "enabled": True
            },
            "categories": {
                "main": [],
                "sub": []
            },
            "display": {
                "page_size": 10,
                "show_uninitialized_only": False,
                "default_sort": "name"
            },
            "paths": {
                "root_path": "",
                "index_path": "",
                "scan_folders": [],
                "ignore_scan_folders": [],
                "category_paths": "",
                "delete_paths": ""
            }
        }

    def _read_from_file(self) -> dict:
        """Read settings from JSON file."""
        try:
            with open(self.settings_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            # File was deleted, create default
            defaults = self._get_default_settings()
            self._save_settings(defaults)
            return defaults
        except Exception as e:
            raise ValueError(f"Error loading settings from {self.settings_file}: {e}")

    def _save_settings(self, settings: dict):
        """Save settings to JSON file."""
        try:
            os.makedirs(os.path.dirname(self.settings_file), exist_ok=True)
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving settings: {e}")
            raise

    def get_settings(self) -> dict:
        """Get all settings - always reads from file."""
        return self._read_from_file()

    def get_setting(self, key_path: str, default=None):
        """Get a specific setting by dot notation path - reads from file."""
        settings = self._read_from_file()
        keys = key_path.split('.')
        value = settings
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    def update_settings(self, updates: dict):
        """Update settings - reads current, merges, saves back to file."""
        current = self._read_from_file()
        self._deep_merge(current, updates)
        self._save_settings(current)

    def _deep_merge(self, base: dict, override: dict):
        """Deep merge override into base."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value


# Global settings manager instance
settings_manager = SettingsManager()
