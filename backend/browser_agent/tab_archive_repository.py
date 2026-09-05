"""Browser Agent tab archive repository (SQLite).

This module stores persistent tab-archive records separately from the existing
browser_tab download queue table.
"""
from __future__ import annotations

import sqlite3
import json
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from . import settings_manager

TABLE_ARCHIVED_TAB = "archived_tab"
TABLE_TAB_LABEL = "tab_label"
TABLE_TAB_LABEL_REL = "archived_tab_label"
TABLE_ARCHIVE_BATCH = "tab_archive_batch"
TABLE_TAB_VECTOR = "tab_archive_vector"


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(settings_manager.get_db_path())
    conn.row_factory = sqlite3.Row
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
        CREATE TABLE IF NOT EXISTS {TABLE_TAB_VECTOR} (
            tab_id INTEGER PRIMARY KEY,
            embedding TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            model_name TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    conn.commit()
    conn.close()


def _row_to_record(row: sqlite3.Row) -> Dict[str, Any]:
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
    cur.execute(f"SELECT * FROM {TABLE_ARCHIVED_TAB} WHERE id = ?", (int(tab_id),))
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
        f"SELECT * FROM {TABLE_ARCHIVED_TAB} WHERE id IN ({placeholders})",
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
        f"SELECT * FROM {TABLE_ARCHIVED_TAB} WHERE normalized_url IN ({placeholders})",
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
            "LOWER(title) LIKE ? OR "
            "LOWER(comment) LIKE ? OR "
            "LOWER(domain) LIKE ? OR "
            "LOWER(url) LIKE ? OR "
            f"id IN (SELECT rel.tab_id FROM {TABLE_TAB_LABEL_REL} rel "
            f"JOIN {TABLE_TAB_LABEL} lbl ON lbl.id = rel.label_id WHERE LOWER(lbl.name) LIKE ?)"
            ")"
        )
        params.extend([pattern, pattern, pattern, pattern, pattern])

    if eternal is not None:
        where.append("eternal = ?")
        params.append(1 if eternal else 0)

    if health_status:
        where.append("health_status = ?")
        params.append(health_status.strip())

    sql = f"SELECT * FROM {TABLE_ARCHIVED_TAB}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY COALESCE(last_opened_at, last_archived_at, created_at) DESC, id DESC"
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
    cur.execute(f"DELETE FROM {TABLE_TAB_VECTOR} WHERE tab_id = ?", (int(tab_id),))
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


def list_records_for_health(limit: int = 200) -> List[Dict[str, Any]]:
    limit_value = max(1, min(1000, int(limit)))
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT * FROM {TABLE_ARCHIVED_TAB}
        ORDER BY COALESCE(last_checked_at, '1970-01-01 00:00:00') ASC, id DESC
        LIMIT ?
        """,
        (limit_value,),
    )
    records = [_row_to_record(row) for row in cur.fetchall()]
    _attach_labels(conn, records)
    conn.close()
    return records


def update_record_health(
    tab_id: int,
    *,
    health_status: str,
    checked_at: str,
    last_http_status: Optional[int] = None,
    final_url: str = "",
) -> Optional[Dict[str, Any]]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        f"""
        UPDATE {TABLE_ARCHIVED_TAB}
        SET health_status = ?,
            last_checked_at = ?,
            last_http_status = ?,
            final_url = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            str(health_status or "unknown"),
            str(checked_at),
            last_http_status,
            str(final_url or ""),
            _now_text(),
            int(tab_id),
        ),
    )
    affected = cur.rowcount
    conn.commit()
    conn.close()
    if affected <= 0:
        return None
    return get_record_by_id(tab_id)


def get_vector_record(tab_id: int) -> Optional[Dict[str, Any]]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        f"SELECT tab_id, embedding, content_hash, model_name, updated_at FROM {TABLE_TAB_VECTOR} WHERE tab_id = ?",
        (int(tab_id),),
    )
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    try:
        vector = json.loads(row["embedding"])
    except Exception:
        vector = []
    return {
        "tab_id": int(row["tab_id"]),
        "embedding": [float(x) for x in vector if isinstance(x, (int, float))],
        "content_hash": str(row["content_hash"] or ""),
        "model_name": str(row["model_name"] or ""),
        "updated_at": str(row["updated_at"] or ""),
    }


def upsert_vector(
    tab_id: int,
    embedding: List[float],
    content_hash: str,
    model_name: str,
) -> None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        f"""
        INSERT INTO {TABLE_TAB_VECTOR}(tab_id, embedding, content_hash, model_name, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(tab_id) DO UPDATE SET
            embedding = excluded.embedding,
            content_hash = excluded.content_hash,
            model_name = excluded.model_name,
            updated_at = excluded.updated_at
        """,
        (
            int(tab_id),
            json.dumps([float(x) for x in embedding], ensure_ascii=False),
            str(content_hash or ""),
            str(model_name or ""),
            _now_text(),
        ),
    )
    conn.commit()
    conn.close()


def get_vectors(tab_ids: Optional[List[int]] = None) -> List[Dict[str, Any]]:
    conn = _conn()
    cur = conn.cursor()
    params: List[Any] = []
    sql = f"SELECT tab_id, embedding, content_hash, model_name, updated_at FROM {TABLE_TAB_VECTOR}"
    if tab_ids is not None:
        ids = [int(x) for x in tab_ids]
        if not ids:
            conn.close()
            return []
        placeholders = ",".join(["?"] * len(ids))
        sql += f" WHERE tab_id IN ({placeholders})"
        params.extend(ids)
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()

    result: List[Dict[str, Any]] = []
    for row in rows:
        try:
            vector = json.loads(row["embedding"])
        except Exception:
            continue
        result.append(
            {
                "tab_id": int(row["tab_id"]),
                "embedding": [float(x) for x in vector if isinstance(x, (int, float))],
                "content_hash": str(row["content_hash"] or ""),
                "model_name": str(row["model_name"] or ""),
                "updated_at": str(row["updated_at"] or ""),
            }
        )
    return result
