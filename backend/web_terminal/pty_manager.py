"""Web Terminal — PTY manager.

Owns the live {window_id -> _PtyProcess} map.
Each PTY spawns $SHELL under a pseudo-terminal via stdlib `pty`.
A background reader thread forwards raw output to scrollback + WebSocket.

Resource cleanup contract:
  - Shell exits naturally  → reader detects EOF → _reap() → remove from map
  - delete_window()        → kill SIGTERM → close fd → join reader (timeout=2s)
  - shutdown_all()         → called by Flask teardown
"""
import os
import pty
import select
import signal
import struct
import fcntl
import termios
import threading
import time
from typing import Callable, Optional

from . import scrollback_store

_READ_CHUNK = 4096
_SELECT_TIMEOUT = 0.2
_READER_JOIN_TIMEOUT = 2.0


class _PtyProcess:
    def __init__(self, window_id: str, cwd: str, broadcaster: Callable[[dict], None]):
        self.window_id = window_id
        self.cwd = cwd
        self._broadcaster = broadcaster
        self._closed = False
        self._lock = threading.Lock()

        shell = os.environ.get('SHELL', '/bin/zsh')
        env = dict(os.environ)
        env['TERM'] = 'xterm-256color'

        self.pid, self._fd = pty.fork()
        if self.pid == 0:
            try:
                os.chdir(cwd)
            except OSError:
                pass
            os.execvpe(shell, [shell], env)
            os._exit(127)

        self._thread = threading.Thread(
            target=self._read_loop,
            name=f'wt-pty-{window_id}',
            daemon=True,
        )
        self._thread.start()

    def _read_loop(self):
        while not self._closed:
            try:
                r, _, _ = select.select([self._fd], [], [], _SELECT_TIMEOUT)
            except (OSError, ValueError):
                break
            if not r:
                continue
            try:
                data = os.read(self._fd, _READ_CHUNK)
            except OSError:
                break
            if not data:
                break
            text = data.decode('utf-8', errors='replace')
            scrollback_store.append(self.window_id, text)
            self._emit('wt_output', {'data': text})
        self._reap()
        self._emit('wt_exit', {})

    def _emit(self, event: str, extra: dict):
        payload = {'window_id': self.window_id, 'event': event, **extra}
        try:
            self._broadcaster(payload)
        except Exception as e:
            print(f'[web_terminal] broadcast error: {e}')

    def write(self, data: str):
        with self._lock:
            if self._closed:
                return
            try:
                os.write(self._fd, data.encode())
            except OSError:
                pass

    def resize(self, cols: int, rows: int):
        with self._lock:
            if self._closed:
                return
            try:
                winsize = struct.pack('HHHH', rows, cols, 0, 0)
                fcntl.ioctl(self._fd, termios.TIOCSWINSZ, winsize)
            except OSError:
                pass

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                os.kill(self.pid, signal.SIGTERM)
            except OSError:
                pass
            try:
                os.close(self._fd)
            except OSError:
                pass

    def join(self, timeout: float = _READER_JOIN_TIMEOUT):
        self._thread.join(timeout=timeout)

    def _reap(self):
        try:
            os.waitpid(self.pid, os.WNOHANG)
        except OSError:
            pass

    @property
    def alive(self) -> bool:
        return not self._closed and self._thread.is_alive()


class PtyManager:
    def __init__(self):
        self._ptys: dict[str, _PtyProcess] = {}
        self._lock = threading.Lock()
        self._broadcaster: Optional[Callable[[dict], None]] = None

    def register_broadcaster(self, broadcaster: Callable[[dict], None]):
        self._broadcaster = broadcaster

    def _emit(self, payload: dict):
        if self._broadcaster:
            try:
                self._broadcaster(payload)
            except Exception:
                pass

    def attach(self, window_id: str, cwd: str) -> bool:
        """Spawn a new PTY for window_id. Returns False if one is already running."""
        with self._lock:
            existing = self._ptys.get(window_id)
            if existing and existing.alive:
                return False
            proc = _PtyProcess(window_id, cwd, self._emit)
            self._ptys[window_id] = proc
            return True

    def detach(self, window_id: str):
        """Kill PTY but keep the window (scrollback preserved)."""
        with self._lock:
            proc = self._ptys.pop(window_id, None)
        if proc:
            proc.close()
            proc.join()

    def write(self, window_id: str, data: str):
        proc = self._ptys.get(window_id)
        if proc:
            proc.write(data)

    def resize(self, window_id: str, cols: int, rows: int):
        proc = self._ptys.get(window_id)
        if proc:
            proc.resize(cols, rows)

    def is_alive(self, window_id: str) -> bool:
        proc = self._ptys.get(window_id)
        return proc is not None and proc.alive

    def shutdown_all(self):
        with self._lock:
            procs = list(self._ptys.values())
            self._ptys.clear()
        for proc in procs:
            proc.close()
        for proc in procs:
            proc.join(timeout=1.0)


_manager: Optional[PtyManager] = None


def get_manager() -> PtyManager:
    global _manager
    if _manager is None:
        _manager = PtyManager()
    return _manager
