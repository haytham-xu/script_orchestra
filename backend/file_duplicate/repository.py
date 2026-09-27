"""
File Duplicate — SQLite repository (shared DB, self-healing schema)
"""
from shared.db import get_conn

_CREATE_SQLS = [
    """
    CREATE TABLE IF NOT EXISTS file_duplicate_files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        root_id INTEGER NOT NULL,
        root_path TEXT NOT NULL,
        file_path TEXT NOT NULL UNIQUE,
        relative_path TEXT NOT NULL,
        filename TEXT NOT NULL,
        filesize INTEGER NOT NULL,
        mtime REAL NOT NULL,
        partial_hash TEXT,
        full_hash TEXT,
        hash_status TEXT NOT NULL DEFAULT 'pending'
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_fd_files_filesize ON file_duplicate_files(filesize)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_fd_files_partial ON file_duplicate_files(partial_hash)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_fd_files_full ON file_duplicate_files(full_hash)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_fd_files_root ON file_duplicate_files(root_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS file_duplicate_groups (
        group_hash TEXT PRIMARY KEY,
        filesize INTEGER NOT NULL,
        member_count INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS file_duplicate_meta (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """,
]


def _conn():
    conn = get_conn()
    for sql in _CREATE_SQLS:
        conn.execute(sql)
    return conn


def init_db() -> None:
    conn = _conn()
    conn.commit()
    conn.close()


# ── File entries ─────────────────────────────────────────────────────────────

def upsert_file(root_id: int, root_path: str, file_path: str, relative_path: str,
                filename: str, filesize: int, mtime: float) -> int:
    """Insert or update a file entry. Returns the row id."""
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO file_duplicate_files
            (root_id, root_path, file_path, relative_path, filename, filesize, mtime,
             partial_hash, full_hash, hash_status)
        VALUES (?,?,?,?,?,?,?, NULL, NULL, 'pending')
        ON CONFLICT(file_path) DO UPDATE SET
            filesize=excluded.filesize,
            mtime=excluded.mtime,
            root_id=excluded.root_id,
            root_path=excluded.root_path,
            partial_hash=CASE WHEN filesize != excluded.filesize OR mtime != excluded.mtime
                              THEN NULL ELSE partial_hash END,
            full_hash=CASE WHEN filesize != excluded.filesize OR mtime != excluded.mtime
                           THEN NULL ELSE full_hash END,
            hash_status=CASE WHEN filesize != excluded.filesize OR mtime != excluded.mtime
                             THEN 'pending' ELSE hash_status END
    """, (root_id, root_path, file_path, relative_path, filename, filesize, mtime))
    row_id = cur.lastrowid or get_file_id_by_path(file_path)
    conn.commit()
    conn.close()
    return row_id


def get_file_entry_by_id(file_id: int):
    """Return (file_path, relative_path) for the given file_id, or None."""
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT file_path, relative_path FROM file_duplicate_files WHERE id=?", (file_id,))
    row = cur.fetchone()
    conn.close()
    return (row[0], row[1]) if row else None


def get_file_id_by_path(file_path: str):
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM file_duplicate_files WHERE file_path=?", (file_path,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def delete_files_not_in(root_id: int, known_paths: list) -> int:
    """Remove DB rows for files under root_id that are no longer on disk. Returns deleted count."""
    if not known_paths:
        conn = _conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM file_duplicate_files WHERE root_id=?", (root_id,))
        count = cur.rowcount
        conn.commit()
        conn.close()
        return count
    # Use a temp table approach for large lists
    conn = _conn()
    cur = conn.cursor()
    cur.execute("CREATE TEMP TABLE IF NOT EXISTS _fd_keep_paths (p TEXT PRIMARY KEY)")
    cur.executemany("INSERT OR IGNORE INTO _fd_keep_paths VALUES (?)", [(p,) for p in known_paths])
    cur.execute("""
        DELETE FROM file_duplicate_files
        WHERE root_id=? AND file_path NOT IN (SELECT p FROM _fd_keep_paths)
    """, (root_id,))
    count = cur.rowcount
    cur.execute("DROP TABLE IF EXISTS _fd_keep_paths")
    conn.commit()
    conn.close()
    return count


def update_partial_hash(file_id: int, partial_hash: str) -> None:
    conn = _conn()
    conn.execute("""
        UPDATE file_duplicate_files SET partial_hash=?, hash_status='partial'
        WHERE id=?
    """, (partial_hash, file_id))
    conn.commit()
    conn.close()


def update_full_hash(file_id: int, full_hash: str) -> None:
    conn = _conn()
    conn.execute("""
        UPDATE file_duplicate_files SET full_hash=?, hash_status='full'
        WHERE id=?
    """, (full_hash, file_id))
    conn.commit()
    conn.close()


def bulk_update_partial_hashes(updates: list) -> None:
    """updates: list of (partial_hash, file_id)"""
    conn = _conn()
    conn.executemany("""
        UPDATE file_duplicate_files SET partial_hash=?, hash_status='partial' WHERE id=?
    """, updates)
    conn.commit()
    conn.close()


def bulk_update_full_hashes(updates: list) -> None:
    """updates: list of (full_hash, file_id)"""
    conn = _conn()
    conn.executemany("""
        UPDATE file_duplicate_files SET full_hash=?, hash_status='full' WHERE id=?
    """, updates)
    conn.commit()
    conn.close()


def get_files_needing_partial_hash(limit: int = 1000) -> list:
    """Files with same size as another file but no partial hash yet. Ordered by size desc."""
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, file_path, filesize FROM file_duplicate_files
        WHERE hash_status = 'pending'
          AND filesize > 0
          AND filesize IN (
              SELECT filesize FROM file_duplicate_files
              GROUP BY filesize HAVING COUNT(*) > 1
          )
        ORDER BY filesize DESC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows  # [(id, file_path, filesize), ...]


def get_files_needing_full_hash(limit: int = 1000) -> list:
    """Files where partial_hash matches another file but full_hash not yet computed."""
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, file_path, filesize FROM file_duplicate_files
        WHERE hash_status = 'partial'
          AND partial_hash IS NOT NULL
          AND partial_hash IN (
              SELECT partial_hash FROM file_duplicate_files
              WHERE partial_hash IS NOT NULL
              GROUP BY partial_hash HAVING COUNT(*) > 1
          )
        ORDER BY filesize DESC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows


def count_pending() -> dict:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT hash_status, COUNT(*) FROM file_duplicate_files GROUP BY hash_status
    """)
    rows = cur.fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}


