"""Claude Bridge — message history repository.

Persists conversation messages to SQLite so sessions survive page navigation.
DB lives next to this file: claude_bridge/claude_bridge.db
"""
import os
import sqlite3
import time
from typing import List

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claude_bridge.db")

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL,
    payload     TEXT    NOT NULL,
    ts          REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
"""


def init_db() -> None:
    with sqlite3.connect(_DB_PATH) as conn:
        conn.executescript(_CREATE_SQL)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def save_message(session_id: str, payload: dict) -> None:
    import json
    with _conn() as conn:
        conn.execute(
            "INSERT INTO messages (session_id, payload, ts) VALUES (?, ?, ?)",
            (session_id, json.dumps(payload, ensure_ascii=False), time.time()),
        )


def get_messages(session_id: str) -> List[dict]:
    import json
    with _conn() as conn:
        rows = conn.execute(
            "SELECT payload FROM messages WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
    return [json.loads(r["payload"]) for r in rows]


def delete_session(session_id: str) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
