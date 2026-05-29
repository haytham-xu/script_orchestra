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
    'max_cpu_cores': 1,  # Default to 1 CPU core for precise control
    'phase1': {
        'worker_handler_size': 1,           # Worker processes files one at a time
        'db_commit_batch_size': 100,        # Accumulate N results before DB commit
        'progress_update_interval': 100,    # Send progress every N files
        'ipc_chunk_size': 10,               # IPC optimization: batch N tasks
        'scan_delay': 0.0,                  # Delay between file scans (seconds)
        'compute_delay': 0.0                # Delay between hash computations (seconds)
    },
    'phase2': {
        'worker_handler_size': 1,           # Worker processes files one at a time
        'db_commit_batch_size': 100,        # Accumulate N results before DB commit
        'progress_update_interval': 100,    # Send progress every N files
        'ipc_chunk_size': 10,               # IPC optimization: batch N tasks
        'compare_delay': 0.0                # Delay between comparisons (seconds)
    },
    # Keep old 'performance' for backward compatibility (will be migrated)
    'performance': {
        'scan_delay': 0.0,
        'compute_delay': 0.0,
        'compare_delay': 0.0,
        'chunk_size': 100,
        'progress_update_interval': 100
    }
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

    def get_performance_settings(self) -> Dict:
        """Get performance settings (delays and chunk size)"""
        settings = self.get_settings()
        default_perf = DEFAULT_SETTINGS['performance']
        return settings.get('performance', default_perf)

    def get_scan_delay(self) -> float:
        """Get scan delay in seconds"""
        return self.get_performance_settings().get('scan_delay', 0.0)

    def get_compute_delay(self) -> float:
        """Get compute delay in seconds"""
        return self.get_performance_settings().get('compute_delay', 0.0)

    def get_compare_delay(self) -> float:
        """Get compare delay in seconds"""
        return self.get_performance_settings().get('compare_delay', 0.0)

    def get_chunk_size(self) -> int:
        """Get chunk size for batch processing"""
        return self.get_performance_settings().get('chunk_size', 100)

    def get_progress_update_interval(self) -> int:
        """Get progress update interval (how many files between updates)"""
        return self.get_performance_settings().get('progress_update_interval', 100)

    # ========== Phase 1 Settings ==========

    def get_phase1_settings(self) -> Dict:
        """Get Phase 1 settings with migration from old format"""
        settings = self.get_settings()

        # If phase1 exists, use it
        if 'phase1' in settings:
            return settings['phase1']

        # Otherwise, migrate from old performance settings
        perf = self.get_performance_settings()
        return {
            'worker_handler_size': 1,
            'db_commit_batch_size': perf.get('chunk_size', 100),
            'progress_update_interval': perf.get('progress_update_interval', 100),
            'ipc_chunk_size': 10,
            'scan_delay': perf.get('scan_delay', 0.0),
            'compute_delay': perf.get('compute_delay', 0.0)
        }

    def get_phase1_worker_handler_size(self) -> int:
        """Get Phase 1 worker handler size"""
        return self.get_phase1_settings().get('worker_handler_size', 1)

    def get_phase1_db_commit_batch_size(self) -> int:
        """Get Phase 1 database commit batch size"""
        return self.get_phase1_settings().get('db_commit_batch_size', 100)

    def get_phase1_progress_update_interval(self) -> int:
        """Get Phase 1 progress update interval"""
        return self.get_phase1_settings().get('progress_update_interval', 100)

    def get_phase1_ipc_chunk_size(self) -> int:
        """Get Phase 1 IPC chunk size"""
        return self.get_phase1_settings().get('ipc_chunk_size', 10)

    def get_phase1_scan_delay(self) -> float:
        """Get Phase 1 scan delay in seconds"""
        return self.get_phase1_settings().get('scan_delay', 0.0)

    def get_phase1_compute_delay(self) -> float:
        """Get Phase 1 compute delay in seconds"""
        return self.get_phase1_settings().get('compute_delay', 0.0)

    # ========== Phase 2 Settings ==========

    def get_phase2_settings(self) -> Dict:
        """Get Phase 2 settings with migration from old format"""
        settings = self.get_settings()

        # If phase2 exists, use it
        if 'phase2' in settings:
            return settings['phase2']

        # Otherwise, migrate from old performance settings
        perf = self.get_performance_settings()
        return {
            'worker_handler_size': 1,
            'db_commit_batch_size': perf.get('chunk_size', 100),
            'progress_update_interval': perf.get('progress_update_interval', 100),
            'ipc_chunk_size': 10,
            'compare_delay': perf.get('compare_delay', 0.0)
        }

    def get_phase2_worker_handler_size(self) -> int:
        """Get Phase 2 worker handler size"""
        return self.get_phase2_settings().get('worker_handler_size', 1)

    def get_phase2_db_commit_batch_size(self) -> int:
        """Get Phase 2 database commit batch size"""
        return self.get_phase2_settings().get('db_commit_batch_size', 100)

    def get_phase2_progress_update_interval(self) -> int:
        """Get Phase 2 progress update interval"""
        return self.get_phase2_settings().get('progress_update_interval', 100)

    def get_phase2_ipc_chunk_size(self) -> int:
        """Get Phase 2 IPC chunk size"""
        return self.get_phase2_settings().get('ipc_chunk_size', 10)

    def get_phase2_compare_delay(self) -> float:
        """Get Phase 2 compare delay in seconds"""
        return self.get_phase2_settings().get('compare_delay', 0.0)


# Global instance
settings_manager = SettingsManager()
