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
        """Get default settings structure with empty values.

        paths is intentionally minimal: manga viewer is a reading +
        light-classification tool. The scan source is derived from the
        category main×sub folder combinations, and the index lives under
        root_path (see get_index_path_derived).
        """
        return {
            "random": {
                "count": 10,
                "enabled": True
            },
            "categories": {
                # each entry: {"key": str, "name": str, "path": str}
                #   key  = shown in UI + used as the category label
                #   name = currently unused, kept for future use
                #   path = on-disk folder name under root_path
                "main": [],
                "sub": []
            },
            "display": {
                "page_size": 10,
                "show_uninitialized_only": False,
                "size_sort_enabled": False,
                "name_sort_enabled": True,
                "default_sort": "name"
            },
            "paths": {
                "root_path": "",
                "delete_paths": "",
                "ignore_scan_folders": []
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

    # ---- category helpers --------------------------------------------

    @staticmethod
    def normalize_category(c: dict) -> dict:
        """Normalize a category entry to {key, name, path}.

        Tolerates legacy fields: id→key, target_folder→path, label→name.
        """
        if not isinstance(c, dict):
            return {"key": "", "name": "", "path": ""}
        key = c.get("key") or c.get("id") or ""
        name = c.get("name") if c.get("name") is not None else c.get("label", "")
        path = c.get("path") if c.get("path") is not None else c.get("target_folder", "")
        return {"key": key, "name": name or "", "path": path or ""}

    def get_categories(self) -> dict:
        """Return categories with every entry normalized to {key, name, path}."""
        cats = self._read_from_file().get("categories", {})
        return {
            "main": [self.normalize_category(c) for c in cats.get("main", [])],
            "sub": [self.normalize_category(c) for c in cats.get("sub", [])],
        }

    def get_index_path_derived(self) -> str:
        """Index dir derived from root_path: <root>/.manga_index (dot-prefixed
        so it is never mistaken for a manga folder)."""
        root = self.get_setting("paths.root_path", "")
        if not root:
            return ""
        return os.path.join(root, ".manga_index")


# Global settings manager instance
settings_manager = SettingsManager()
