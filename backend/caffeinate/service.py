"""
Caffeinate Service

Business logic for starting/stopping a `caffeinate` process and streaming
periodic timestamp log lines to WebSocket clients.
"""
import subprocess
import threading
from datetime import datetime
from typing import Dict, List, Optional

from .config import (
    DEFAULT_INTERVAL_SECONDS,
    MAX_INTERVAL_SECONDS,
    MAX_LOG_ENTRIES,
    MIN_INTERVAL_SECONDS,
)


class CaffeinateService:
    """Manage a single caffeinate process plus a heartbeat log emitter."""

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._logs: List[Dict] = []
        self._current_id = 0
        self._interval_seconds: int = DEFAULT_INTERVAL_SECONDS
        self._started_at: Optional[str] = None
        self._stop_event: Optional[threading.Event] = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._broadcaster = None

    def register_broadcaster(self, broadcaster):
        """Register a callable used to push new log entries to clients."""
        self._broadcaster = broadcaster

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def get_status(self) -> Dict:
        return {
            "running": self.is_running(),
            "interval_seconds": self._interval_seconds,
            "started_at": self._started_at,
            "pid": self._process.pid if self.is_running() else None,
            "log_count": len(self._logs),
        }

    def get_logs(self, limit: int = MAX_LOG_ENTRIES) -> List[Dict]:
        return self._logs[-limit:]

    def clear_logs(self) -> int:
        with self._lock:
            count = len(self._logs)
            self._logs.clear()
        return count

    def start(self, interval_seconds: int = DEFAULT_INTERVAL_SECONDS) -> Dict:
        if interval_seconds < MIN_INTERVAL_SECONDS or interval_seconds > MAX_INTERVAL_SECONDS:
            raise ValueError(
                f"interval_seconds must be between {MIN_INTERVAL_SECONDS} "
                f"and {MAX_INTERVAL_SECONDS}"
            )

        with self._lock:
            if self.is_running():
                raise RuntimeError("Caffeinate is already running")

            self._process = subprocess.Popen(
                ["caffeinate", "-dims"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._interval_seconds = interval_seconds
            self._started_at = datetime.now().isoformat()
            self._stop_event = threading.Event()
            self._heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop,
                args=(self._stop_event, interval_seconds),
                daemon=True,
            )
            self._heartbeat_thread.start()

        self._append_log(f"Caffeinate started (pid={self._process.pid}, "
                         f"interval={interval_seconds}s)")
        return self.get_status()

    def stop(self) -> Dict:
        with self._lock:
            if not self.is_running():
                raise RuntimeError("Caffeinate is not running")

            if self._stop_event:
                self._stop_event.set()

            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=2)

            pid = self._process.pid
            self._process = None
            self._started_at = None

        self._append_log(f"Caffeinate stopped (pid={pid})")
        return self.get_status()

    def _heartbeat_loop(self, stop_event: threading.Event, interval: int):
        while not stop_event.is_set():
            if not self.is_running():
                break
            self._append_log(f"heartbeat: {datetime.now().isoformat()}")
            stop_event.wait(interval)

    def _append_log(self, message: str) -> Dict:
        with self._lock:
            self._current_id += 1
            entry = {
                "id": self._current_id,
                "timestamp": datetime.now().isoformat(),
                "message": message,
            }
            self._logs.append(entry)
            if len(self._logs) > MAX_LOG_ENTRIES:
                self._logs = self._logs[-MAX_LOG_ENTRIES:]

        if self._broadcaster:
            try:
                self._broadcaster(entry)
            except Exception as exc:
                print(f"[Caffeinate] broadcaster failed: {exc}")

        return entry


_service_instance: Optional[CaffeinateService] = None


def get_service() -> CaffeinateService:
    global _service_instance
    if _service_instance is None:
        _service_instance = CaffeinateService()
    return _service_instance
