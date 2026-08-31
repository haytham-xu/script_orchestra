"""Claude Bridge — session manager (singleton, mirrors browser_agent/service.py).

Owns the live {session_id -> AgentSession} map and the single broadcaster wired
in by app.py. All websocket/HTTP handlers funnel through get_manager().
"""
import uuid
from typing import Callable, Optional

from . import config
from .agent_runner import AgentSession
from .pty_session import PtySession, new_pty_id


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, AgentSession] = {}
        self._ptys: dict[str, PtySession] = {}
        self._broadcaster: Optional[Callable[[dict], None]] = None

    def register_broadcaster(self, broadcaster: Callable[[dict], None]) -> None:
        self._broadcaster = broadcaster

    def _emit(self, payload: dict) -> None:
        if self._broadcaster:
            self._broadcaster(payload)

    # ---- lifecycle ------------------------------------------------------
    def create_session(self, cwd: Optional[str] = None,
                        model: Optional[str] = None) -> AgentSession:
        cwd = cwd or config.DEFAULT_CWD
        if not config.cwd_allowed(cwd):
            raise ValueError(f"cwd not allowed: {cwd}")
        session_id = uuid.uuid4().hex[:12]
        session = AgentSession(session_id, cwd, model or config.DEFAULT_MODEL, self._emit)
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> Optional[AgentSession]:
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[dict]:
        return [s.to_dict() for s in self._sessions.values()]

    def close_session(self, session_id: str) -> bool:
        session = self._sessions.pop(session_id, None)
        if not session:
            return False
        session.close()
        return True

    # ---- inbound actions (from websocket handlers) ----------------------
    def submit(self, session_id: str, text: str) -> None:
        s = self._sessions.get(session_id)
        if s:
            s.submit(text)

    def resolve_permission(self, session_id: str, request_id: str, decision: str) -> None:
        s = self._sessions.get(session_id)
        if s:
            s.resolve_permission(request_id, decision)

    def interrupt(self, session_id: str) -> None:
        s = self._sessions.get(session_id)
        if s:
            s.interrupt()

    def set_model(self, session_id: str, model: str) -> None:
        s = self._sessions.get(session_id)
        if s:
            s.set_model(model)

    # ---- PTY sessions ---------------------------------------------------
    def create_pty(self, cwd: Optional[str] = None) -> PtySession:
        cwd = cwd or config.DEFAULT_CWD
        if not config.cwd_allowed(cwd):
            raise ValueError(f"cwd not allowed: {cwd}")
        pty_id = new_pty_id()
        pty = PtySession(pty_id, cwd, self._emit)
        self._ptys[pty_id] = pty
        return pty

    def pty_write(self, pty_id: str, data: str) -> None:
        p = self._ptys.get(pty_id)
        if p:
            p.write(data)

    def pty_resize(self, pty_id: str, cols: int, rows: int) -> None:
        p = self._ptys.get(pty_id)
        if p:
            p.resize(cols, rows)

    def close_pty(self, pty_id: str) -> bool:
        p = self._ptys.pop(pty_id, None)
        if not p:
            return False
        p.close()
        return True

    def list_ptys(self) -> list[dict]:
        return [p.to_dict() for p in self._ptys.values()]


_manager: Optional[SessionManager] = None


def get_manager() -> SessionManager:
    global _manager
    if _manager is None:
        _manager = SessionManager()
    return _manager
