"""Browser Agent — SQLite persistence for the download queue.

Ported from the 2023 browser_plugin prototype. Fixes the original
update bug (stored the Status enum object instead of its string value)
and reads the DB path from settings instead of a hardcoded location.
"""
import sqlite3
from datetime import datetime
from typing import List, Optional

from .entity import BrowserTab, Status
from . import settings_manager
from . import tab_archive_repository

TABLE = "browser_tab"


def _conn():
    return sqlite3.connect(settings_manager.get_db_path())


def init_db() -> None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            id INTEGER PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'TODO',
            retry_times INTEGER DEFAULT 0,
            file_name TEXT DEFAULT '',
            size INTEGER DEFAULT 0,
            download_link TEXT DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()

    # Initialize tab-archive schema in the same SQLite database.
    tab_archive_repository.init_db()


def _row_to_tab(row) -> BrowserTab:
    return BrowserTab(row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8])


def insert_browser_tab(tab: BrowserTab) -> None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"""
        INSERT INTO {TABLE}
        (code, created_at, updated_at, status, retry_times, file_name, size, download_link)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (tab.code, tab.created_at, tab.updated_at, tab.status,
          tab.retry_times, tab.file_name, tab.size, tab.download_link))
    conn.commit()
    conn.close()


def get_all() -> List[BrowserTab]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {TABLE} ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()
    return [_row_to_tab(r) for r in rows]


def get_all_need_downloaded() -> List[BrowserTab]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {TABLE} WHERE status IN (?, ?)",
                (Status.TODO.value, Status.FAILED.value))
    rows = cur.fetchall()
    conn.close()
    return [_row_to_tab(r) for r in rows]


def get_by_id(tab_id) -> Optional[BrowserTab]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {TABLE} WHERE id = ?", (tab_id,))
    row = cur.fetchone()
    conn.close()
    return _row_to_tab(row) if row else None


def get_by_code(code) -> Optional[BrowserTab]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {TABLE} WHERE code = ?", (code,))
    row = cur.fetchone()
    conn.close()
    return _row_to_tab(row) if row else None


def update_browser_tab(tab: BrowserTab) -> None:
    conn = _conn()
    cur = conn.cursor()
    # FIX: original stored tab.status (enum object). We store the string value.
    status_value = tab.status.value if isinstance(tab.status, Status) else tab.status
    cur.execute(f"""
        UPDATE {TABLE}
        SET updated_at = ?, status = ?, retry_times = ?, file_name = ?, size = ?
        WHERE id = ?
    """, (datetime.now(), status_value, tab.retry_times,
          tab.file_name, tab.size, tab.id))
    conn.commit()
    conn.close()


def delete_by_id(tab_id) -> None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM {TABLE} WHERE id = ?", (tab_id,))
    conn.commit()
    conn.close()
