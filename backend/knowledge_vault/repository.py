"""Knowledge Vault — SQLite persistence.

raw_fragment is append-only (soft-archive, never hard-delete). node/edge form
the AI-managed network (rebuildable). fragment_vector stores embeddings for
the SQLite vector store. Tables self-heal on every connection.
"""
import json
import sqlite3
from datetime import datetime
from typing import List, Optional

from .entity import RawFragment, KnowledgeNode, Edge
from . import settings_manager

_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS raw_fragment (
        id INTEGER PRIMARY KEY,
        content TEXT NOT NULL,
        note TEXT DEFAULT '',
        raw_text TEXT DEFAULT '',
        kind TEXT DEFAULT '',
        created_at TEXT,
        archived INTEGER DEFAULT 0,
        last_accessed TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS node (
        id INTEGER PRIMARY KEY,
        title TEXT NOT NULL,
        summary TEXT DEFAULT '',
        kind TEXT DEFAULT '',
        fragment_ids TEXT DEFAULT '[]',
        freshness TEXT DEFAULT 'fresh',
        updated_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS edge (
        id INTEGER PRIMARY KEY,
        source_id INTEGER NOT NULL,
        target_id INTEGER NOT NULL,
        relation TEXT DEFAULT 'related',
        weight REAL DEFAULT 1.0
    )""",
    """CREATE TABLE IF NOT EXISTS fragment_vector (
        fragment_id INTEGER PRIMARY KEY,
        vector TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS label (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        color TEXT DEFAULT '#8e8e93'
    )""",
    """CREATE TABLE IF NOT EXISTS fragment_label (
        fragment_id INTEGER NOT NULL,
        label_id INTEGER NOT NULL,
        PRIMARY KEY (fragment_id, label_id)
    )""",
]


def _conn():
    conn = sqlite3.connect(settings_manager.get_db_path())
    for stmt in _SCHEMA:
        conn.execute(stmt)
    return conn


def init_db() -> None:
    conn = _conn()
    conn.commit()
    conn.close()


# ---- raw_fragment (append-only) --------------------------------------

_RF_COLS = "id, content, note, raw_text, kind, created_at, archived, last_accessed"


def insert_fragment(f: RawFragment) -> RawFragment:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""INSERT INTO raw_fragment
        (content, note, raw_text, kind, created_at, archived, last_accessed)
        VALUES (?,?,?,?,?,?,?)""",
        (f.content, f.note, f.raw_text, f.kind, f.created_at, f.archived, f.last_accessed))
    f.id = cur.lastrowid
    conn.commit()
    conn.close()
    return f


def get_fragments(include_archived=False) -> List[RawFragment]:
    conn = _conn()
    cur = conn.cursor()
    q = f"SELECT {_RF_COLS} FROM raw_fragment"
    if not include_archived:
        q += " WHERE archived = 0"
    q += " ORDER BY id DESC"
    cur.execute(q)
    rows = cur.fetchall()
    # Bulk-load label assignments so we don't N+1 query per fragment.
    cur.execute("SELECT fragment_id, label_id FROM fragment_label")
    label_map = {}
    for frag_id, label_id in cur.fetchall():
        label_map.setdefault(frag_id, []).append(label_id)
    conn.close()
    frags = [RawFragment.from_row(r) for r in rows]
    for f in frags:
        f.label_ids = label_map.get(f.id, [])
    return frags


def get_fragment(fid) -> Optional[RawFragment]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"SELECT {_RF_COLS} FROM raw_fragment WHERE id = ?", (fid,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    cur.execute("SELECT label_id FROM fragment_label WHERE fragment_id = ?", (fid,))
    label_ids = [r[0] for r in cur.fetchall()]
    conn.close()
    f = RawFragment.from_row(row)
    f.label_ids = label_ids
    return f


def update_fragment(fid, content=None, note=None) -> None:
    """Edit the content/note of a fragment (user-initiated). The raw layer is
    append-only w.r.t. the AI, but the user may correct their own entries."""
    conn = _conn()
    sets, params = [], []
    if content is not None:
        sets.append("content = ?"); params.append(content)
    if note is not None:
        sets.append("note = ?"); params.append(note)
    if sets:
        params.append(fid)
        conn.execute(f"UPDATE raw_fragment SET {', '.join(sets)} WHERE id = ?", params)
        conn.commit()
    conn.close()


def archive_fragment(fid) -> None:
    conn = _conn()
    conn.execute("UPDATE raw_fragment SET archived = 1 WHERE id = ?", (fid,))
    conn.commit()
    conn.close()


def delete_fragment(fid) -> None:
    """Hard-delete a fragment and its vector (user-initiated only; the AI never
    deletes)."""
    conn = _conn()
    conn.execute("DELETE FROM raw_fragment WHERE id = ?", (fid,))
    conn.execute("DELETE FROM fragment_vector WHERE fragment_id = ?", (fid,))
    conn.commit()
    conn.close()


def touch_fragment(fid) -> None:
    conn = _conn()
    conn.execute("UPDATE raw_fragment SET last_accessed = ? WHERE id = ?",
                 (datetime.now().isoformat(), fid))
    conn.commit()
    conn.close()


# ---- vectors ----------------------------------------------------------

def save_vector(fragment_id: int, vector: List[float]) -> None:
    conn = _conn()
    conn.execute("INSERT OR REPLACE INTO fragment_vector (fragment_id, vector) VALUES (?, ?)",
                 (fragment_id, json.dumps(vector)))
    conn.commit()
    conn.close()


def get_all_vectors() -> List[tuple]:
    """Returns [(fragment_id, [floats])] for non-archived fragments."""
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""SELECT v.fragment_id, v.vector FROM fragment_vector v
                   JOIN raw_fragment f ON f.id = v.fragment_id
                   WHERE f.archived = 0""")
    rows = cur.fetchall()
    conn.close()
    return [(r[0], json.loads(r[1])) for r in rows]


# ---- knowledge network (rebuildable) ---------------------------------

def clear_network() -> None:
    conn = _conn()
    conn.execute("DELETE FROM node")
    conn.execute("DELETE FROM edge")
    conn.commit()
    conn.close()


def insert_node(n: KnowledgeNode) -> KnowledgeNode:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""INSERT INTO node (title, summary, kind, fragment_ids, freshness, updated_at)
                   VALUES (?,?,?,?,?,?)""",
                (n.title, n.summary, n.kind, n.fragment_ids, n.freshness,
                 n.updated_at or datetime.now().isoformat()))
    n.id = cur.lastrowid
    conn.commit()
    conn.close()
    return n


def insert_edge(e: Edge) -> Edge:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""INSERT INTO edge (source_id, target_id, relation, weight)
                   VALUES (?,?,?,?)""",
                (e.source_id, e.target_id, e.relation, e.weight))
    e.id = cur.lastrowid
    conn.commit()
    conn.close()
    return e


def get_nodes() -> List[KnowledgeNode]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT id, title, summary, kind, fragment_ids, freshness, updated_at FROM node ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    return [KnowledgeNode.from_row(r) for r in rows]


def get_edges() -> List[Edge]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT id, source_id, target_id, relation, weight FROM edge")
    rows = cur.fetchall()
    conn.close()
    return [Edge.from_row(r) for r in rows]


def set_node_freshness(node_id: int, freshness: str) -> None:
    conn = _conn()
    conn.execute("UPDATE node SET freshness = ? WHERE id = ?", (freshness, node_id))
    conn.commit()
    conn.close()


# ---- labels (user-managed tags; a fragment may have many) --------------

def get_labels() -> List[dict]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT id, name, color FROM label ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "color": r[2]} for r in rows]


def create_label(name: str, color: str = "#8e8e93") -> dict:
    conn = _conn()
    cur = conn.cursor()
    # Idempotent: reuse an existing label of the same name.
    cur.execute("SELECT id, name, color FROM label WHERE name = ?", (name,))
    row = cur.fetchone()
    if row:
        conn.close()
        return {"id": row[0], "name": row[1], "color": row[2]}
    cur.execute("INSERT INTO label (name, color) VALUES (?, ?)", (name, color))
    lid = cur.lastrowid
    conn.commit()
    conn.close()
    return {"id": lid, "name": name, "color": color}


def delete_label(label_id: int) -> None:
    conn = _conn()
    conn.execute("DELETE FROM label WHERE id = ?", (label_id,))
    conn.execute("DELETE FROM fragment_label WHERE label_id = ?", (label_id,))
    conn.commit()
    conn.close()


def set_fragment_labels(fragment_id: int, label_ids: List[int]) -> None:
    conn = _conn()
    conn.execute("DELETE FROM fragment_label WHERE fragment_id = ?", (fragment_id,))
    for lid in label_ids:
        conn.execute("INSERT OR IGNORE INTO fragment_label (fragment_id, label_id) VALUES (?, ?)",
                     (fragment_id, lid))
    conn.commit()
    conn.close()
