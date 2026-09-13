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

        - Plain files at the root are tracked with a timestamp determined by
          the configured timestamp_rules (last_used or mtime).
        - Subdirectories are tracked as a single entry whose last_active is
          the max last_active of direct children, size = sum of their sizes.

        After the scan, entries not touched in this pass are pruned.
        """
        try:
            settings = settings_manager.load_settings()
            scan_paths = settings.get('scan_paths', [])
            ignore_patterns = settings.get('ignore_patterns', [])
            ts_rules = settings.get('timestamp_rules', [])
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
                            mtime = st.st_mtime
                            atime = st.st_atime
                            size = st.st_size
                            last_active = _resolve_last_active(entry_path, mtime, ts_rules)
                            repository.upsert_file(
                                entry_path, size, mtime, atime, last_active, scan_time
                            )

                        elif os.path.isdir(entry_path):
                            size, last_active, mtime, atime = _stat_dir_shallow(
                                entry_path, ts_rules
                            )
                            repository.upsert_file(
                                entry_path, size, mtime, atime, last_active, scan_time
                            )
                    except OSError:
                        pass

                    self._scanned += 1

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


def _ts_source_for(path: str, rules: list) -> str:
    """Return 'last_used' or 'mtime' for the given file path based on rules.

    Rules are evaluated in order; the first rule whose extensions list contains
    the file's extension (case-insensitive) or '*' wins.
    """
    ext = os.path.splitext(path)[1].lower()
    for rule in rules:
        for pattern in rule.get('extensions', []):
            if pattern == '*' or pattern.lower() == ext:
                return rule.get('source', 'mtime')
    return 'mtime'


def _get_last_used_macos(path: str) -> float | None:
    """Query kMDItemLastUsedDate via mdls. Returns a Unix timestamp or None."""
    try:
        r = subprocess.run(
            ['mdls', '-name', 'kMDItemLastUsedDate', '-raw', path],
            capture_output=True, text=True, timeout=3,
        )
        val = r.stdout.strip()
        if val and val != '(null)':
            # Format: "2024-01-15 10:23:45 +0000"
            from datetime import datetime
            dt = datetime.strptime(val, '%Y-%m-%d %H:%M:%S %z')
            return dt.timestamp()
    except Exception:
        pass
    return None


def _resolve_last_active(path: str, mtime: float, rules: list) -> float:
    """Determine last_active for a file according to the timestamp rules."""
    source = _ts_source_for(path, rules)
    if source == 'last_used' and platform.system() == 'Darwin':
        lu = _get_last_used_macos(path)
        if lu is not None:
            return lu
    return mtime


def _stat_dir_shallow(dir_path: str, ts_rules: list = None):
    """Return (total_size, last_active, max_mtime, max_atime) for a directory.

    Reads direct children only. last_active for each child file is resolved
    via ts_rules so directories also benefit from last_used timestamps.
    """
    if ts_rules is None:
        ts_rules = []
    total_size = 0
    max_mtime = 0.0
    max_atime = 0.0
    max_last_active = 0.0

    try:
        for name in os.listdir(dir_path):
            child = os.path.join(dir_path, name)
            try:
                st = os.stat(child)
                if os.path.isfile(child):
                    total_size += st.st_size
                    la = _resolve_last_active(child, st.st_mtime, ts_rules)
                    if la > max_last_active:
                        max_last_active = la
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

    if max_last_active == 0.0:
        max_last_active = max(max_mtime, max_atime)

    return total_size, max_last_active, max_mtime, max_atime
