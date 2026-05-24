"""
Settings Manager for Duplicate Finder

Manages configuration for duplicate detection and deletion.
"""
import json
from pathlib import Path
from typing import Dict, Optional
from multiprocessing import cpu_count

# Settings file path
SETTINGS_FILE = Path(__file__).parent / 'settings.json'

DEFAULT_SETTINGS = {
    'delete_target_path': '',
    'similarity_threshold': 90,
    'max_cpu_cores': 1  # Default to 1 CPU core for precise control
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
                loaded = json.load(f)
                print(f"[SettingsManager] Loaded settings from {self.settings_file}: max_cpu_cores={loaded.get('max_cpu_cores', 'NOT_SET')}")
                return loaded
        except Exception as e:
            print(f"[SettingsManager] Error loading settings: {e}, using defaults")
            return DEFAULT_SETTINGS.copy()

    def save_settings(self, settings: Dict):
        """Save settings to file"""
        print(f"[SettingsManager] Saving settings to {self.settings_file}: max_cpu_cores={settings.get('max_cpu_cores', 'NOT_SET')}")
        with open(self.settings_file, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        print(f"[SettingsManager] Settings saved successfully")

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

    def get_max_cpu_cores(self) -> int:
        """Get configured maximum CPU cores to use (1 to cpu_count())"""
        current_settings = self.get_settings()
        max_cores = current_settings.get('max_cpu_cores', 1)
        # Ensure within valid range (1 to available cores)
        available_cores = cpu_count()
        result = max(1, min(available_cores, max_cores))
        print(f"[SettingsManager] get_max_cpu_cores() - raw value from settings: {max_cores}, available: {available_cores}, returning: {result}")
        return result

    def get_phash_db_path(self) -> Optional[str]:
        """Get configured phash database path"""
        return self.get_settings().get('phash_db_path', None)


# Global instance
settings_manager = SettingsManager()
