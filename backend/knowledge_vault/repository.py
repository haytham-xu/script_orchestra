"""Knowledge Vault — SQLite persistence.

raw_fragment is append-only (soft-archive, never hard-delete).
fragment_vector stores embeddings for semantic search.
Tables self-heal on every connection.
"""
import json
import sqlite3
from datetime import datetime
from typing import List, Optional

from .entity import RawFragment, FragmentGroup
from shared.db import get_conn

_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS knowledge_vault_raw_fragment (
        id INTEGER PRIMARY KEY,
        content TEXT NOT NULL,
        note TEXT DEFAULT '',
        raw_text TEXT DEFAULT '',
        kind TEXT DEFAULT '',
        created_at TEXT,
        archived INTEGER DEFAULT 0,
        last_accessed TEXT,
        header TEXT DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS knowledge_vault_fragment_vector (
        fragment_id INTEGER PRIMARY KEY,
        vector TEXT NOT NULL,
        content_hash TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS knowledge_vault_label (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        color TEXT DEFAULT '#8e8e93'
    )""",
    """CREATE TABLE IF NOT EXISTS knowledge_vault_fragment_label (
        fragment_id INTEGER NOT NULL,
        label_id INTEGER NOT NULL,
        PRIMARY KEY (fragment_id, label_id)
    )""",
    """CREATE TABLE IF NOT EXISTS knowledge_vault_fragment_group (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        note TEXT DEFAULT '',
        parent_id INTEGER,
        created_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS knowledge_vault_fragment_group_member (
        fragment_id INTEGER NOT NULL,
        group_id INTEGER NOT NULL,
        PRIMARY KEY (fragment_id, group_id)
    )""",
]


def _conn():
    conn = get_conn()
    for stmt in _SCHEMA:
        conn.execute(stmt)
    _maybe_add_content_hash(conn)
    _maybe_add_header(conn)
    return conn


def _maybe_add_content_hash(conn) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(knowledge_vault_fragment_vector)")}
    if "content_hash" not in cols:
        conn.execute("ALTER TABLE knowledge_vault_fragment_vector ADD COLUMN content_hash TEXT")


def _maybe_add_header(conn) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(knowledge_vault_raw_fragment)")}
    if "header" not in cols:
        conn.execute("ALTER TABLE knowledge_vault_raw_fragment ADD COLUMN header TEXT DEFAULT ''")


def init_db() -> None:
    conn = _conn()
    conn.commit()
    conn.close()


# ---- raw_fragment (append-only) --------------------------------------

_RF_COLS = "id, content, note, raw_text, kind, created_at, archived, last_accessed, header"


def insert_fragment(f: RawFragment) -> RawFragment:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""INSERT INTO knowledge_vault_raw_fragment
        (content, note, raw_text, kind, created_at, archived, last_accessed, header)
        VALUES (?,?,?,?,?,?,?,?)""",
        (f.content_storage(), f.note, f.raw_text, f.kind, f.created_at, f.archived,
         f.last_accessed, f.header or ""))
    f.id = cur.lastrowid
    conn.commit()
    conn.close()
    return f


def get_fragments(include_archived=False, archived_only=False, ungrouped_only=False) -> List[RawFragment]:
    conn = _conn()
    cur = conn.cursor()
    q = f"SELECT {_RF_COLS} FROM knowledge_vault_raw_fragment"
    conditions = []
    if archived_only:
        conditions.append("archived = 1")
    elif not include_archived:
        conditions.append("archived = 0")
    if ungrouped_only:
        conditions.append("id NOT IN (SELECT fragment_id FROM knowledge_vault_fragment_group_member)")
    if conditions:
        q += " WHERE " + " AND ".join(conditions)
    q += " ORDER BY id DESC"
    cur.execute(q)
    rows = cur.fetchall()
    cur.execute("SELECT fragment_id, label_id FROM knowledge_vault_fragment_label")
    label_map = {}
    for frag_id, label_id in cur.fetchall():
        label_map.setdefault(frag_id, []).append(label_id)
    cur.execute("SELECT fragment_id, group_id FROM knowledge_vault_fragment_group_member")
    group_map = {frag_id: group_id for frag_id, group_id in cur.fetchall()}
    conn.close()
    frags = [RawFragment.from_row(r) for r in rows]
    for f in frags:
        f.label_ids = label_map.get(f.id, [])
        f.group_id = group_map.get(f.id)
    return frags


def get_fragment(fid) -> Optional[RawFragment]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"SELECT {_RF_COLS} FROM knowledge_vault_raw_fragment WHERE id = ?", (fid,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    cur.execute("SELECT label_id FROM knowledge_vault_fragment_label WHERE fragment_id = ?", (fid,))
    label_ids = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT group_id FROM knowledge_vault_fragment_group_member WHERE fragment_id = ?", (fid,))
    grp = cur.fetchone()
    conn.close()
    f = RawFragment.from_row(row)
    f.label_ids = label_ids
    f.group_id = grp[0] if grp else None
    return f


def update_fragment(fid, content=None, note=None, header=None) -> None:
    conn = _conn()
    sets, params = [], []
    if content is not None:
        sets.append("content = ?"); params.append(content)
    if note is not None:
        sets.append("note = ?"); params.append(note)
    if header is not None:
        sets.append("header = ?"); params.append(header)
    if sets:
        params.append(fid)
        conn.execute(f"UPDATE knowledge_vault_raw_fragment SET {', '.join(sets)} WHERE id = ?", params)
        conn.commit()
    conn.close()


def archive_fragment(fid) -> None:
    conn = _conn()
    conn.execute("UPDATE knowledge_vault_raw_fragment SET archived = 1 WHERE id = ?", (fid,))
    conn.commit()
    conn.close()


def unarchive_fragment(fid) -> None:
    conn = _conn()
    conn.execute("UPDATE knowledge_vault_raw_fragment SET archived = 0 WHERE id = ?", (fid,))
    conn.commit()
    conn.close()


def delete_fragment(fid) -> None:
    conn = _conn()
    conn.execute("DELETE FROM knowledge_vault_raw_fragment WHERE id = ?", (fid,))
    conn.execute("DELETE FROM knowledge_vault_fragment_vector WHERE fragment_id = ?", (fid,))
    conn.execute("DELETE FROM knowledge_vault_fragment_group_member WHERE fragment_id = ?", (fid,))
    conn.commit()
    conn.close()


def touch_fragment(fid) -> None:
    conn = _conn()
    conn.execute("UPDATE knowledge_vault_raw_fragment SET last_accessed = ? WHERE id = ?",
                 (datetime.now().isoformat(), fid))
    conn.commit()
    conn.close()


# ---- vectors ----------------------------------------------------------

def save_vector(fragment_id: int, vector: List[float], content_hash: str = None) -> None:
    conn = _conn()
    conn.execute(
        "INSERT OR REPLACE INTO knowledge_vault_fragment_vector (fragment_id, vector, content_hash) VALUES (?, ?, ?)",
        (fragment_id, json.dumps(vector), content_hash))
    conn.commit()
    conn.close()


def get_all_vectors() -> List[tuple]:
    """Returns [(fragment_id, [floats])] for non-archived fragments."""
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""SELECT v.fragment_id, v.vector FROM knowledge_vault_fragment_vector v
                   JOIN knowledge_vault_raw_fragment f ON f.id = v.fragment_id
                   WHERE f.archived = 0""")
    rows = cur.fetchall()
    conn.close()
    return [(r[0], json.loads(r[1])) for r in rows]


# ---- labels (user-managed tags; a fragment may have many) --------------

def get_labels() -> List[dict]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT id, name, color FROM knowledge_vault_label ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "color": r[2]} for r in rows]


def create_label(name: str, color: str = "#8e8e93") -> dict:
    conn = _conn()
    cur = conn.cursor()
    # case-insensitive duplicate check
    cur.execute("SELECT id, name, color FROM knowledge_vault_label WHERE LOWER(name) = LOWER(?)", (name,))
    row = cur.fetchone()
    if row:
        conn.close()
        return {"id": row[0], "name": row[1], "color": row[2], "existing": True}
    cur.execute("INSERT INTO knowledge_vault_label (name, color) VALUES (?, ?)", (name, color))
    lid = cur.lastrowid
    conn.commit()
    conn.close()
    return {"id": lid, "name": name, "color": color}


def update_label(label_id: int, name: str = None, color: str = None) -> Optional[dict]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT id, name, color FROM knowledge_vault_label WHERE id = ?", (label_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    new_name = name if name is not None else row[1]
    new_color = color if color is not None else row[2]
    cur.execute("UPDATE knowledge_vault_label SET name = ?, color = ? WHERE id = ?", (new_name, new_color, label_id))
    conn.commit()
    conn.close()
    return {"id": label_id, "name": new_name, "color": new_color}


def delete_label(label_id: int) -> None:
    conn = _conn()
    conn.execute("DELETE FROM knowledge_vault_label WHERE id = ?", (label_id,))
    conn.execute("DELETE FROM knowledge_vault_fragment_label WHERE label_id = ?", (label_id,))
    conn.commit()
    conn.close()


def set_fragment_labels(fragment_id: int, label_ids: List[int]) -> None:
    conn = _conn()
    conn.execute("DELETE FROM knowledge_vault_fragment_label WHERE fragment_id = ?", (fragment_id,))
    for lid in label_ids:
        conn.execute("INSERT OR IGNORE INTO knowledge_vault_fragment_label (fragment_id, label_id) VALUES (?, ?)",
                     (fragment_id, lid))
    conn.commit()
    conn.close()


# ---- fragment groups --------------------------------------------------

_FG_COLS = "id, name, note, parent_id, created_at"


def insert_group(g: FragmentGroup) -> FragmentGroup:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO knowledge_vault_fragment_group (name, note, parent_id, created_at) VALUES (?,?,?,?)",
        (g.name, g.note or "", g.parent_id, g.created_at))
    g.id = cur.lastrowid
    conn.commit()
    conn.close()
    return g


def get_groups() -> List[FragmentGroup]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"SELECT {_FG_COLS} FROM knowledge_vault_fragment_group ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    return [FragmentGroup.from_row(r) for r in rows]


def get_group(gid) -> Optional[FragmentGroup]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"SELECT {_FG_COLS} FROM knowledge_vault_fragment_group WHERE id = ?", (gid,))
    row = cur.fetchone()
    conn.close()
    return FragmentGroup.from_row(row) if row else None


_UNSET = object()


def update_group(gid, name=None, note=None, parent_id=_UNSET) -> None:
    conn = _conn()
    sets, params = [], []
    if name is not None:
        sets.append("name = ?"); params.append(name)
    if note is not None:
        sets.append("note = ?"); params.append(note)
    if parent_id is not _UNSET:
        sets.append("parent_id = ?"); params.append(parent_id)
    if sets:
        params.append(gid)
        conn.execute(f"UPDATE knowledge_vault_fragment_group SET {', '.join(sets)} WHERE id = ?", params)
        conn.commit()
    conn.close()


def delete_group(gid) -> None:
    conn = _conn()
    conn.execute("DELETE FROM knowledge_vault_fragment_group WHERE id = ?", (gid,))
    conn.execute("DELETE FROM knowledge_vault_fragment_group_member WHERE group_id = ?", (gid,))
    conn.commit()
    conn.close()


def set_group_members(group_id: int, fragment_ids: List[int]) -> None:
    conn = _conn()
    # Remove fragment from any other group first (a fragment belongs to at most one group)
    if fragment_ids:
        placeholders = ",".join("?" * len(fragment_ids))
        conn.execute(
            f"DELETE FROM knowledge_vault_fragment_group_member WHERE fragment_id IN ({placeholders})",
            fragment_ids)
    conn.execute("DELETE FROM knowledge_vault_fragment_group_member WHERE group_id = ?", (group_id,))
    for fid in fragment_ids:
        conn.execute(
            "INSERT OR IGNORE INTO knowledge_vault_fragment_group_member (fragment_id, group_id) VALUES (?,?)",
            (fid, group_id))
    conn.commit()
    conn.close()


def get_group_members(group_id: int) -> List[int]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT fragment_id FROM knowledge_vault_fragment_group_member WHERE group_id = ?", (group_id,))
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_fragment_group_id(fragment_id: int) -> Optional[int]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT group_id FROM knowledge_vault_fragment_group_member WHERE fragment_id = ?", (fragment_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None
