"""
Video Duplicate Finder — Scan Manager.

Thread-safe registry of in-flight scans, each backed by a `threading.Event`
that worker code polls to honor stop requests.

DECOUPLED: this module must not import from duplicate_finder.

Use pattern:
    stop_event = scan_manager.start_scan('vscan-123')
    # ... long-running work polls stop_event.is_set() ...
    if scan_manager.is_stopped('vscan-123'):
        return
    scan_manager.complete_scan('vscan-123')

To stop:
    scan_manager.stop_scan('vscan-123')   # → True if found

NOTE: Phase 1/2/3 in `video_workflow.py` use a *different* stop mechanism —
a single `multiprocessing.Manager().Event()` shared across all phases,
because workers run in separate processes. This module is for the legacy
single-process scan path (/scan endpoint), not the new workflow phases.
"""
import threading
from typing import Dict, List


class ScanManager:
    """Process-local registry of active scans."""

    def __init__(self):
        self._active: Dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def start_scan(self, scan_id: str) -> threading.Event:
        """Register a new scan and return its stop-event."""
        with self._lock:
            event = threading.Event()
            self._active[scan_id] = event
            print(f"[Video ScanManager] scan {scan_id} started")
            return event

    def stop_scan(self, scan_id: str) -> bool:
        """Signal a scan to stop. Returns True if found."""
        with self._lock:
            event = self._active.get(scan_id)
            if event is None:
                print(f"[Video ScanManager] stop_scan: {scan_id} not found")
                return False
            event.set()
            print(f"[Video ScanManager] stop signal sent to {scan_id}")
            return True

    def is_stopped(self, scan_id: str) -> bool:
        """Check whether the stop-event for `scan_id` has been set."""
        with self._lock:
            event = self._active.get(scan_id)
            return bool(event and event.is_set())

    def complete_scan(self, scan_id: str) -> None:
        """Deregister a finished scan."""
        with self._lock:
            event = self._active.pop(scan_id, None)
            if event is not None:
                print(f"[Video ScanManager] scan {scan_id} completed and cleaned up")

    def get_active_scans(self) -> List[str]:
        """Snapshot of currently active scan IDs."""
        with self._lock:
            return list(self._active.keys())


# Module-level singleton
scan_manager = ScanManager()