def get_total_file_count() -> int:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM file_duplicate_files")
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0


def get_root_stats() -> list:
    """Per-root file count and indexing progress."""
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT root_id, root_path,
               COUNT(*) as total,
               SUM(CASE WHEN hash_status='full' THEN 1 ELSE 0 END) as indexed,
               SUM(filesize) as total_size
        FROM file_duplicate_files
        GROUP BY root_id, root_path
    """)
    rows = cur.fetchall()
    conn.close()
    return [{'root_id': r[0], 'root_path': r[1], 'total': r[2],
             'indexed': r[3], 'total_size': r[4]} for r in rows]


# ── Duplicate groups ──────────────────────────────────────────────────────────

def rebuild_groups() -> int:
    """Recompute file_duplicate_groups from full hashes. Returns group count."""
    conn = _conn()
    conn.execute("DELETE FROM file_duplicate_groups")
    conn.execute("""
        INSERT INTO file_duplicate_groups (group_hash, filesize, member_count)
        SELECT full_hash, filesize, COUNT(*) as cnt
        FROM file_duplicate_files
        WHERE full_hash IS NOT NULL
        GROUP BY full_hash
        HAVING cnt > 1
    """)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM file_duplicate_groups")
    count = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return count


def get_groups_page(page: int, page_size: int, sort_by: str = 'filesize',
                    sort_order: str = 'desc', root_filter: int = None) -> tuple:
    """Returns (groups_list, total_count). Each group includes member details."""
    valid_sorts = {'filesize', 'member_count'}
    if sort_by not in valid_sorts:
        sort_by = 'filesize'
    order = 'DESC' if sort_order == 'desc' else 'ASC'

    conn = _conn()
    cur = conn.cursor()

    # Count total
    if root_filter is not None:
        cur.execute("""
            SELECT COUNT(DISTINCT g.group_hash) FROM file_duplicate_groups g
            JOIN file_duplicate_files f ON f.full_hash = g.group_hash
            WHERE f.root_id = ?
        """, (root_filter,))
    else:
        cur.execute("SELECT COUNT(*) FROM file_duplicate_groups")
    total = cur.fetchone()[0]

    offset = (page - 1) * page_size

    if root_filter is not None:
        cur.execute(f"""
            SELECT DISTINCT g.group_hash, g.filesize, g.member_count
            FROM file_duplicate_groups g
            JOIN file_duplicate_files f ON f.full_hash = g.group_hash
            WHERE f.root_id = ?
            ORDER BY g.{sort_by} {order}
            LIMIT ? OFFSET ?
        """, (root_filter, page_size, offset))
    else:
        cur.execute(f"""
            SELECT group_hash, filesize, member_count
            FROM file_duplicate_groups
            ORDER BY {sort_by} {order}
            LIMIT ? OFFSET ?
        """, (page_size, offset))

    group_rows = cur.fetchall()
    groups = []
    for (group_hash, filesize, member_count) in group_rows:
        cur.execute("""
            SELECT id, root_id, root_path, file_path, relative_path, filename,
                   filesize, mtime, partial_hash, full_hash, hash_status
            FROM file_duplicate_files WHERE full_hash=?
            ORDER BY root_id ASC, file_path ASC
        """, (group_hash,))
        members = cur.fetchall()
        from .entity import FileEntry
        member_dicts = [FileEntry.from_row(m).to_dict() for m in members]
        root_ids = list({m['root_id'] for m in member_dicts})
        groups.append({
            'group_hash': group_hash,
            'filesize': filesize,
            'member_count': member_count,
            'members': member_dicts,
            'root_ids': root_ids,
        })

    conn.close()
    return groups, total


def get_group_stats() -> dict:
    """High-level stats: total groups, total duplicate files, total wasted space."""
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*), SUM(member_count), SUM(filesize * (member_count - 1))
        FROM file_duplicate_groups
    """)
    row = cur.fetchone()
    conn.close()
    return {
        'total_groups': row[0] or 0,
        'total_duplicate_files': row[1] or 0,
        'wasted_bytes': row[2] or 0,
    }


