"""File Tracker — SQLite persistence.

Self-healing schema: CREATE TABLE IF NOT EXISTS on every _conn().
Upsert preserves user-managed status/note across re-scans.
"""
import os
import time

from shared.db import get_conn
from .entity import TrackedFile

_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS file_tracker_tracked_file (
        id          INTEGER PRIMARY KEY,
        path        TEXT UNIQUE NOT NULL,
        size_bytes  INTEGER DEFAULT 0,
        mtime       REAL    DEFAULT 0.0,
        atime       REAL    DEFAULT 0.0,
        last_active REAL    DEFAULT 0.0,
        status      TEXT    DEFAULT 'normal',
        scan_time   REAL    DEFAULT 0.0,
        note        TEXT    DEFAULT ''
    )""",
]

_COLS = 'id, path, size_bytes, mtime, atime, last_active, status, scan_time, note'


def _conn():
    conn = get_conn()
    for stmt in _SCHEMA:
        conn.execute(stmt)
    return conn


def init_db() -> None:
    conn = _conn()
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def upsert_file(path: str, size_bytes: int, mtime: float, atime: float,
                last_active: float, scan_time: float) -> None:
    """Insert or update filesystem metadata; never overwrite status/note."""
    conn = _conn()
    conn.execute("""
        INSERT INTO file_tracker_tracked_file (path, size_bytes, mtime, atime, last_active, scan_time)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            size_bytes  = excluded.size_bytes,
            mtime       = excluded.mtime,
            atime       = excluded.atime,
            last_active = excluded.last_active,
            scan_time   = excluded.scan_time
    """, (path, size_bytes, mtime, atime, last_active, scan_time))
    conn.commit()
    conn.close()


def update_file_status(fid: int, status: str = None, note: str = None) -> None:
    conn = _conn()
    sets, params = [], []
    if status is not None:
        sets.append('status = ?'); params.append(status)
    if note is not None:
        sets.append('note = ?'); params.append(note)
    if sets:
        params.append(fid)
        conn.execute(f'UPDATE file_tracker_tracked_file SET {", ".join(sets)} WHERE id = ?', params)
        conn.commit()
    conn.close()


def bulk_update_status(ids: list, status: str) -> None:
    if not ids:
        return
    conn = _conn()
    placeholders = ','.join('?' * len(ids))
    conn.execute(
        f'UPDATE file_tracker_tracked_file SET status = ? WHERE id IN ({placeholders})',
        [status] + list(ids),
    )
    conn.commit()
    conn.close()


def delete_file(fid: int) -> None:
    conn = _conn()
    conn.execute('DELETE FROM file_tracker_tracked_file WHERE id = ?', (fid,))
    conn.commit()
    conn.close()


def prune_missing() -> int:
    """Remove DB entries for paths that no longer exist on disk.
    Used by the manual 'Prune' button in Settings.
    """
    conn = _conn()
    cur = conn.cursor()
    cur.execute('SELECT id, path FROM file_tracker_tracked_file')
    rows = cur.fetchall()
    removed = 0
    for fid, path in rows:
        if not os.path.exists(path):
            conn.execute('DELETE FROM file_tracker_tracked_file WHERE id = ?', (fid,))
            removed += 1
    conn.commit()
    conn.close()
    return removed


def prune_by_scan_time(scan_time: float) -> int:
    """Remove entries not touched in the most recent scan pass.

    Any row whose scan_time is strictly older than the current scan_time
    was not seen during the scan (deleted, renamed, or newly ignored) and
    should be removed — unless the user has manually set its status to
    'ignored' or 'archived', in which case we keep it so the mark survives
    even if the path temporarily disappears.
    """
    conn = _conn()
    cur = conn.execute(
        "DELETE FROM file_tracker_tracked_file WHERE scan_time < ? AND status = 'normal'",
        (scan_time,),
    )
    removed = cur.rowcount
    conn.commit()
    conn.close()
    return removed


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def get_file(fid: int):
    conn = _conn()
    cur = conn.cursor()
    cur.execute(f'SELECT {_COLS} FROM file_tracker_tracked_file WHERE id = ?', (fid,))
    row = cur.fetchone()
    conn.close()
    return TrackedFile.from_row(row) if row else None


def get_files(
    status: str = 'all',
    min_age_days: float = None,
    max_age_days: float = None,
    sort: str = 'last_active',
    order: str = 'asc',
    page: int = 1,
    per_page: int = 200,
    q: str = None,
):
    """Return (list[TrackedFile], total_count) with optional filters."""
    now = time.time()
    wheres, params = [], []

    if status and status != 'all':
        wheres.append('status = ?')
        params.append(status)
    if min_age_days is not None:
        wheres.append('last_active <= ?')
        params.append(now - min_age_days * 86400)
    if max_age_days is not None:
        wheres.append('last_active >= ?')
        params.append(now - max_age_days * 86400)
    if q:
        wheres.append('path LIKE ?')
        params.append(f'%{q}%')

    where_sql = ('WHERE ' + ' AND '.join(wheres)) if wheres else ''
    safe_sort = sort if sort in ('last_active', 'size_bytes', 'path') else 'last_active'
    safe_order = 'DESC' if order == 'desc' else 'ASC'
    offset = (page - 1) * per_page

    conn = _conn()
    cur = conn.cursor()
    cur.execute(f'SELECT COUNT(*) FROM file_tracker_tracked_file {where_sql}', params)
    total = cur.fetchone()[0]
    cur.execute(
        f'SELECT {_COLS} FROM file_tracker_tracked_file {where_sql} '
        f'ORDER BY {safe_sort} {safe_order} LIMIT ? OFFSET ?',
        params + [per_page, offset],
    )
    rows = cur.fetchall()
    conn.close()
    return [TrackedFile.from_row(r) for r in rows], total


def get_stats():
    """Return aggregate counts/sizes by status."""
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT status, COUNT(*), SUM(size_bytes)
        FROM file_tracker_tracked_file
        GROUP BY status
    """)
    rows = cur.fetchall()
    cur.execute('SELECT COUNT(*), SUM(size_bytes) FROM file_tracker_tracked_file')
    total_row = cur.fetchone()
    conn.close()
    by_status = {r[0]: {'count': r[1], 'size': r[2] or 0} for r in rows}
    return {
        'total': total_row[0] or 0,
        'total_size': total_row[1] or 0,
        'by_status': by_status,
    }
