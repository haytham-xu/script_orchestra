"""
Video Duplicate Finder — Settings Manager.

Singleton-style configuration loader/writer.

DECOUPLED: this module must not import from duplicate_finder.
Layout intentionally mirrors duplicate_finder's settings_manager.py but
field set is video-specific (see buffer/04_image_to_video_mapping.md §8).

Settings file lives next to this module:
    backend/video_duplicate_finder/settings.json
"""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional
from multiprocessing import cpu_count

SETTINGS_FILE = Path(__file__).parent / 'settings.json'

# Default thumbnail cache directory: <module_dir>/thumbnails/
_DEFAULT_THUMB_DIR = Path(__file__).parent / 'thumbnails'

# Default DB file: <module_dir>/video_hash_cache.db
_DEFAULT_DB_PATH = Path(__file__).parent / 'video_hash_cache.db'

DEFAULT_SETTINGS: Dict = {
    'delete_target_path': '',
    'similarity_threshold': 80,
    'folder_paths': [],
    'folder_root_paths': {},
    'exclude_folder_paths': [],

    # Video-specific auto-selection rules
    # (see DECISION D-08 / 04_image_to_video_mapping.md §9)
    'auto_selection_rules': {
        'auto_mark_lower_resolution': True,
        'auto_mark_lower_bitrate': True,
        'auto_mark_smaller_filesize': False,
        'auto_mark_older_codec': True,
        'auto_mark_numbered_copies': True,
        'prefer_folders': [],
    },

    # Companion files moved/renamed along with the video
    # (see DECISION D-07 / 04 §1.7)
    'companion_extensions': [
        '.srt', '.ass', '.vtt', '.sub', '.idx',
        '.nfo', '.jpg', '.png', '.chapters',
    ],

    # Filesystem locations (None → use the module-relative defaults)
    'video_db_path': None,
    'thumbnail_cache_dir': None,

    # Workers
    'max_cpu_cores': 2,  # video version: lower default than image (D-13)

    # ffmpeg path: None → use imageio_ffmpeg.get_ffmpeg_exe() bundled binary
    # (string override allowed for users who want system ffmpeg)
    # (see DECISION D-12 revised)
    'ffmpeg_path': None,

    # Hash extraction tuning
    'n_frames': 8,
    'frame_extract_timeout_seconds': 30,
    'thumbnail_position_percent': 30,  # 0..100; 30 = pick frame at 30% of duration

    # UI
    'page_size': 100,

    # Phase 1 perf knobs (smaller batch than image version — single video
    # task is much slower, so feedback granularity must be finer)
    'phase1': {
        'worker_handler_size': 1,
        'db_commit_batch_size': 50,
        'progress_update_interval': 10,
        'ipc_chunk_size': 1,
        'scan_delay': 0.0,
        'compute_delay': 0.0,
    },

    # Phase 2 perf knobs
    'phase2': {
        'worker_handler_size': 1,
        'db_commit_batch_size': 100,
        'progress_update_interval': 100,
        'ipc_chunk_size': 10,
        'compare_delay': 0.0,
    },
}


