"""Browser Agent tab archive repository (SQLite).

This module stores persistent tab-archive records separately from the existing
browser_tab download queue table.
"""
from __future__ import annotations

import sqlite3
import json
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from shared.db import get_conn

TABLE_ARCHIVED_TAB = "browser_agent_archived_tab"
TABLE_TAB_LABEL = "browser_agent_tab_label"
TABLE_TAB_LABEL_REL = "browser_agent_archived_tab_label"
TABLE_ARCHIVE_BATCH = "browser_agent_tab_archive_batch"
TABLE_LIVE_FIRST_SEEN = "browser_agent_live_tab_first_seen"
TABLE_TAB_GROUP = "browser_agent_tab_group"          # legacy shared table, kept for migration
TABLE_LIVE_TAB_GROUP = "browser_agent_live_tab_group"
TABLE_SHELF_ITEM = "browser_agent_shelf_item"
TABLE_TAB_ACTIVATION = "browser_agent_tab_activation"
TABLE_LIVE_GROUP = "browser_agent_live_group"
TABLE_ARCHIVE_GROUP = "browser_agent_archive_group"
TABLE_SHELF_GROUP = "browser_agent_shelf_group"


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _conn() -> sqlite3.Connection:
    conn = get_conn()
    return conn


def init_db() -> None:
    conn = _conn()
    cur = conn.cursor()

    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_ARCHIVED_TAB} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            normalized_url TEXT UNIQUE NOT NULL,
            url TEXT NOT NULL,
            title TEXT DEFAULT '',
            domain TEXT DEFAULT '',
            favicon_url TEXT DEFAULT '',
            comment TEXT DEFAULT '',
            eternal INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            first_archived_at TEXT,
            last_archived_at TEXT,
            last_opened_at TEXT,
            last_seen_at TEXT,
            open_count INTEGER DEFAULT 0,
            archive_count INTEGER DEFAULT 0,
            health_status TEXT DEFAULT 'unchecked',
            last_checked_at TEXT,
            last_http_status INTEGER,
            final_url TEXT DEFAULT '',
            updated_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{TABLE_ARCHIVED_TAB}_domain "
        f"ON {TABLE_ARCHIVED_TAB}(domain)"
    )
    cur.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{TABLE_ARCHIVED_TAB}_eternal "
        f"ON {TABLE_ARCHIVED_TAB}(eternal)"
    )
    cur.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{TABLE_ARCHIVED_TAB}_opened "
        f"ON {TABLE_ARCHIVED_TAB}(last_opened_at)"
    )
    cur.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{TABLE_ARCHIVED_TAB}_archived "
        f"ON {TABLE_ARCHIVED_TAB}(last_archived_at)"
    )

    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_TAB_LABEL} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_TAB_LABEL_REL} (
            tab_id INTEGER NOT NULL,
            label_id INTEGER NOT NULL,
            PRIMARY KEY (tab_id, label_id)
        )
        """
    )

    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_ARCHIVE_BATCH} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            mode TEXT NOT NULL,
            requested_count INTEGER DEFAULT 0,
            persisted_count INTEGER DEFAULT 0,
            closed_count INTEGER DEFAULT 0,
            failed_count INTEGER DEFAULT 0
        )
        """
    )

    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_LIVE_FIRST_SEEN} (
            tab_id INTEGER PRIMARY KEY,
            first_seen_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_TAB_GROUP} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            scope TEXT NOT NULL DEFAULT 'archive',
            parent_id INTEGER REFERENCES {TABLE_TAB_GROUP}(id) ON DELETE CASCADE,
            display_order REAL NOT NULL DEFAULT 0.0,
            bookmark_id TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(scope, name)
        )
        """
    )

    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_LIVE_TAB_GROUP} (
            tab_id INTEGER PRIMARY KEY,
            group_id INTEGER NOT NULL REFERENCES {TABLE_TAB_GROUP}(id) ON DELETE CASCADE
        )
        """
    )

    # Self-heal: add group_id + display_order to archived tab table if missing
    cur.execute(f"PRAGMA table_info({TABLE_ARCHIVED_TAB})")
    existing_cols = {row["name"] for row in cur.fetchall()}
    if "group_id" not in existing_cols:
        cur.execute(
            f"ALTER TABLE {TABLE_ARCHIVED_TAB} "
            f"ADD COLUMN group_id INTEGER REFERENCES {TABLE_TAB_GROUP}(id) ON DELETE SET NULL"
        )
    if "display_order" not in existing_cols:
        cur.execute(
            f"ALTER TABLE {TABLE_ARCHIVED_TAB} ADD COLUMN display_order REAL NOT NULL DEFAULT 0.0"
        )

    # Self-heal: add parent_id + display_order to group table if missing
    cur.execute(f"PRAGMA table_info({TABLE_TAB_GROUP})")
    grp_cols = {row["name"] for row in cur.fetchall()}
    if "parent_id" not in grp_cols:
        cur.execute(
            f"ALTER TABLE {TABLE_TAB_GROUP} "
            f"ADD COLUMN parent_id INTEGER REFERENCES {TABLE_TAB_GROUP}(id) ON DELETE CASCADE"
        )
    if "display_order" not in grp_cols:
        cur.execute(
            f"ALTER TABLE {TABLE_TAB_GROUP} ADD COLUMN display_order REAL NOT NULL DEFAULT 0.0"
        )

    # One-time rebuild: introduce per-scope groups (scope column + UNIQUE(scope, name)).
    # The legacy schema declared `name TEXT NOT NULL UNIQUE`, which SQLite cannot relax via
    # ALTER, so when `scope` is absent we recreate the table and copy existing rows as
    # archive-scoped. Guarded by the missing column so it runs at most once per DB.
    if "scope" not in grp_cols:
        cur.execute("PRAGMA foreign_keys=OFF")
        cur.execute(
            f"""
            CREATE TABLE {TABLE_TAB_GROUP}_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                scope TEXT NOT NULL DEFAULT 'archive',
                parent_id INTEGER REFERENCES {TABLE_TAB_GROUP}_new(id) ON DELETE CASCADE,
                display_order REAL NOT NULL DEFAULT 0.0,
                bookmark_id TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(scope, name)
            )
            """
        )
        cur.execute(
            f"INSERT INTO {TABLE_TAB_GROUP}_new "
            f"(id, name, scope, parent_id, display_order, bookmark_id, created_at) "
            f"SELECT id, name, 'archive', parent_id, display_order, NULL, created_at "
            f"FROM {TABLE_TAB_GROUP}"
        )
        cur.execute(f"DROP TABLE {TABLE_TAB_GROUP}")
        cur.execute(f"ALTER TABLE {TABLE_TAB_GROUP}_new RENAME TO {TABLE_TAB_GROUP}")
        cur.execute("PRAGMA foreign_keys=ON")
    elif "bookmark_id" not in grp_cols:
        cur.execute(f"ALTER TABLE {TABLE_TAB_GROUP} ADD COLUMN bookmark_id TEXT")

    cur.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{TABLE_ARCHIVED_TAB}_group "
        f"ON {TABLE_ARCHIVED_TAB}(group_id)"
    )
    cur.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{TABLE_ARCHIVED_TAB}_display_order "
        f"ON {TABLE_ARCHIVED_TAB}(display_order)"
    )
    cur.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{TABLE_TAB_GROUP}_parent "
        f"ON {TABLE_TAB_GROUP}(parent_id)"
    )

    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_SHELF_ITEM} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER REFERENCES {TABLE_TAB_GROUP}(id) ON DELETE SET NULL,
            title TEXT,
            url TEXT NOT NULL,
            favicon_url TEXT,
            bookmark_id TEXT,
            display_order REAL NOT NULL DEFAULT 0.0,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{TABLE_SHELF_ITEM}_group "
        f"ON {TABLE_SHELF_ITEM}(group_id)"
    )

    # ---------- per-pane group tables (split from shared browser_agent_tab_group) ----------

    _PANE_GROUP_DDL = """
        CREATE TABLE IF NOT EXISTS {table} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            parent_id INTEGER REFERENCES {table}(id) ON DELETE CASCADE,
            display_order REAL NOT NULL DEFAULT 0.0,
            bookmark_id TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(name, parent_id)
        )
    """
    for _tbl in (TABLE_LIVE_GROUP, TABLE_ARCHIVE_GROUP, TABLE_SHELF_GROUP):
        cur.execute(_PANE_GROUP_DDL.format(table=_tbl))
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{_tbl}_parent ON {_tbl}(parent_id)"
        )

    # One-time migration: copy rows from legacy browser_agent_tab_group into the
    # three pane-specific tables.  Guarded by a sentinel row in browser_agent_archive_group
    # so it runs at most once even if init_db() is called multiple times.
    cur.execute(
        f"SELECT name FROM sqlite_master WHERE type='table' AND name='{TABLE_TAB_GROUP}'"
    )
    legacy_exists = cur.fetchone() is not None
    if legacy_exists:
        cur.execute(f"SELECT COUNT(*) AS n FROM {TABLE_ARCHIVE_GROUP}")
        already_migrated = cur.fetchone()["n"] > 0
        if not already_migrated:
            # Migrate archive-scoped groups (preserve ids via INSERT OR IGNORE)
            cur.execute(
                f"INSERT OR IGNORE INTO {TABLE_ARCHIVE_GROUP}"
                f"(id, name, parent_id, display_order, bookmark_id, created_at) "
                f"SELECT id, name, parent_id, display_order, bookmark_id, created_at "
                f"FROM {TABLE_TAB_GROUP} WHERE scope = 'archive'"
            )
            # Migrate live-scoped groups
            cur.execute(
                f"INSERT OR IGNORE INTO {TABLE_LIVE_GROUP}"
                f"(id, name, parent_id, display_order, bookmark_id, created_at) "
                f"SELECT id, name, parent_id, display_order, bookmark_id, created_at "
                f"FROM {TABLE_TAB_GROUP} WHERE scope = 'live'"
            )
            # Migrate shelf-scoped groups
            cur.execute(
                f"INSERT OR IGNORE INTO {TABLE_SHELF_GROUP}"
                f"(id, name, parent_id, display_order, bookmark_id, created_at) "
                f"SELECT id, name, parent_id, display_order, bookmark_id, created_at "
                f"FROM {TABLE_TAB_GROUP} WHERE scope = 'shelf'"
            )

    # Update archived_tab FK to point at archive_group
    cur.execute(f"PRAGMA table_info({TABLE_ARCHIVED_TAB})")
    at_cols = {r["name"] for r in cur.fetchall()}
    if "archive_group_id" not in at_cols:
        cur.execute(
            f"ALTER TABLE {TABLE_ARCHIVED_TAB} "
            f"ADD COLUMN archive_group_id INTEGER REFERENCES {TABLE_ARCHIVE_GROUP}(id) ON DELETE SET NULL"
        )
        # Back-fill from legacy group_id (same ids were preserved during migration)
        cur.execute(
            f"UPDATE {TABLE_ARCHIVED_TAB} SET archive_group_id = group_id WHERE group_id IS NOT NULL"
        )
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE_ARCHIVED_TAB}_archive_group "
            f"ON {TABLE_ARCHIVED_TAB}(archive_group_id)"
        )

    # Update shelf_item FK to point at shelf_group
    cur.execute(f"PRAGMA table_info({TABLE_SHELF_ITEM})")
    si_cols = {r["name"] for r in cur.fetchall()}
    if "shelf_group_id" not in si_cols:
        cur.execute(
            f"ALTER TABLE {TABLE_SHELF_ITEM} "
            f"ADD COLUMN shelf_group_id INTEGER REFERENCES {TABLE_SHELF_GROUP}(id) ON DELETE SET NULL"
        )
        cur.execute(
            f"UPDATE {TABLE_SHELF_ITEM} SET shelf_group_id = group_id WHERE group_id IS NOT NULL"
        )
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE_SHELF_ITEM}_shelf_group "
            f"ON {TABLE_SHELF_ITEM}(shelf_group_id)"
        )

    # Update live_tab_group FK to point at live_group
    cur.execute(f"PRAGMA table_info({TABLE_LIVE_TAB_GROUP})")
    ltg_cols = {r["name"] for r in cur.fetchall()}
    if "live_group_id" not in ltg_cols:
        cur.execute(
            f"ALTER TABLE {TABLE_LIVE_TAB_GROUP} "
            f"ADD COLUMN live_group_id INTEGER REFERENCES {TABLE_LIVE_GROUP}(id) ON DELETE CASCADE"
        )
        cur.execute(
            f"UPDATE {TABLE_LIVE_TAB_GROUP} SET live_group_id = group_id"
        )
    if "display_order" not in ltg_cols:
        cur.execute(
            f"ALTER TABLE {TABLE_LIVE_TAB_GROUP} ADD COLUMN display_order REAL"
        )
        # Back-fill: assign 1000-step order per group using Python loop (portable across SQLite versions)
        rows = cur.execute(
            f"SELECT tab_id, COALESCE(live_group_id, group_id) AS gid FROM {TABLE_LIVE_TAB_GROUP} ORDER BY COALESCE(live_group_id, group_id), tab_id"
        ).fetchall()
        prev_gid = None
        counter = 0
        for row in rows:
            if row["gid"] != prev_gid:
                counter = 0
                prev_gid = row["gid"]
            counter += 1
            cur.execute(
                f"UPDATE {TABLE_LIVE_TAB_GROUP} SET display_order = ? WHERE tab_id = ?",
                (counter * 1000.0, row["tab_id"]),
            )
    if "custom_header" not in ltg_cols:
        cur.execute(
            f"ALTER TABLE {TABLE_LIVE_TAB_GROUP} ADD COLUMN custom_header TEXT"
        )

    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_TAB_ACTIVATION} (
            url TEXT PRIMARY KEY,
            activation_count INTEGER NOT NULL DEFAULT 0,
            last_activated_at TEXT NOT NULL
        )
        """
    )

    conn.commit()
    conn.close()


def _row_to_record(row: sqlite3.Row) -> Dict[str, Any]:
    keys = row.keys()
    return {
        "id": int(row["id"]),
        "normalized_url": row["normalized_url"],
        "url": row["url"],
        "title": row["title"],
        "domain": row["domain"],
        "favicon_url": row["favicon_url"],
        "comment": row["comment"],
        "eternal": bool(row["eternal"]),
        "created_at": row["created_at"],
        "first_archived_at": row["first_archived_at"],
        "last_archived_at": row["last_archived_at"],
        "last_opened_at": row["last_opened_at"],
        "last_seen_at": row["last_seen_at"],
        "open_count": int(row["open_count"] or 0),
        "archive_count": int(row["archive_count"] or 0),
        "health_status": row["health_status"],
        "last_checked_at": row["last_checked_at"],
        "last_http_status": row["last_http_status"],
        "final_url": row["final_url"],
        "updated_at": row["updated_at"],
        "labels": [],
        "group_id": row["archive_group_id"] if "archive_group_id" in keys else (row["group_id"] if "group_id" in keys else None),
        "group_name": row["group_name"] if "group_name" in keys else None,
        "display_order": float(row["display_order"]) if "display_order" in keys else 0.0,
    }


def _load_labels_for_tab_ids(conn: sqlite3.Connection, tab_ids: Iterable[int]) -> Dict[int, List[str]]:
    ids = [int(x) for x in tab_ids]
    if not ids:
        return {}

    placeholders = ",".join(["?"] * len(ids))
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT rel.tab_id AS tab_id, lbl.name AS label_name
        FROM {TABLE_TAB_LABEL_REL} AS rel
        JOIN {TABLE_TAB_LABEL} AS lbl ON lbl.id = rel.label_id
        WHERE rel.tab_id IN ({placeholders})
        ORDER BY lbl.name ASC
        """,
        ids,
    )

    out: Dict[int, List[str]] = {}
    for row in cur.fetchall():
        tab_id = int(row["tab_id"])
        out.setdefault(tab_id, []).append(row["label_name"])
    return out


