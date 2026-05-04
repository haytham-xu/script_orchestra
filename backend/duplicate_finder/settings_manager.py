"""
Settings Manager for Duplicate Finder

Manages configuration for duplicate detection and deletion.
"""
import json
from pathlib import Path
from typing import Dict, Optional

# Settings file path
SETTINGS_FILE = Path(__file__).parent / 'settings.json'

DEFAULT_SETTINGS = {
    'delete_target_path': '',
    'similarity_threshold': 90
}

class SettingsManager:
    def __init__(self):
        self.settings_file = SETTINGS_FILE
        self._ensure_settings_exist()

    def _ensure_settings_exist(self):
        """Create settings file with defaults if it doesn't exist"""
        if not self.settings_file.exists():
            self.save_settings(DEFAULT_SETTINGS)

    def get_settings(self) -> Dict:
        """Load settings from file"""
        try:
            with open(self.settings_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading settings: {e}")
            return DEFAULT_SETTINGS.copy()

    def save_settings(self, settings: Dict):
        """Save settings to file"""
        with open(self.settings_file, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)

    def get_delete_target_path(self) -> str:
        """Get configured delete target path"""
        return self.get_settings().get('delete_target_path', '')

    def get_similarity_threshold(self) -> int:
        """Get configured similarity threshold (0-100)"""
        threshold = self.get_settings().get('similarity_threshold', 90)
        # Convert percentage to hamming distance (0-64 for 16x16 hash)
        # 100% = 0 distance, 0% = 64 distance
        max_distance = 64
        return int((100 - threshold) / 100 * max_distance)


# Global instance
settings_manager = SettingsManager()