class SettingsManager:
    """Loads / writes settings.json. One instance per process (module singleton)."""

    def __init__(self):
        self.settings_file = SETTINGS_FILE
        self._ensure_settings_exist()

    # ---- core file I/O ----

    def _ensure_settings_exist(self):
        if not self.settings_file.exists():
            self.save_settings(DEFAULT_SETTINGS)
            print(f"[Video SettingsManager] Seeded defaults to {self.settings_file}")

    def get_settings(self) -> Dict:
        """Read settings.json. Returns a fresh copy on every call (file may have
        been edited between requests). Falls back to defaults on read error."""
        try:
            with open(self.settings_file, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            return loaded
        except Exception as e:
            print(f"[Video SettingsManager] Error loading settings: {e} — using defaults")
            return DEFAULT_SETTINGS.copy()

    def save_settings(self, settings: Dict):
        with open(self.settings_file, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)

    # ---- typed accessors ----

    def get_delete_target_path(self) -> str:
        return self.get_settings().get('delete_target_path', '') or ''

    def get_similarity_threshold(self) -> int:
        """UI threshold (percentage 0..100)."""
        return int(self.get_settings().get('similarity_threshold', 80))

    def get_folder_paths(self) -> List[str]:
        return list(self.get_settings().get('folder_paths', []) or [])

    def get_exclude_folder_paths(self) -> List[str]:
        return list(self.get_settings().get('exclude_folder_paths', []) or [])

    def get_max_cpu_cores(self) -> int:
        raw = int(self.get_settings().get('max_cpu_cores', 2) or 2)
        available = cpu_count()
        return max(1, min(available, raw))

    # ---- video-specific paths ----

    def get_video_db_path(self) -> str:
        """Configured DB path, or the module-relative default."""
        configured = self.get_settings().get('video_db_path')
        if configured:
            return str(configured)
        return str(_DEFAULT_DB_PATH)

    def get_thumbnail_cache_dir(self) -> str:
        """Configured cache dir, or the module-relative default.
        Creates the directory if missing."""
        configured = self.get_settings().get('thumbnail_cache_dir')
        dir_path = Path(configured) if configured else _DEFAULT_THUMB_DIR
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"[Video SettingsManager] Could not create thumbnail dir {dir_path}: {e}")
        return str(dir_path)

    def get_ffmpeg_path(self) -> str:
        """ffmpeg executable path. Returns:
          - configured ffmpeg_path setting (if non-empty)
          - else imageio_ffmpeg.get_ffmpeg_exe() bundled binary
          - else literal 'ffmpeg' (system PATH fallback)
        See DECISION D-12 (revised) — cv2 is primary, ffmpeg is fallback.
        """
        configured = self.get_settings().get('ffmpeg_path')
        if configured:
            return str(configured)
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception as e:
            print(f"[Video SettingsManager] imageio_ffmpeg unavailable ({e}) — falling back to 'ffmpeg' in PATH")
            return 'ffmpeg'

    # ---- hash tuning ----

    def get_n_frames(self) -> int:
        return int(self.get_settings().get('n_frames', 8) or 8)

    def get_frame_extract_timeout_seconds(self) -> int:
        return int(self.get_settings().get('frame_extract_timeout_seconds', 30) or 30)

    def get_thumbnail_position_percent(self) -> int:
        v = int(self.get_settings().get('thumbnail_position_percent', 30) or 30)
        return max(0, min(100, v))

    def get_companion_extensions(self) -> List[str]:
        exts = self.get_settings().get('companion_extensions') or []
        # normalize: lowercase, must start with '.'
        out: List[str] = []
        for e in exts:
            if not isinstance(e, str) or not e:
                continue
            e = e.lower()
            if not e.startswith('.'):
                e = '.' + e
            out.append(e)
        return out

    # ---- auto-select ----

    def get_auto_selection_rules(self) -> Dict:
        rules = self.get_settings().get('auto_selection_rules') or {}
        # ensure all expected keys present (don't punish missing entries with KeyError)
        defaults = DEFAULT_SETTINGS['auto_selection_rules']
        return {**defaults, **rules}

    # ---- phase 1 / 2 perf ----

    def get_phase1_settings(self) -> Dict:
        return self.get_settings().get('phase1') or DEFAULT_SETTINGS['phase1']

    def get_phase1_worker_handler_size(self) -> int:
        return int(self.get_phase1_settings().get('worker_handler_size', 1) or 1)

    def get_phase1_db_commit_batch_size(self) -> int:
        return int(self.get_phase1_settings().get('db_commit_batch_size', 50) or 50)

    def get_phase1_progress_update_interval(self) -> int:
        return int(self.get_phase1_settings().get('progress_update_interval', 10) or 10)

    def get_phase1_ipc_chunk_size(self) -> int:
        return int(self.get_phase1_settings().get('ipc_chunk_size', 1) or 1)

    def get_phase1_scan_delay(self) -> float:
        return float(self.get_phase1_settings().get('scan_delay', 0.0) or 0.0)

    def get_phase1_compute_delay(self) -> float:
        return float(self.get_phase1_settings().get('compute_delay', 0.0) or 0.0)

    def get_phase2_settings(self) -> Dict:
        return self.get_settings().get('phase2') or DEFAULT_SETTINGS['phase2']

    def get_phase2_worker_handler_size(self) -> int:
        return int(self.get_phase2_settings().get('worker_handler_size', 1) or 1)

    def get_phase2_db_commit_batch_size(self) -> int:
        return int(self.get_phase2_settings().get('db_commit_batch_size', 100) or 100)

    def get_phase2_progress_update_interval(self) -> int:
        return int(self.get_phase2_settings().get('progress_update_interval', 100) or 100)

    def get_phase2_ipc_chunk_size(self) -> int:
        return int(self.get_phase2_settings().get('ipc_chunk_size', 10) or 10)

    def get_phase2_compare_delay(self) -> float:
        return float(self.get_phase2_settings().get('compare_delay', 0.0) or 0.0)

    # ---- UI ----

    def get_page_size(self) -> int:
        return int(self.get_settings().get('page_size', 100) or 100)


# Module-level singleton (mirrors duplicate_finder pattern; instance is fresh
# per-process — no cross-process state).
settings_manager = SettingsManager()
