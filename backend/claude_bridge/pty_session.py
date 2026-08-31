"""Claude Bridge — PTY session (fallback / full-TUI route).

Spawns an interactive `claude` under a pseudo-terminal via stdlib `pty` (no extra
deps), forwards its raw output to the phone over WebSocket, and pipes phone
keystrokes back in. The phone renders it with xterm.js — this is the "real
terminal" fallback for when the Agent-SDK chat isn't enough (full TUI, its own
approval prompts, slash commands).

One background reader thread per session polls the PTY master fd with select and
emits chunks via the broadcaster. socketio.emit() is thread-safe in the app's
threading mode, so the reader can broadcast directly.
"""
import os
import pty
import select
import signal
import struct
import fcntl
import termios
import threading
import uuid
from typing import Callable, Optional

from . import config

_READ_CHUNK = 4096
_SELECT_TIMEOUT = 0.2


class PtySession:
    def __init__(self, pty_id: str, cwd: str, broadcaster: Callable[[dict], None]):
        self.id = pty_id
        self.cwd = cwd
        self._broadcaster = broadcaster
        self._closed = False

        env = dict(os.environ)
        # A real TERM is required or claude's TUI renders wrong.
        env.setdefault("TERM", "xterm-256color")
        env.setdefault("ANTHROPIC_BASE_URL", config.base_url())
        if config.AUTH_TOKEN and not env.get("ANTHROPIC_AUTH_TOKEN"):
            env["ANTHROPIC_AUTH_TOKEN"] = config.AUTH_TOKEN

        cli = config.cli_path()
        self.pid, self._fd = pty.fork()
        if self.pid == 0:
            # ---- child: become the interactive claude process ----
            try:
                os.chdir(cwd)
            except OSError:
                pass
            os.execvpe(cli, [cli], env)
            os._exit(127)  # execvpe only returns on failure

        # ---- parent: reader thread forwards PTY output ----
        self._thread = threading.Thread(
            target=self._read_loop, name=f"claude-bridge-pty-{pty_id}", daemon=True
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
            self._emit({"type": "cb_pty_output", "data": data.decode(errors="replace")})
        self._reap()
        self._emit({"type": "cb_pty_exit"})

    def _emit(self, payload: dict):
        payload = {"pty_id": self.id, **payload}
        try:
            self._broadcaster(payload)
        except Exception as exc:  # never let a broadcast error kill the reader
            print(f"[claude_bridge] pty broadcast failed: {exc}")

    # ---- inbound (from socketio thread) --------------------------------
    def write(self, data: str):
        if self._closed:
            return
        try:
            os.write(self._fd, data.encode())
        except OSError:
            pass

    def resize(self, cols: int, rows: int):
        if self._closed:
            return
        try:
            winsize = struct.pack("HHHH", int(rows), int(cols), 0, 0)
            fcntl.ioctl(self._fd, termios.TIOCSWINSZ, winsize)
        except OSError:
            pass

    def close(self):
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

    def _reap(self):
        try:
            os.waitpid(self.pid, os.WNOHANG)
        except OSError:
            pass

    def to_dict(self) -> dict:
        return {"pty_id": self.id, "cwd": self.cwd}


def new_pty_id() -> str:
    return uuid.uuid4().hex[:12]
