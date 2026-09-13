"""File Tracker — background scan service."""
import fnmatch
import os
import platform
import subprocess
import threading
import time

from . import repository, settings_manager

_instance = None


def get_service():
    global _instance
    if _instance is None:
        _instance = FileTrackerService()
    return _instance


class FileTrackerService:
    def __init__(self):
        self._scanning = False
        self._scanned = 0
        self._estimated_total = 0
        self._current_path = ''
        self._last_scan_time = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Status / scan control
    # ------------------------------------------------------------------

    def get_status(self):
        return {
            'running': self._scanning,
            'progress': {
                'scanned': self._scanned,
                'total': self._estimated_total,
                'path': self._current_path,
            },
            'last_scan_time': self._last_scan_time,
        }

    def start_scan(self) -> bool:
        with self._lock:
            if self._scanning:
                return False
            self._scanning = True
            self._scanned = 0
            self._estimated_total = 0
            self._current_path = ''
        t = threading.Thread(target=self._run_scan, daemon=True)
        t.start()
        return True

    # ------------------------------------------------------------------
    # Internal scan
    # ------------------------------------------------------------------

    def _run_scan(self):
        try:
            settings = settings_manager.load_settings()
            scan_paths = settings.get('scan_paths', [])
            ignore_patterns = settings.get('ignore_patterns', [])
            scan_time = time.time()

            for root_path in scan_paths:
                if not os.path.isdir(root_path):
                    continue
                for dirpath, dirnames, filenames in os.walk(root_path, topdown=True):
                    # Prune ignored dirs in-place so os.walk won't descend into them
                    dirnames[:] = [
                        d for d in dirnames
                        if not self._should_ignore(d, ignore_patterns)
                    ]
                    self._estimated_total += len(filenames)
                    for fname in filenames:
                        if self._should_ignore(fname, ignore_patterns):
                            self._scanned += 1
                            continue
                        fpath = os.path.join(dirpath, fname)
                        self._current_path = fpath
                        try:
                            st = os.stat(fpath)
                            mtime = st.st_mtime
                            atime = st.st_atime
                            size = st.st_size
                            last_active = max(mtime, atime)
                            repository.upsert_file(
                                fpath, size, mtime, atime, last_active, scan_time
                            )
                        except OSError:
                            pass
                        self._scanned += 1

            repository.prune_missing()
            self._last_scan_time = time.time()
        finally:
            with self._lock:
                self._scanning = False
            self._current_path = ''

    def _should_ignore(self, name: str, patterns: list) -> bool:
        for pat in patterns:
            if pat.startswith('/'):
                continue
            if fnmatch.fnmatch(name, pat):
                return True
        return False

    # ------------------------------------------------------------------
    # File actions
    # ------------------------------------------------------------------

    def trash_file(self, file_id: int) -> None:
        f = repository.get_file(file_id)
        if not f:
            raise ValueError(f'File {file_id} not found in DB')
        if not os.path.exists(f.path):
            raise FileNotFoundError(f'File no longer exists: {f.path}')
        try:
            import send2trash
            send2trash.send2trash(f.path)
        except ImportError:
            _trash_via_osascript(f.path)
        repository.delete_file(file_id)

    def reveal_file(self, file_id: int) -> None:
        f = repository.get_file(file_id)
        if not f:
            raise ValueError(f'File {file_id} not found in DB')
        system = platform.system()
        if system == 'Darwin':
            subprocess.Popen(['open', '-R', f.path])
        elif system == 'Windows':
            subprocess.Popen(['explorer', '/select,', f.path])
        else:
            subprocess.Popen(['xdg-open', os.path.dirname(f.path)])


def _trash_via_osascript(path: str) -> None:
    script = f'tell application "Finder" to delete POSIX file "{path}"'
    result = subprocess.run(['osascript', '-e', script], capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f'osascript trash failed: {result.stderr.decode()}')