def _attach_labels(conn: sqlite3.Connection, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    labels_map = _load_labels_for_tab_ids(conn, [r["id"] for r in records])
    for record in records:
        record["labels"] = labels_map.get(record["id"], [])
    return records


def get_record_by_id(tab_id: int) -> Optional[Dict[str, Any]]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT t.*, g.name AS group_name
        FROM {TABLE_ARCHIVED_TAB} t
        LEFT JOIN {TABLE_ARCHIVE_GROUP} g ON g.id = t.archive_group_id
        WHERE t.id = ?
        """,
        (int(tab_id),),
    )
    row = cur.fetchone()
    if row is None:
        conn.close()
        return None
    record = _row_to_record(row)
    _attach_labels(conn, [record])
    conn.close()
    return record


def get_records_by_ids(tab_ids: List[int]) -> List[Dict[str, Any]]:
    ids = [int(x) for x in tab_ids]
    if not ids:
        return []

    conn = _conn()
    placeholders = ",".join(["?"] * len(ids))
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT t.*, g.name AS group_name
        FROM {TABLE_ARCHIVED_TAB} t
        LEFT JOIN {TABLE_ARCHIVE_GROUP} g ON g.id = t.archive_group_id
        WHERE t.id IN ({placeholders})
        """,
        ids,
    )
    rows = cur.fetchall()
    records = [_row_to_record(row) for row in rows]
    _attach_labels(conn, records)
    conn.close()
    return records


