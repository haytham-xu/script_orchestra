"""Web Terminal — SQLite repository (window metadata only, not content).

Table: web_terminal_window
Schema is self-healing: applied on every _conn() via CREATE TABLE IF NOT EXISTS.
"""
import time
import uuid
from typing import Optional

from shared.db import get_conn
from .entity import TerminalWindow

_DDL = """
CREATE TABLE IF NOT EXISTS web_terminal_window (
    window_id   TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT '',
    cwd         TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL,
    last_active REAL NOT NULL
);
"""


def init_db():
    with get_conn() as conn:
        conn.executescript(_DDL)


def create_window(title: str, cwd: str) -> TerminalWindow:
    now = time.time()
    wid = uuid.uuid4().hex[:12]
    win = TerminalWindow(window_id=wid, title=title, cwd=cwd,
                         created_at=now, last_active=now)
    with get_conn() as conn:
        conn.execute(
            'INSERT INTO web_terminal_window (window_id, title, cwd, created_at, last_active) '
            'VALUES (?, ?, ?, ?, ?)',
            (win.window_id, win.title, win.cwd, win.created_at, win.last_active),
        )
    return win


def list_windows() -> list[TerminalWindow]:
    with get_conn() as conn:
        rows = conn.execute(
            'SELECT * FROM web_terminal_window ORDER BY last_active DESC'
        ).fetchall()
    return [TerminalWindow.from_row(r) for r in rows]


def get_window(window_id: str) -> Optional[TerminalWindow]:
    with get_conn() as conn:
        row = conn.execute(
            'SELECT * FROM web_terminal_window WHERE window_id = ?', (window_id,)
        ).fetchone()
    return TerminalWindow.from_row(row) if row else None


def touch_window(window_id: str):
    with get_conn() as conn:
        conn.execute(
            'UPDATE web_terminal_window SET last_active = ? WHERE window_id = ?',
            (time.time(), window_id),
        )


def delete_window(window_id: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            'DELETE FROM web_terminal_window WHERE window_id = ?', (window_id,)
        )
    return cur.rowcount > 0