def get_root_duplicate_stats() -> list:
    """Per-root: how many files are duplicates and how much space could be freed."""
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT f.root_id, f.root_path,
               COUNT(*) as dup_file_count,
               SUM(f.filesize) as dup_total_size
        FROM file_duplicate_files f
        JOIN file_duplicate_groups g ON f.full_hash = g.group_hash
        GROUP BY f.root_id, f.root_path
    """)
    rows = cur.fetchall()
    conn.close()
    return [{'root_id': r[0], 'root_path': r[1],
             'dup_file_count': r[2], 'dup_total_size': r[3]} for r in rows]


# ── File mutations ────────────────────────────────────────────────────────────

def remove_file_entry(file_id: int) -> None:
    conn = _conn()
    conn.execute("DELETE FROM file_duplicate_files WHERE id=?", (file_id,))
    conn.commit()
    conn.close()


def remove_file_entries(file_ids: list) -> None:
    conn = _conn()
    conn.executemany("DELETE FROM file_duplicate_files WHERE id=?", [(i,) for i in file_ids])
    conn.commit()
    conn.close()


def update_file_path(file_id: int, new_path: str, new_root_path: str,
                     new_root_id: int, new_relative: str) -> None:
    conn = _conn()
    conn.execute("""
        UPDATE file_duplicate_files
        SET file_path=?, root_path=?, root_id=?, relative_path=?
        WHERE id=?
    """, (new_path, new_root_path, new_root_id, new_relative, file_id))
    conn.commit()
    conn.close()


# ── Meta ─────────────────────────────────────────────────────────────────────

def set_meta(key: str, value: str) -> None:
    conn = _conn()
    conn.execute("INSERT OR REPLACE INTO file_duplicate_meta VALUES (?,?)", (key, value))
    conn.commit()
    conn.close()


def get_meta(key: str) -> str | None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT value FROM file_duplicate_meta WHERE key=?", (key,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None