def get_records_by_normalized_urls(urls: List[str]) -> Dict[str, Dict[str, Any]]:
    clean_urls = [str(u).strip() for u in urls if str(u).strip()]
    if not clean_urls:
        return {}

    conn = _conn()
    placeholders = ",".join(["?"] * len(clean_urls))
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT t.*, g.name AS group_name
        FROM {TABLE_ARCHIVED_TAB} t
        LEFT JOIN {TABLE_ARCHIVE_GROUP} g ON g.id = t.archive_group_id
        WHERE t.normalized_url IN ({placeholders})
        """,
        clean_urls,
    )
    records = [_row_to_record(row) for row in cur.fetchall()]
    _attach_labels(conn, records)
    conn.close()
    return {record["normalized_url"]: record for record in records}


def list_records(
    query: str = "",
    eternal: Optional[bool] = None,
    health_status: Optional[str] = None,
    limit: int = 1000,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    limit_value = max(1, min(5000, int(limit)))
    offset_value = max(0, int(offset))

    where = []
    params: List[Any] = []

    q = query.strip()
    if q:
        pattern = f"%{q.lower()}%"
        where.append(
            "("  # nosec B608
            "LOWER(t.title) LIKE ? OR "
            "LOWER(t.comment) LIKE ? OR "
            "LOWER(t.domain) LIKE ? OR "
            "LOWER(t.url) LIKE ? OR "
            f"t.id IN (SELECT rel.tab_id FROM {TABLE_TAB_LABEL_REL} rel "
            f"JOIN {TABLE_TAB_LABEL} lbl ON lbl.id = rel.label_id WHERE LOWER(lbl.name) LIKE ?)"
            ")"
        )
        params.extend([pattern, pattern, pattern, pattern, pattern])

    if eternal is not None:
        where.append("t.eternal = ?")
        params.append(1 if eternal else 0)

    if health_status:
        where.append("t.health_status = ?")
        params.append(health_status.strip())

    sql = f"""
        SELECT t.*, g.name AS group_name
        FROM {TABLE_ARCHIVED_TAB} t
        LEFT JOIN {TABLE_ARCHIVE_GROUP} g ON g.id = t.archive_group_id
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY t.display_order ASC, t.id ASC"
    sql += " LIMIT ? OFFSET ?"
    params.extend([limit_value, offset_value])

    conn = _conn()
    cur = conn.cursor()
    cur.execute(sql, params)
    records = [_row_to_record(row) for row in cur.fetchall()]
    _attach_labels(conn, records)
    conn.close()
    return records


def upsert_from_live(
    *,
    normalized_url: str,
    url: str,
    title: str,
    domain: str,
    favicon_url: str,
    touch_seen_at: Optional[str] = None,
) -> Dict[str, Any]:
    now = _now_text()
    seen_at = touch_seen_at or now

    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        f"SELECT * FROM {TABLE_ARCHIVED_TAB} WHERE normalized_url = ?",
        (normalized_url,),
    )
    row = cur.fetchone()

    if row is None:
        cur.execute(
            f"""
            INSERT INTO {TABLE_ARCHIVED_TAB} (
                normalized_url, url, title, domain, favicon_url, comment,
                eternal, created_at, first_archived_at, last_archived_at,
                last_opened_at, last_seen_at, open_count, archive_count,
                health_status, last_checked_at, last_http_status,
                final_url, updated_at
            ) VALUES (?, ?, ?, ?, ?, '', 0, ?, NULL, NULL, NULL, ?, 0, 0,
                      'unchecked', NULL, NULL, '', ?)
            """,
            (
                normalized_url,
                url,
                title,
                domain,
                favicon_url,
                now,
                seen_at,
                now,
            ),
        )
        record_id = int(cur.lastrowid)
        conn.commit()
        conn.close()
        created = get_record_by_id(record_id)
        if created is None:
            raise RuntimeError("Failed to create archived tab record")
        return created

    existing = _row_to_record(row)
    next_title = (title or "").strip() or existing["title"]
    next_domain = (domain or "").strip() or existing["domain"]
    next_favicon = (favicon_url or "").strip() or existing["favicon_url"]
    next_url = (url or "").strip() or existing["url"]

    cur.execute(
        f"""
        UPDATE {TABLE_ARCHIVED_TAB}
        SET url = ?,
            title = ?,
            domain = ?,
            favicon_url = ?,
            last_seen_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            next_url,
            next_title,
            next_domain,
            next_favicon,
            seen_at,
            now,
            existing["id"],
        ),
    )
    conn.commit()
    conn.close()
    updated = get_record_by_id(existing["id"])
    if updated is None:
        raise RuntimeError("Failed to read updated archived tab record")
    return updated


def touch_existing_from_live(
    *,
    normalized_url: str,
    url: str,
    title: str,
    domain: str,
    favicon_url: str,
    touch_seen_at: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    now = _now_text()
    seen_at = touch_seen_at or now

    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        f"SELECT * FROM {TABLE_ARCHIVED_TAB} WHERE normalized_url = ?",
        (normalized_url,),
    )
    row = cur.fetchone()
    if row is None:
        conn.close()
        return None

    existing = _row_to_record(row)
    next_title = (title or "").strip() or existing["title"]
    next_domain = (domain or "").strip() or existing["domain"]
    next_favicon = (favicon_url or "").strip() or existing["favicon_url"]
    next_url = (url or "").strip() or existing["url"]

    cur.execute(
        f"""
        UPDATE {TABLE_ARCHIVED_TAB}
        SET url = ?,
            title = ?,
            domain = ?,
            favicon_url = ?,
            last_seen_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            next_url,
            next_title,
            next_domain,
            next_favicon,
            seen_at,
            now,
            existing["id"],
        ),
    )
    conn.commit()
    conn.close()
    return get_record_by_id(existing["id"])


