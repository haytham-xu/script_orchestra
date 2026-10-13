"""Browser Agent — SQLite persistence for the download queue.

Ported from the 2023 browser_plugin prototype. Fixes the original
update bug (stored the Status enum object instead of its string value)
and reads the DB path from settings instead of a hardcoded location.
"""
from datetime import datetime
from typing import List, Optional

from shared.db import get_conn
from .entity import BrowserTab, Status
from . import tab_archive_repository

TABLE = "browser_agent_browser_tab"
TABLE_HISTORY = "browser_agent_download_history"
TABLE_SSMH_LOG = "browser_agent_ssmh_download_log"
TABLE_SSMH_SCAN = "browser_agent_ssmh_scan_cache"


def _conn():
    return get_conn()


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
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_HISTORY} (
            id INTEGER PRIMARY KEY,
            url_path TEXT UNIQUE NOT NULL,
            source_type TEXT NOT NULL,
            downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_SSMH_LOG} (
            id INTEGER PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source_url TEXT NOT NULL,
            dl_type TEXT NOT NULL DEFAULT '',
            method TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            filename TEXT DEFAULT '',
            error_msg TEXT DEFAULT ''
        )
    """)
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_SSMH_SCAN} (
            url_path TEXT PRIMARY KEY,
            dl_type TEXT NOT NULL,
            first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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


def is_path_downloaded(url_path: str) -> bool:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"SELECT 1 FROM {TABLE_HISTORY} WHERE url_path = ?", (url_path,))
    found = cur.fetchone() is not None
    conn.close()
    return found


def record_downloaded_path(url_path: str, source_type: str) -> None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        f"INSERT OR IGNORE INTO {TABLE_HISTORY} (url_path, source_type) VALUES (?, ?)",
        (url_path, source_type),
    )
    conn.commit()
    conn.close()


def log_ssmh_download(source_url: str, dl_type: str, method: str,
                      status: str, filename: str = '', error_msg: str = '') -> None:
    """Record one download attempt (one row per method tried per file)."""
    try:
        conn = _conn()
        cur = conn.cursor()
        cur.execute(
            f"INSERT INTO {TABLE_SSMH_LOG} "
            "(source_url, dl_type, method, status, filename, error_msg) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (source_url, dl_type, method, status, filename, error_msg),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # logging must never crash the caller


def get_ssmh_scan_type(url_path: str) -> Optional[str]:
    """Return cached dl_type for this path, or None if not yet classified."""
    try:
        conn = _conn()
        cur = conn.cursor()
        cur.execute(
            f"SELECT dl_type FROM {TABLE_SSMH_SCAN} WHERE url_path = ?", (url_path,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def upsert_ssmh_scan_type(url_path: str, dl_type: str) -> None:
    """Store or update the dl_type for a scanned path."""
    try:
        conn = _conn()
        cur = conn.cursor()
        cur.execute(
            f"INSERT INTO {TABLE_SSMH_SCAN} (url_path, dl_type) VALUES (?, ?) "
            "ON CONFLICT(url_path) DO UPDATE SET dl_type=excluded.dl_type, "
            "updated_at=CURRENT_TIMESTAMP",
            (url_path, dl_type),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
