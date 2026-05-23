"""
Scan manager for handling stop signals and resource cleanup
"""
import threading
from typing import Dict, List

class ScanManager:
    """Manage active scans and provide stop functionality"""

    def __init__(self):
        self._active_scans: Dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def start_scan(self, scan_id: str) -> threading.Event:
        """Register a new scan"""
        with self._lock:
            stop_event = threading.Event()
            self._active_scans[scan_id] = stop_event
            print(f"[ScanManager] Scan {scan_id} started")
            return stop_event

    def stop_scan(self, scan_id: str) -> bool:
        """Request to stop a scan"""
        with self._lock:
            stop_event = self._active_scans.get(scan_id)
            if stop_event is not None:
                stop_event.set()
                print(f"[ScanManager] Stop signal sent to scan {scan_id}")
                return True
            else:
                print(f"[ScanManager] Scan {scan_id} not found")
                return False

    def is_stopped(self, scan_id: str) -> bool:
        """Check if scan should stop"""
        with self._lock:
            stop_event = self._active_scans.get(scan_id)
            if stop_event is not None:
                return stop_event.is_set()
            return False

    def complete_scan(self, scan_id: str) -> None:
        """Remove scan from active list"""
        with self._lock:
            stop_event = self._active_scans.pop(scan_id, None)
            if stop_event is not None:
                print(f"[ScanManager] Scan {scan_id} completed and cleaned up")

    def get_active_scans(self) -> List[str]:
        """Get list of active scan IDs"""
        with self._lock:
            return list(self._active_scans.keys())


# Global scan manager instance
scan_manager = ScanManager()