def mark_archived(record_ids: List[int], timestamp_text: Optional[str] = None) -> None:
    ids = [int(x) for x in record_ids]
    if not ids:
        return

    ts = timestamp_text or _now_text()
    conn = _conn()
    placeholders = ",".join(["?"] * len(ids))
    cur = conn.cursor()
    cur.execute(
        f"""
        UPDATE {TABLE_ARCHIVED_TAB}
        SET first_archived_at = COALESCE(first_archived_at, ?),
            last_archived_at = ?,
            archive_count = archive_count + 1,
            updated_at = ?
        WHERE id IN ({placeholders})
        """,
        [ts, ts, ts] + ids,
    )
    conn.commit()
    conn.close()


def mark_opened(record_ids: List[int], timestamp_text: Optional[str] = None) -> None:
    ids = [int(x) for x in record_ids]
    if not ids:
        return

    ts = timestamp_text or _now_text()
    conn = _conn()
    placeholders = ",".join(["?"] * len(ids))
    cur = conn.cursor()
    cur.execute(
        f"""
        UPDATE {TABLE_ARCHIVED_TAB}
        SET last_opened_at = ?,
            last_seen_at = ?,
            open_count = open_count + 1,
            updated_at = ?
        WHERE id IN ({placeholders})
        """,
        [ts, ts, ts] + ids,
    )
    conn.commit()
    conn.close()


def update_record(tab_id: int, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    allowed = {
        "title": str,
        "comment": str,
        "eternal": bool,
        "health_status": str,
    }

    updates = []
    params: List[Any] = []
    for key, type_hint in allowed.items():
        if key not in patch:
            continue
        value = patch[key]
        if key == "eternal":
            value = 1 if bool(value) else 0
        elif type_hint is str:
            value = str(value or "").strip()
        updates.append(f"{key} = ?")
        params.append(value)

    if not updates:
        return get_record_by_id(tab_id)

    now = _now_text()
    updates.append("updated_at = ?")
    params.append(now)
    params.append(int(tab_id))

    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        f"UPDATE {TABLE_ARCHIVED_TAB} SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    conn.commit()
    conn.close()
    return get_record_by_id(tab_id)


def update_record_url(tab_id: int, *, url: str, domain: str, normalized_url: str) -> None:
    now = _now_text()
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        f"UPDATE {TABLE_ARCHIVED_TAB} SET url = ?, domain = ?, normalized_url = ?, updated_at = ? WHERE id = ?",
        (url, domain, normalized_url, now, int(tab_id)),
    )
    conn.commit()
    conn.close()


def delete_record(tab_id: int) -> bool:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM {TABLE_TAB_LABEL_REL} WHERE tab_id = ?", (int(tab_id),))
    cur.execute(f"DELETE FROM {TABLE_ARCHIVED_TAB} WHERE id = ?", (int(tab_id),))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return bool(deleted)


