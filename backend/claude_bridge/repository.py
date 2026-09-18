"""Claude Bridge — message history repository.

Persists conversation messages to SQLite so sessions survive page navigation.
"""
import sqlite3
import time
from typing import List

from shared.db import get_conn

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS claude_bridge_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL,
    payload     TEXT    NOT NULL,
    ts          REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_claude_bridge_messages_session ON claude_bridge_messages(session_id, id);
"""


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(_CREATE_SQL)


def _conn() -> sqlite3.Connection:
    conn = get_conn()
    return conn


def save_message(session_id: str, payload: dict) -> None:
    import json
    with _conn() as conn:
        conn.execute(
            "INSERT INTO claude_bridge_messages (session_id, payload, ts) VALUES (?, ?, ?)",
            (session_id, json.dumps(payload, ensure_ascii=False), time.time()),
        )


def get_messages(session_id: str) -> List[dict]:
    import json
    with _conn() as conn:
        rows = conn.execute(
            "SELECT payload FROM claude_bridge_messages WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
    return [json.loads(r["payload"]) for r in rows]


def delete_session(session_id: str) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM claude_bridge_messages WHERE session_id = ?", (session_id,))
