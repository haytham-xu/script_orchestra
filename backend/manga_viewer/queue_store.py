"""Manga Viewer — read-queue and snooze-queue persistence (SQLite)."""
import sqlite3
import time
from typing import Any, Dict, List

from shared.db import get_conn

_SNOOZE_DAYS = 7


def _conn() -> sqlite3.Connection:
    return get_conn()


def init_db() -> None:
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS manga_viewer_read_queue (
                folder_id TEXT PRIMARY KEY,
                added_at  REAL NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS manga_viewer_snooze_queue (
                folder_id  TEXT PRIMARY KEY,
                added_at   REAL NOT NULL,
                expires_at REAL NOT NULL
            )
        """)


# ── read queue ────────────────────────────────────────────────────────────────

def rq_add(folder_id: str) -> Dict[str, Any]:
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO manga_viewer_read_queue(folder_id, added_at) VALUES (?, ?)",
            (folder_id, time.time()),
        )
    return rq_get(folder_id)


def rq_remove(folder_id: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM manga_viewer_read_queue WHERE folder_id = ?", (folder_id,))


def rq_list() -> List[Dict[str, Any]]:
    with _conn() as c:
        rows = c.execute(
            "SELECT folder_id, added_at FROM manga_viewer_read_queue ORDER BY added_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def rq_ids() -> List[str]:
    with _conn() as c:
        rows = c.execute("SELECT folder_id FROM manga_viewer_read_queue").fetchall()
    return [r["folder_id"] for r in rows]


def rq_get(folder_id: str) -> Dict[str, Any]:
    with _conn() as c:
        row = c.execute(
            "SELECT folder_id, added_at FROM manga_viewer_read_queue WHERE folder_id = ?", (folder_id,)
        ).fetchone()
    if row is None:
        return {}
    return dict(row)


# ── snooze queue ──────────────────────────────────────────────────────────────

def sq_add(folder_id: str, days: int = _SNOOZE_DAYS) -> Dict[str, Any]:
    now = time.time()
    expires = now + days * 86400
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO manga_viewer_snooze_queue(folder_id, added_at, expires_at) VALUES (?, ?, ?)",
            (folder_id, now, expires),
        )
    return sq_get(folder_id)


def sq_remove(folder_id: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM manga_viewer_snooze_queue WHERE folder_id = ?", (folder_id,))


def sq_cleanup() -> int:
    """Delete expired entries. Returns number deleted."""
    with _conn() as c:
        cur = c.execute(
            "DELETE FROM manga_viewer_snooze_queue WHERE expires_at <= ?", (time.time(),)
        )
        return cur.rowcount


def sq_list() -> List[Dict[str, Any]]:
    """All snooze entries (expired and active), newest first."""
    with _conn() as c:
        rows = c.execute(
            "SELECT folder_id, added_at, expires_at FROM manga_viewer_snooze_queue ORDER BY added_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def sq_active_ids() -> List[str]:
    """Folder IDs currently snoozed (not yet expired)."""
    with _conn() as c:
        rows = c.execute(
            "SELECT folder_id FROM manga_viewer_snooze_queue WHERE expires_at > ?", (time.time(),)
        ).fetchall()
    return [r["folder_id"] for r in rows]


def sq_get(folder_id: str) -> Dict[str, Any]:
    with _conn() as c:
        row = c.execute(
            "SELECT folder_id, added_at, expires_at FROM manga_viewer_snooze_queue WHERE folder_id = ?",
            (folder_id,),
        ).fetchone()
    if row is None:
        return {}
    return dict(row)