def list_labels() -> List[Dict[str, Any]]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"SELECT id, name, created_at FROM {TABLE_TAB_LABEL} ORDER BY name ASC")
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "id": int(row["id"]),
            "name": row["name"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def create_label(name: str) -> Dict[str, Any]:
    normalized = str(name or "").strip()
    if not normalized:
        raise ValueError("Label name is required")

    now = _now_text()
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        f"INSERT OR IGNORE INTO {TABLE_TAB_LABEL}(name, created_at) VALUES (?, ?)",
        (normalized, now),
    )
    conn.commit()

    cur.execute(f"SELECT id, name, created_at FROM {TABLE_TAB_LABEL} WHERE name = ?", (normalized,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        raise RuntimeError("Failed to create label")
    return {"id": int(row["id"]), "name": row["name"], "created_at": row["created_at"]}


def delete_label(label_id: int) -> bool:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM {TABLE_TAB_LABEL_REL} WHERE label_id = ?", (int(label_id),))
    cur.execute(f"DELETE FROM {TABLE_TAB_LABEL} WHERE id = ?", (int(label_id),))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return bool(deleted)


def set_record_labels(tab_id: int, label_ids: List[int]) -> None:
    ids = sorted({int(x) for x in label_ids})

    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM {TABLE_TAB_LABEL_REL} WHERE tab_id = ?", (int(tab_id),))

    for label_id in ids:
        cur.execute(
            f"INSERT OR IGNORE INTO {TABLE_TAB_LABEL_REL}(tab_id, label_id) VALUES (?, ?)",
            (int(tab_id), int(label_id)),
        )

    cur.execute(
        f"UPDATE {TABLE_ARCHIVED_TAB} SET updated_at = ? WHERE id = ?",
        (_now_text(), int(tab_id)),
    )

    conn.commit()
    conn.close()


def insert_archive_batch(
    mode: str,
    requested_count: int,
    persisted_count: int,
    closed_count: int,
    failed_count: int,
) -> int:
    now = _now_text()
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        f"""
        INSERT INTO {TABLE_ARCHIVE_BATCH}
        (created_at, mode, requested_count, persisted_count, closed_count, failed_count)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            now,
            str(mode or "selected"),
            int(requested_count),
            int(persisted_count),
            int(closed_count),
            int(failed_count),
        ),
    )
    batch_id = int(cur.lastrowid)
    conn.commit()
    conn.close()
    return batch_id


def sync_live_first_seen(current_tab_ids: List[int]) -> Dict[int, str]:
    """Insert first_seen_at for new tab_ids, delete rows for tabs no longer live.

    Returns a mapping of tab_id -> first_seen_at for all current tabs.
    """
    if not current_tab_ids:
        conn = _conn()
        cur = conn.cursor()
        cur.execute(f"DELETE FROM {TABLE_LIVE_FIRST_SEEN}")
        conn.commit()
        conn.close()
        return {}

    conn = _conn()
    cur = conn.cursor()
    now = _now_text()
    cur.executemany(
        f"INSERT OR IGNORE INTO {TABLE_LIVE_FIRST_SEEN}(tab_id, first_seen_at) VALUES (?, ?)",
        [(tid, now) for tid in current_tab_ids],
    )
    placeholders = ",".join("?" * len(current_tab_ids))
    cur.execute(
        f"DELETE FROM {TABLE_LIVE_FIRST_SEEN} WHERE tab_id NOT IN ({placeholders})",
        current_tab_ids,
    )
    cur.execute(
        f"SELECT tab_id, first_seen_at FROM {TABLE_LIVE_FIRST_SEEN} WHERE tab_id IN ({placeholders})",
        current_tab_ids,
    )
    rows = cur.fetchall()
    conn.commit()
    conn.close()
    return {int(row["tab_id"]): str(row["first_seen_at"]) for row in rows}


# ---------------------------------------------------------------------------
# Group CRUD (tree-aware)
# ---------------------------------------------------------------------------

def _group_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    keys = row.keys()
    return {
        "id": int(row["id"]),
        "name": row["name"],
        "scope": row["scope"] if "scope" in keys else "archive",
        "parent_id": int(row["parent_id"]) if row["parent_id"] is not None else None,
        "display_order": float(row["display_order"]),
        "bookmark_id": row["bookmark_id"] if "bookmark_id" in keys else None,
        "created_at": row["created_at"],
        "children": [],
    }


_GROUP_COLS = "id, name, scope, parent_id, display_order, bookmark_id, created_at"


def list_groups(parent_id: Optional[int] = None, scope: str = "archive") -> List[Dict[str, Any]]:
    """Return direct children of parent_id (or root groups if None) within a scope."""
    conn = _conn()
    cur = conn.cursor()
    if parent_id is None:
        cur.execute(
            f"SELECT {_GROUP_COLS} FROM {TABLE_TAB_GROUP} "
            f"WHERE scope = ? AND parent_id IS NULL ORDER BY display_order ASC, name ASC",
            (scope,),
        )
    else:
        cur.execute(
            f"SELECT {_GROUP_COLS} FROM {TABLE_TAB_GROUP} "
            f"WHERE scope = ? AND parent_id = ? ORDER BY display_order ASC, name ASC",
            (scope, int(parent_id)),
        )
    rows = cur.fetchall()
    conn.close()
    return [_group_row_to_dict(r) for r in rows]


def get_group_tree(scope: str = "archive") -> List[Dict[str, Any]]:
    """Return the full nested group tree for a single scope."""
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        f"SELECT {_GROUP_COLS} FROM {TABLE_TAB_GROUP} "
        f"WHERE scope = ? ORDER BY display_order ASC, name ASC",
        (scope,),
    )
    rows = cur.fetchall()
    conn.close()

    by_id: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        d = _group_row_to_dict(r)
        by_id[d["id"]] = d

    roots: List[Dict[str, Any]] = []
    for node in by_id.values():
        pid = node["parent_id"]
        if pid is None:
            roots.append(node)
        elif pid in by_id:
            by_id[pid]["children"].append(node)
        else:
            # Parent in a different scope (should not happen) — treat as root.
            roots.append(node)

    return roots


def _next_display_order(conn: sqlite3.Connection, parent_id: Optional[int], scope: str) -> float:
    cur = conn.cursor()
    if parent_id is None:
        cur.execute(
            f"SELECT MAX(display_order) AS m FROM {TABLE_TAB_GROUP} "
            f"WHERE scope = ? AND parent_id IS NULL",
            (scope,),
        )
    else:
        cur.execute(
            f"SELECT MAX(display_order) AS m FROM {TABLE_TAB_GROUP} "
            f"WHERE scope = ? AND parent_id = ?",
            (scope, int(parent_id)),
        )
    row = cur.fetchone()
    mx = row["m"] if row and row["m"] is not None else 0.0
    return float(mx) + 1000.0


def create_group(
    name: str,
    parent_id: Optional[int] = None,
    scope: str = "archive",
    display_order: Optional[float] = None,
) -> Dict[str, Any]:
    normalized = str(name or "").strip()
    if not normalized:
        raise ValueError("Group name is required")

    now = _now_text()
    conn = _conn()
    try:
        if display_order is None:
            display_order = _next_display_order(conn, parent_id, scope)
        cur = conn.cursor()
        try:
            cur.execute(
                f"INSERT INTO {TABLE_TAB_GROUP}(name, scope, parent_id, display_order, created_at) "
                f"VALUES (?, ?, ?, ?, ?)",
                (normalized, scope, parent_id, float(display_order), now),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"A group named '{normalized}' already exists in this scope") from exc
        conn.commit()
        gid = cur.lastrowid
        cur.execute(
            f"SELECT {_GROUP_COLS} FROM {TABLE_TAB_GROUP} WHERE id = ?",
            (gid,),
        )
        row = cur.fetchone()
    finally:
        conn.close()
    if row is None:
        raise RuntimeError("Failed to create group")
    return _group_row_to_dict(row)


def find_or_create_shelf_group(
    name: str, parent_id: Optional[int], bookmark_id: Optional[str] = None
) -> Dict[str, Any]:
    """Idempotently resolve a shelf-scoped group by (parent_id, name), creating if absent."""
    normalized = str(name or "").strip()
    if not normalized:
        raise ValueError("Group name is required")

    conn = _conn()
    cur = conn.cursor()
    if parent_id is None:
        cur.execute(
            f"SELECT {_GROUP_COLS} FROM {TABLE_TAB_GROUP} "
            f"WHERE scope = 'shelf' AND parent_id IS NULL AND name = ?",
            (normalized,),
        )
    else:
        cur.execute(
            f"SELECT {_GROUP_COLS} FROM {TABLE_TAB_GROUP} "
            f"WHERE scope = 'shelf' AND parent_id = ? AND name = ?",
            (int(parent_id), normalized),
        )
    row = cur.fetchone()
    if row is not None:
        existing = _group_row_to_dict(row)
        if bookmark_id and existing.get("bookmark_id") != bookmark_id:
            cur.execute(
                f"UPDATE {TABLE_TAB_GROUP} SET bookmark_id = ? WHERE id = ?",
                (bookmark_id, existing["id"]),
            )
            conn.commit()
            existing["bookmark_id"] = bookmark_id
        conn.close()
        existing["_created"] = False
        return existing

    now = _now_text()
    display_order = _next_display_order(conn, parent_id, "shelf")
    cur.execute(
        f"INSERT INTO {TABLE_TAB_GROUP}(name, scope, parent_id, display_order, bookmark_id, created_at) "
        f"VALUES (?, 'shelf', ?, ?, ?, ?)",
        (normalized, parent_id, float(display_order), bookmark_id, now),
    )
    conn.commit()
    gid = cur.lastrowid
    cur.execute(f"SELECT {_GROUP_COLS} FROM {TABLE_TAB_GROUP} WHERE id = ?", (gid,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        raise RuntimeError("Failed to create shelf group")
    created = _group_row_to_dict(row)
    created["_created"] = True
    return created


def rename_group(group_id: int, name: str) -> Optional[Dict[str, Any]]:
    normalized = str(name or "").strip()
    if not normalized:
        raise ValueError("Group name is required")

    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        f"UPDATE {TABLE_TAB_GROUP} SET name = ? WHERE id = ?",
        (normalized, int(group_id)),
    )
    conn.commit()
    cur.execute(
        f"SELECT {_GROUP_COLS} FROM {TABLE_TAB_GROUP} WHERE id = ?",
        (int(group_id),),
    )
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    return _group_row_to_dict(row)


def move_group(group_id: int, new_parent_id: Optional[int], new_display_order: float) -> Optional[Dict[str, Any]]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        f"UPDATE {TABLE_TAB_GROUP} SET parent_id = ?, display_order = ? WHERE id = ?",
        (new_parent_id, float(new_display_order), int(group_id)),
    )
    conn.commit()
    cur.execute(
        f"SELECT {_GROUP_COLS} FROM {TABLE_TAB_GROUP} WHERE id = ?",
        (int(group_id),),
    )
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    return _group_row_to_dict(row)


def delete_group(group_id: int) -> bool:
    conn = _conn()
    cur = conn.cursor()
    # ON DELETE CASCADE handles children and live_tab_group rows automatically
    # archive tab group_id goes NULL via ON DELETE SET NULL
    cur.execute(f"DELETE FROM {TABLE_TAB_GROUP} WHERE id = ?", (int(group_id),))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return bool(deleted)


# ---------------------------------------------------------------------------
# Per-pane group helpers (live / archive / shelf — fully independent tables)
# ---------------------------------------------------------------------------

def _pane_group_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    keys = row.keys()
    return {
        "id": int(row["id"]),
        "name": row["name"],
        "parent_id": int(row["parent_id"]) if row["parent_id"] is not None else None,
        "display_order": float(row["display_order"]),
        "bookmark_id": row["bookmark_id"] if "bookmark_id" in keys else None,
        "created_at": row["created_at"],
        "children": [],
    }


_PANE_GROUP_COLS = "id, name, parent_id, display_order, bookmark_id, created_at"


def _pane_next_display_order(conn: sqlite3.Connection, table: str, parent_id: Optional[int]) -> float:
    cur = conn.cursor()
    if parent_id is None:
        cur.execute(f"SELECT MAX(display_order) AS m FROM {table} WHERE parent_id IS NULL")
    else:
        cur.execute(f"SELECT MAX(display_order) AS m FROM {table} WHERE parent_id = ?", (int(parent_id),))
    row = cur.fetchone()
    mx = row["m"] if row and row["m"] is not None else 0.0
    return float(mx) + 1000.0


def _pane_list_groups(table: str, parent_id: Optional[int] = None) -> List[Dict[str, Any]]:
    conn = _conn()
    cur = conn.cursor()
    if parent_id is None:
        cur.execute(
            f"SELECT {_PANE_GROUP_COLS} FROM {table} WHERE parent_id IS NULL ORDER BY display_order ASC, name ASC"
        )
    else:
        cur.execute(
            f"SELECT {_PANE_GROUP_COLS} FROM {table} WHERE parent_id = ? ORDER BY display_order ASC, name ASC",
            (int(parent_id),),
        )
    rows = cur.fetchall()
    conn.close()
    return [_pane_group_row_to_dict(r) for r in rows]


def _pane_get_group_tree(table: str) -> List[Dict[str, Any]]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"SELECT {_PANE_GROUP_COLS} FROM {table} ORDER BY display_order ASC, name ASC")
    rows = cur.fetchall()
    conn.close()
    by_id: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        d = _pane_group_row_to_dict(r)
        by_id[d["id"]] = d
    roots: List[Dict[str, Any]] = []
    for node in by_id.values():
        pid = node["parent_id"]
        if pid is None:
            roots.append(node)
        elif pid in by_id:
            by_id[pid]["children"].append(node)
        else:
            roots.append(node)
    return roots


def _pane_create_group(
    table: str,
    name: str,
    parent_id: Optional[int] = None,
    display_order: Optional[float] = None,
    bookmark_id: Optional[str] = None,
) -> Dict[str, Any]:
    normalized = str(name or "").strip()
    if not normalized:
        raise ValueError("Group name is required")
    now = _now_text()
    conn = _conn()
    try:
        if display_order is None:
            display_order = _pane_next_display_order(conn, table, parent_id)
        cur = conn.cursor()
        try:
            cur.execute(
                f"INSERT INTO {table}(name, parent_id, display_order, bookmark_id, created_at) VALUES (?, ?, ?, ?, ?)",
                (normalized, parent_id, float(display_order), bookmark_id, now),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"A group named '{normalized}' already exists") from exc
        conn.commit()
        gid = cur.lastrowid
        cur.execute(f"SELECT {_PANE_GROUP_COLS} FROM {table} WHERE id = ?", (gid,))
        row = cur.fetchone()
    finally:
        conn.close()
    if row is None:
        raise RuntimeError("Failed to create group")
    return _pane_group_row_to_dict(row)


def _pane_rename_group(table: str, group_id: int, name: str) -> Optional[Dict[str, Any]]:
    normalized = str(name or "").strip()
    if not normalized:
        raise ValueError("Group name is required")
    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"UPDATE {table} SET name = ? WHERE id = ?", (normalized, int(group_id)))
    conn.commit()
    cur.execute(f"SELECT {_PANE_GROUP_COLS} FROM {table} WHERE id = ?", (int(group_id),))
    row = cur.fetchone()
    conn.close()
    return _pane_group_row_to_dict(row) if row else None


def _pane_move_group(table: str, group_id: int, new_parent_id: Optional[int], new_display_order: float) -> Optional[Dict[str, Any]]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        f"UPDATE {table} SET parent_id = ?, display_order = ? WHERE id = ?",
        (new_parent_id, float(new_display_order), int(group_id)),
    )
    conn.commit()
    cur.execute(f"SELECT {_PANE_GROUP_COLS} FROM {table} WHERE id = ?", (int(group_id),))
    row = cur.fetchone()
    conn.close()
    return _pane_group_row_to_dict(row) if row else None


def _pane_delete_group(table: str, group_id: int) -> bool:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM {table} WHERE id = ?", (int(group_id),))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return bool(deleted)


# -- Live group --

def live_list_groups(parent_id: Optional[int] = None) -> List[Dict[str, Any]]:
    return _pane_list_groups(TABLE_LIVE_GROUP, parent_id)

def live_get_group_tree() -> List[Dict[str, Any]]:
    return _pane_get_group_tree(TABLE_LIVE_GROUP)

def live_create_group(name: str, parent_id: Optional[int] = None, display_order: Optional[float] = None) -> Dict[str, Any]:
    return _pane_create_group(TABLE_LIVE_GROUP, name, parent_id, display_order)

def live_rename_group(group_id: int, name: str) -> Optional[Dict[str, Any]]:
    return _pane_rename_group(TABLE_LIVE_GROUP, group_id, name)

def live_move_group(group_id: int, new_parent_id: Optional[int], new_display_order: float) -> Optional[Dict[str, Any]]:
    return _pane_move_group(TABLE_LIVE_GROUP, group_id, new_parent_id, new_display_order)

def live_delete_group(group_id: int) -> bool:
    return _pane_delete_group(TABLE_LIVE_GROUP, group_id)


# -- Archive group --

def archive_list_groups(parent_id: Optional[int] = None) -> List[Dict[str, Any]]:
    return _pane_list_groups(TABLE_ARCHIVE_GROUP, parent_id)

def archive_get_group_tree() -> List[Dict[str, Any]]:
    return _pane_get_group_tree(TABLE_ARCHIVE_GROUP)

def archive_create_group(name: str, parent_id: Optional[int] = None, display_order: Optional[float] = None) -> Dict[str, Any]:
    return _pane_create_group(TABLE_ARCHIVE_GROUP, name, parent_id, display_order)

def archive_rename_group(group_id: int, name: str) -> Optional[Dict[str, Any]]:
    return _pane_rename_group(TABLE_ARCHIVE_GROUP, group_id, name)

def archive_move_group(group_id: int, new_parent_id: Optional[int], new_display_order: float) -> Optional[Dict[str, Any]]:
    return _pane_move_group(TABLE_ARCHIVE_GROUP, group_id, new_parent_id, new_display_order)

def archive_delete_group(group_id: int) -> bool:
    return _pane_delete_group(TABLE_ARCHIVE_GROUP, group_id)


# -- Shelf group --

def shelf_list_groups(parent_id: Optional[int] = None) -> List[Dict[str, Any]]:
    return _pane_list_groups(TABLE_SHELF_GROUP, parent_id)

def shelf_get_group_tree() -> List[Dict[str, Any]]:
    return _pane_get_group_tree(TABLE_SHELF_GROUP)

def shelf_create_group(name: str, parent_id: Optional[int] = None, display_order: Optional[float] = None, bookmark_id: Optional[str] = None) -> Dict[str, Any]:
    return _pane_create_group(TABLE_SHELF_GROUP, name, parent_id, display_order, bookmark_id)

def shelf_rename_group(group_id: int, name: str) -> Optional[Dict[str, Any]]:
    return _pane_rename_group(TABLE_SHELF_GROUP, group_id, name)

def shelf_move_group(group_id: int, new_parent_id: Optional[int], new_display_order: float) -> Optional[Dict[str, Any]]:
    return _pane_move_group(TABLE_SHELF_GROUP, group_id, new_parent_id, new_display_order)

def shelf_delete_group(group_id: int) -> bool:
    return _pane_delete_group(TABLE_SHELF_GROUP, group_id)

def shelf_find_or_create_group(name: str, parent_id: Optional[int], bookmark_id: Optional[str] = None) -> Dict[str, Any]:
    """Idempotently resolve a shelf group by (parent_id, name), creating if absent."""
    normalized = str(name or "").strip()
    if not normalized:
        raise ValueError("Group name is required")
    conn = _conn()
    cur = conn.cursor()
    if parent_id is None:
        cur.execute(
            f"SELECT {_PANE_GROUP_COLS} FROM {TABLE_SHELF_GROUP} WHERE parent_id IS NULL AND name = ?",
            (normalized,),
        )
    else:
        cur.execute(
            f"SELECT {_PANE_GROUP_COLS} FROM {TABLE_SHELF_GROUP} WHERE parent_id = ? AND name = ?",
            (int(parent_id), normalized),
        )
    row = cur.fetchone()
    if row is not None:
        existing = _pane_group_row_to_dict(row)
        if bookmark_id and existing.get("bookmark_id") != bookmark_id:
            cur.execute(
                f"UPDATE {TABLE_SHELF_GROUP} SET bookmark_id = ? WHERE id = ?",
                (bookmark_id, existing["id"]),
            )
            conn.commit()
            existing["bookmark_id"] = bookmark_id
        conn.close()
        existing["_created"] = False
        return existing
    now = _now_text()
    display_order = _pane_next_display_order(conn, TABLE_SHELF_GROUP, parent_id)
    cur.execute(
        f"INSERT INTO {TABLE_SHELF_GROUP}(name, parent_id, display_order, bookmark_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (normalized, parent_id, float(display_order), bookmark_id, now),
    )
    conn.commit()
    gid = cur.lastrowid
    cur.execute(f"SELECT {_PANE_GROUP_COLS} FROM {TABLE_SHELF_GROUP} WHERE id = ?", (gid,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        raise RuntimeError("Failed to create shelf group")
    created = _pane_group_row_to_dict(row)
    created["_created"] = True
    return created

def set_archive_record_group(record_id: int, group_id: Optional[int]) -> Optional[Dict[str, Any]]:
    now = _now_text()
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        f"UPDATE {TABLE_ARCHIVED_TAB} SET archive_group_id = ?, updated_at = ? WHERE id = ?",
        (group_id, now, int(record_id)),
    )
    conn.commit()
    conn.close()
    return get_record_by_id(record_id)


def set_archive_record_order(record_id: int, new_display_order: float) -> None:
    now = _now_text()
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        f"UPDATE {TABLE_ARCHIVED_TAB} SET display_order = ?, updated_at = ? WHERE id = ?",
        (float(new_display_order), now, int(record_id)),
    )
    conn.commit()
    conn.close()


def list_archive_records_ordered(group_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Return archive records ordered by display_order, optionally filtered by group."""
    conn = _conn()
    cur = conn.cursor()
    base = (
        f"SELECT t.*, g.name AS group_name "
        f"FROM {TABLE_ARCHIVED_TAB} t "
        f"LEFT JOIN {TABLE_ARCHIVE_GROUP} g ON g.id = t.archive_group_id"
    )
    if group_id is not None:
        cur.execute(base + " WHERE t.group_id = ? ORDER BY t.display_order ASC", (int(group_id),))
    else:
        cur.execute(base + " ORDER BY t.display_order ASC")
    rows = cur.fetchall()
    records = [_row_to_record(r) for r in rows]
    _attach_labels(conn, records)
    conn.close()
    return records


# ---------------------------------------------------------------------------
# Live tab group assignment
# ---------------------------------------------------------------------------

def set_live_tab_group(tab_id: int, group_id: Optional[int]) -> None:
    conn = _conn()
    cur = conn.cursor()
    if group_id is None:
        cur.execute(f"DELETE FROM {TABLE_LIVE_TAB_GROUP} WHERE tab_id = ?", (int(tab_id),))
    else:
        cur.execute(
            f"INSERT OR REPLACE INTO {TABLE_LIVE_TAB_GROUP}(tab_id, group_id, live_group_id) VALUES (?, ?, ?)",
            (int(tab_id), int(group_id), int(group_id)),
        )
    conn.commit()
    conn.close()


def set_live_tabs_group(tab_ids: List[int], group_id: Optional[int]) -> None:
    ids = [int(x) for x in tab_ids]
    if not ids:
        return

    conn = _conn()
    cur = conn.cursor()
    if group_id is None:
        placeholders = ",".join("?" * len(ids))
        cur.execute(f"DELETE FROM {TABLE_LIVE_TAB_GROUP} WHERE tab_id IN ({placeholders})", ids)
    else:
        cur.executemany(
            f"INSERT OR REPLACE INTO {TABLE_LIVE_TAB_GROUP}(tab_id, group_id, live_group_id) VALUES (?, ?, ?)",
            [(tid, int(group_id), int(group_id)) for tid in ids],
        )
    conn.commit()
    conn.close()


def set_live_tab_group_and_order(tab_id: int, group_id: Optional[int], display_order: float) -> None:
    """Set a live tab's group assignment and display_order in one atomic write."""
    conn = _conn()
    cur = conn.cursor()
    if group_id is None:
        cur.execute(
            f"INSERT OR REPLACE INTO {TABLE_LIVE_TAB_GROUP}(tab_id, group_id, live_group_id, display_order) VALUES (?, 0, NULL, ?)",
            (int(tab_id), display_order),
        )
    else:
        cur.execute(
            f"INSERT OR REPLACE INTO {TABLE_LIVE_TAB_GROUP}(tab_id, group_id, live_group_id, display_order) VALUES (?, ?, ?, ?)",
            (int(tab_id), int(group_id), int(group_id), display_order),
        )
    conn.commit()
    conn.close()


def batch_set_live_tab_orders(items: List[Dict[str, Any]]) -> None:
    """Batch-update group and display_order for multiple live tabs at once.

    Each item: {tab_id, group_id (int|None), display_order (float)}
    """
    if not items:
        return
    conn = _conn()
    cur = conn.cursor()
    for item in items:
        tab_id = int(item["tab_id"])
        group_id = item.get("group_id")
        display_order = float(item["display_order"])
        if group_id is None:
            cur.execute(
                f"INSERT OR REPLACE INTO {TABLE_LIVE_TAB_GROUP}(tab_id, group_id, live_group_id, display_order) VALUES (?, 0, NULL, ?)",
                (tab_id, display_order),
            )
        else:
            gid = int(group_id)
            cur.execute(
                f"INSERT OR REPLACE INTO {TABLE_LIVE_TAB_GROUP}(tab_id, group_id, live_group_id, display_order) VALUES (?, ?, ?, ?)",
                (tab_id, gid, gid, display_order),
            )
    conn.commit()
    conn.close()


def get_live_tab_groups(tab_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    ids = [int(x) for x in tab_ids]
    if not ids:
        return {}

    conn = _conn()
    cur = conn.cursor()
    placeholders = ",".join("?" * len(ids))
    cur.execute(
        f"SELECT tab_id, COALESCE(live_group_id, group_id) AS group_id, display_order "
        f"FROM {TABLE_LIVE_TAB_GROUP} WHERE tab_id IN ({placeholders})",
        ids,
    )
    rows = cur.fetchall()
    conn.close()
    return {
        int(r["tab_id"]): {"group_id": int(r["group_id"]) if r["group_id"] else None, "display_order": r["display_order"]}
        for r in rows if r["group_id"] is not None
    }


def set_live_tab_custom_header(tab_id: int, custom_header: Optional[str]) -> None:
    conn = _conn()
    cur = conn.cursor()
    value = custom_header.strip() if custom_header and custom_header.strip() else None
    cur.execute(
        f"INSERT INTO {TABLE_LIVE_TAB_GROUP}(tab_id, group_id, custom_header) VALUES (?, 0, ?) "
        f"ON CONFLICT(tab_id) DO UPDATE SET custom_header = excluded.custom_header",
        (int(tab_id), value),
    )
    conn.commit()
    conn.close()


def get_live_tab_custom_headers(tab_ids: List[int]) -> Dict[int, Optional[str]]:
    if not tab_ids:
        return {}
    conn = _conn()
    cur = conn.cursor()
    placeholders = ",".join("?" * len(tab_ids))
    cur.execute(
        f"SELECT tab_id, custom_header FROM {TABLE_LIVE_TAB_GROUP} WHERE tab_id IN ({placeholders})",
        [int(x) for x in tab_ids],
    )
    rows = cur.fetchall()
    conn.close()
    return {int(r["tab_id"]): r["custom_header"] for r in rows}


def sync_live_tab_groups(current_tab_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    """Delete rows for tabs no longer live; return current assignments."""
    if not current_tab_ids:
        conn = _conn()
        cur = conn.cursor()
        cur.execute(f"DELETE FROM {TABLE_LIVE_TAB_GROUP}")
        conn.commit()
        conn.close()
        return {}

    conn = _conn()
    cur = conn.cursor()
    placeholders = ",".join("?" * len(current_tab_ids))
    cur.execute(
        f"DELETE FROM {TABLE_LIVE_TAB_GROUP} WHERE tab_id NOT IN ({placeholders})",
        current_tab_ids,
    )
    cur.execute(
        f"SELECT tab_id, COALESCE(live_group_id, group_id) AS group_id, display_order "
        f"FROM {TABLE_LIVE_TAB_GROUP} WHERE tab_id IN ({placeholders})",
        current_tab_ids,
    )
    rows = cur.fetchall()
    conn.commit()
    conn.close()
    return {
        int(r["tab_id"]): {"group_id": int(r["group_id"]) if r["group_id"] else None, "display_order": r["display_order"]}
        for r in rows if r["group_id"] is not None
    }


# ---------------------------------------------------------------------------
# Tab activation (heat tracking)
# ---------------------------------------------------------------------------

def record_tab_activations(activations: List[Dict[str, Any]]) -> None:
    """Upsert activation counts. Each entry: {url, activation_count, last_activated_at}."""
    if not activations:
        return
    conn = _conn()
    cur = conn.cursor()
    for entry in activations:
        cur.execute(
            f"""
            INSERT INTO {TABLE_TAB_ACTIVATION}(url, activation_count, last_activated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                activation_count = activation_count + excluded.activation_count,
                last_activated_at = excluded.last_activated_at
            """,
            (entry["url"], int(entry.get("activation_count", 1)), entry["last_activated_at"]),
        )
    conn.commit()
    conn.close()


def get_tab_activations(urls: List[str]) -> Dict[str, Dict[str, Any]]:
    if not urls:
        return {}
    conn = _conn()
    cur = conn.cursor()
    placeholders = ",".join("?" * len(urls))
    cur.execute(
        f"SELECT url, activation_count, last_activated_at FROM {TABLE_TAB_ACTIVATION} "
        f"WHERE url IN ({placeholders})",
        urls,
    )
    rows = cur.fetchall()
    conn.close()
    return {
        r["url"]: {"activation_count": int(r["activation_count"]), "last_activated_at": r["last_activated_at"]}
        for r in rows
    }


# ---------------------------------------------------------------------------
# Shelf CRUD
# ---------------------------------------------------------------------------

def _shelf_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": int(row["id"]),
        "group_id": int(row["group_id"]) if row["group_id"] is not None else None,
        "title": row["title"],
        "url": row["url"],
        "favicon_url": row["favicon_url"],
        "bookmark_id": row["bookmark_id"],
        "display_order": float(row["display_order"]),
        "created_at": row["created_at"],
    }


def list_shelf_items(group_id: Optional[int] = None) -> List[Dict[str, Any]]:
    conn = _conn()
    cur = conn.cursor()
    if group_id is None:
        cur.execute(
            f"SELECT * FROM {TABLE_SHELF_ITEM} WHERE group_id IS NULL ORDER BY display_order ASC"
        )
    else:
        cur.execute(
            f"SELECT * FROM {TABLE_SHELF_ITEM} WHERE group_id = ? ORDER BY display_order ASC",
            (int(group_id),),
        )
    rows = cur.fetchall()
    conn.close()
    return [_shelf_row_to_dict(r) for r in rows]


def get_all_shelf_items() -> List[Dict[str, Any]]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {TABLE_SHELF_ITEM} ORDER BY display_order ASC")
    rows = cur.fetchall()
    conn.close()
    return [_shelf_row_to_dict(r) for r in rows]


def create_shelf_item(*, url: str, title: Optional[str] = None, favicon_url: Optional[str] = None,
                      group_id: Optional[int] = None, bookmark_id: Optional[str] = None,
                      display_order: Optional[float] = None) -> Dict[str, Any]:
    now = _now_text()
    conn = _conn()
    if display_order is None:
        cur = conn.cursor()
        if group_id is None:
            cur.execute(f"SELECT MAX(display_order) AS m FROM {TABLE_SHELF_ITEM} WHERE group_id IS NULL")
        else:
            cur.execute(f"SELECT MAX(display_order) AS m FROM {TABLE_SHELF_ITEM} WHERE group_id = ?", (int(group_id),))
        row = cur.fetchone()
        display_order = (float(row["m"]) + 1000.0) if row and row["m"] is not None else 0.0
    cur = conn.cursor()
    cur.execute(
        f"INSERT INTO {TABLE_SHELF_ITEM}(group_id, title, url, favicon_url, bookmark_id, display_order, created_at) "
        f"VALUES (?, ?, ?, ?, ?, ?, ?)",
        (group_id, title, url, favicon_url, bookmark_id, float(display_order), now),
    )
    conn.commit()
    iid = cur.lastrowid
    cur.execute(f"SELECT * FROM {TABLE_SHELF_ITEM} WHERE id = ?", (iid,))
    row = cur.fetchone()
    conn.close()
    return _shelf_row_to_dict(row)


def delete_shelf_item(item_id: int) -> bool:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM {TABLE_SHELF_ITEM} WHERE id = ?", (int(item_id),))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return bool(deleted)


def get_shelf_item(item_id: int) -> Optional[Dict[str, Any]]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {TABLE_SHELF_ITEM} WHERE id = ?", (int(item_id),))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    keys = [d[0] for d in cur.description]
    return dict(zip(keys, row))


def set_shelf_item_order(item_id: int, new_display_order: float) -> None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        f"UPDATE {TABLE_SHELF_ITEM} SET display_order = ? WHERE id = ?",
        (float(new_display_order), int(item_id)),
    )
    conn.commit()
    conn.close()


def set_shelf_item_group(item_id: int, group_id: Optional[int]) -> Optional[Dict[str, Any]]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        f"UPDATE {TABLE_SHELF_ITEM} SET shelf_group_id = ?, group_id = ? WHERE id = ?",
        (group_id, group_id, int(item_id)),
    )
    conn.commit()
    cur.execute(f"SELECT * FROM {TABLE_SHELF_ITEM} WHERE id = ?", (int(item_id),))
    row = cur.fetchone()
    conn.close()
    return _shelf_row_to_dict(row) if row else None


def upsert_shelf_item_by_bookmark_id(*, bookmark_id: str, url: str, title: Optional[str],
                                      favicon_url: Optional[str], group_id: Optional[int],
                                      display_order: float) -> Dict[str, Any]:
    """Insert or update a shelf item matched by bookmark_id."""
    now = _now_text()
    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"SELECT id FROM {TABLE_SHELF_ITEM} WHERE bookmark_id = ?", (bookmark_id,))
    existing = cur.fetchone()
    if existing:
        cur.execute(
            f"UPDATE {TABLE_SHELF_ITEM} SET url=?, title=?, favicon_url=?, group_id=?, display_order=? WHERE bookmark_id=?",
            (url, title, favicon_url, group_id, float(display_order), bookmark_id),
        )
        conn.commit()
        cur.execute(f"SELECT * FROM {TABLE_SHELF_ITEM} WHERE bookmark_id = ?", (bookmark_id,))
    else:
        cur.execute(
            f"INSERT INTO {TABLE_SHELF_ITEM}(bookmark_id, url, title, favicon_url, group_id, display_order, created_at) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?)",
            (bookmark_id, url, title, favicon_url, group_id, float(display_order), now),
        )
        conn.commit()
        cur.execute(f"SELECT * FROM {TABLE_SHELF_ITEM} WHERE id = ?", (cur.lastrowid,))
    row = cur.fetchone()
    conn.close()
    return _shelf_row_to_dict(row)

