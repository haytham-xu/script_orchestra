"""Apprentice — SQLite repository (self-healing schema)."""
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from shared.db import get_conn
from .entity import Task, MemoryShort, MemoryLong, HumanMessage, RedLine

_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS apprentice_task (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        repo_path TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        started_at TEXT,
        ended_at TEXT,
        pid INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS apprentice_memory_short (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER NOT NULL,
        raw_log TEXT NOT NULL,
        user_score INTEGER,
        user_note TEXT,
        created_at TEXT NOT NULL,
        distilled INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS apprentice_memory_long (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS apprentice_human_message (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER NOT NULL,
        direction TEXT NOT NULL,
        content TEXT NOT NULL,
        read_by_cmd INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS apprentice_integration_event (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER NOT NULL,
        source TEXT NOT NULL,
        event_type TEXT NOT NULL,
        payload TEXT NOT NULL,
        processed INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS apprentice_red_line (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
]


def _conn() -> sqlite3.Connection:
    conn = get_conn()
    conn.execute("PRAGMA journal_mode=WAL")
    for stmt in _SCHEMA:
        conn.execute(stmt)
    conn.commit()
    return conn


def init_db() -> None:
    conn = _conn()
    conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Task ────────────────────────────────────────────────────

def create_task(title: str, description: str, repo_path: str) -> Task:
    conn = _conn()
    now = _now()
    cur = conn.execute(
        "INSERT INTO apprentice_task (title, description, repo_path, status, created_at) VALUES (?,?,?,?,?)",
        (title, description, repo_path, "pending", now),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM apprentice_task WHERE id=?", (cur.lastrowid,)).fetchone()
    conn.close()
    return Task.from_row(row)


def get_task(task_id: int) -> Optional[Task]:
    conn = _conn()
    row = conn.execute("SELECT * FROM apprentice_task WHERE id=?", (task_id,)).fetchone()
    conn.close()
    return Task.from_row(row) if row else None


def list_tasks() -> list:
    conn = _conn()
    rows = conn.execute("SELECT * FROM apprentice_task ORDER BY id DESC").fetchall()
    conn.close()
    return [Task.from_row(r) for r in rows]


def update_task_status(task_id: int, status: str, pid: Optional[int] = None) -> None:
    conn = _conn()
    now = _now()
    if status == "running":
        conn.execute(
            "UPDATE apprentice_task SET status=?, started_at=?, pid=? WHERE id=?",
            (status, now, pid, task_id),
        )
    elif status in ("done", "failed", "stopped"):
        conn.execute(
            "UPDATE apprentice_task SET status=?, ended_at=? WHERE id=?",
            (status, now, task_id),
        )
    else:
        conn.execute("UPDATE apprentice_task SET status=? WHERE id=?", (status, task_id))
    conn.commit()
    conn.close()


# ── Memory short-term ────────────────────────────────────────

def append_short_memory(task_id: int, narrative: str) -> MemoryShort:
    conn = _conn()
    now = _now()
    cur = conn.execute(
        "INSERT INTO apprentice_memory_short (task_id, raw_log, created_at) VALUES (?,?,?)",
        (task_id, narrative, now),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM apprentice_memory_short WHERE id=?", (cur.lastrowid,)).fetchone()
    conn.close()
    return MemoryShort.from_row(row)


def update_short_memory_feedback(entry_id: int, score: Optional[int], note: Optional[str]) -> None:
    conn = _conn()
    conn.execute(
        "UPDATE apprentice_memory_short SET user_score=?, user_note=? WHERE id=?",
        (score, note, entry_id),
    )
    conn.commit()
    conn.close()


def list_short_memory() -> list:
    conn = _conn()
    rows = conn.execute("SELECT * FROM apprentice_memory_short ORDER BY id DESC").fetchall()
    conn.close()
    return [MemoryShort.from_row(r) for r in rows]


def get_undistilled_short_memory() -> list:
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM apprentice_memory_short WHERE distilled=0 ORDER BY id"
    ).fetchall()
    conn.close()
    return [MemoryShort.from_row(r) for r in rows]


def mark_distilled(entry_ids: list) -> None:
    if not entry_ids:
        return
    conn = _conn()
    placeholders = ",".join("?" * len(entry_ids))
    conn.execute(
        f"UPDATE apprentice_memory_short SET distilled=1 WHERE id IN ({placeholders})", entry_ids
    )
    conn.commit()
    conn.close()


# ── Memory long-term ─────────────────────────────────────────

def get_long_memory() -> Optional[MemoryLong]:
    conn = _conn()
    row = conn.execute("SELECT * FROM apprentice_memory_long ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return MemoryLong.from_row(row) if row else None


def upsert_long_memory(content: str) -> MemoryLong:
    conn = _conn()
    now = _now()
    existing = conn.execute("SELECT id FROM apprentice_memory_long LIMIT 1").fetchone()
    if existing:
        conn.execute(
            "UPDATE apprentice_memory_long SET content=?, updated_at=? WHERE id=?",
            (content, now, existing["id"]),
        )
        row_id = existing["id"]
    else:
        cur = conn.execute(
            "INSERT INTO apprentice_memory_long (content, updated_at) VALUES (?,?)", (content, now)
        )
        row_id = cur.lastrowid
    conn.commit()
    row = conn.execute("SELECT * FROM apprentice_memory_long WHERE id=?", (row_id,)).fetchone()
    conn.close()
    return MemoryLong.from_row(row)


# ── Human channel ─────────────────────────────────────────────

def post_human_message(task_id: int, direction: str, content: str) -> HumanMessage:
    conn = _conn()
    now = _now()
    cur = conn.execute(
        "INSERT INTO apprentice_human_message (task_id, direction, content, created_at) VALUES (?,?,?,?)",
        (task_id, direction, content, now),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM apprentice_human_message WHERE id=?", (cur.lastrowid,)).fetchone()
    conn.close()
    return HumanMessage.from_row(row)


def list_human_messages(task_id: int) -> list:
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM apprentice_human_message WHERE task_id=? ORDER BY id", (task_id,)
    ).fetchall()
    conn.close()
    return [HumanMessage.from_row(r) for r in rows]


def get_unread_user_messages(task_id: int) -> list:
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM apprentice_human_message WHERE task_id=? AND direction='user_to_cmd' AND read_by_cmd=0 ORDER BY id",
        (task_id,),
    ).fetchall()
    conn.close()
    return [HumanMessage.from_row(r) for r in rows]


def mark_messages_read(message_ids: list) -> None:
    if not message_ids:
        return
    conn = _conn()
    placeholders = ",".join("?" * len(message_ids))
    conn.execute(
        f"UPDATE apprentice_human_message SET read_by_cmd=1 WHERE id IN ({placeholders})", message_ids
    )
    conn.commit()
    conn.close()


# ── Red lines ─────────────────────────────────────────────────

def add_red_line(rule: str) -> RedLine:
    conn = _conn()
    now = _now()
    cur = conn.execute(
        "INSERT INTO apprentice_red_line (rule, created_at) VALUES (?,?)", (rule, now)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM apprentice_red_line WHERE id=?", (cur.lastrowid,)).fetchone()
    conn.close()
    return RedLine.from_row(row)


def list_red_lines() -> list:
    conn = _conn()
    rows = conn.execute("SELECT * FROM apprentice_red_line ORDER BY id").fetchall()
    conn.close()
    return [RedLine.from_row(r) for r in rows]


def delete_red_line(red_line_id: int) -> bool:
    conn = _conn()
    cur = conn.execute("DELETE FROM apprentice_red_line WHERE id=?", (red_line_id,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0
