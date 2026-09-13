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
        """Shallow scan: for each configured path, track immediate children.

        - Plain files under the root are tracked directly.
        - Subdirectories are tracked as a single entry: last_active = max
          mtime/atime of direct children, size = sum of direct children sizes.

        After the scan, entries whose scan_time predates this run are pruned
        (handles renames and deletions without a separate disk-existence check).
        """
        try:
            settings = settings_manager.load_settings()
            scan_paths = settings.get('scan_paths', [])
            ignore_patterns = settings.get('ignore_patterns', [])
            scan_time = time.time()

            for root_path in scan_paths:
                if not os.path.isdir(root_path):
                    continue

                try:
                    entries = os.listdir(root_path)
                except OSError:
                    continue

                self._estimated_total += len(entries)

                for name in entries:
                    if self._should_ignore(name, ignore_patterns):
                        self._scanned += 1
                        continue

                    entry_path = os.path.join(root_path, name)
                    self._current_path = entry_path

                    try:
                        if os.path.isfile(entry_path):
                            st = os.stat(entry_path)
                            mtime, atime = st.st_mtime, st.st_atime
                            size = st.st_size
                            last_active = max(mtime, atime)
                            repository.upsert_file(
                                entry_path, size, mtime, atime, last_active, scan_time
                            )

                        elif os.path.isdir(entry_path):
                            # Aggregate direct children of the subdirectory
                            size, last_active, mtime, atime = _stat_dir_shallow(entry_path)
                            repository.upsert_file(
                                entry_path, size, mtime, atime, last_active, scan_time
                            )
                    except OSError:
                        pass

                    self._scanned += 1

            # Mark-and-sweep: remove entries not touched in this scan pass
            repository.prune_by_scan_time(scan_time)
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


def _stat_dir_shallow(dir_path: str):
    """Return (total_size, last_active, max_mtime, max_atime) for a directory.

    Reads direct children only (one level deep) and aggregates:
    - size = sum of child file sizes (subdirectories are counted by their own stat)
    - last_active = max(mtime, atime) across all children
    - mtime/atime = the maximum values seen
    """
    total_size = 0
    max_mtime = 0.0
    max_atime = 0.0

    try:
        for name in os.listdir(dir_path):
            child = os.path.join(dir_path, name)
            try:
                st = os.stat(child)
                if os.path.isfile(child):
                    total_size += st.st_size
                if st.st_mtime > max_mtime:
                    max_mtime = st.st_mtime
                if st.st_atime > max_atime:
                    max_atime = st.st_atime
            except OSError:
                pass
    except OSError:
        pass

    # Fall back to the directory's own stat when empty or unreadable
    if max_mtime == 0.0 or max_atime == 0.0:
        try:
            st = os.stat(dir_path)
            if max_mtime == 0.0:
                max_mtime = st.st_mtime
            if max_atime == 0.0:
                max_atime = st.st_atime
        except OSError:
            pass

    last_active = max(max_mtime, max_atime)
    return total_size, last_active, max_mtime, max_atime
