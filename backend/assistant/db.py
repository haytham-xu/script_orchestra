"""
Assistant DB

SQLite-backed storage for conversations and messages. One file per install
(`assistant.db` in this module directory). Connections are opened
per-operation to keep the API simple and thread-safe under Flask.
"""
import sqlite3
import threading
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from .config import DB_PATH, DEFAULT_SYSTEM_PROMPT

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    system_prompt TEXT NOT NULL,
    model_alias TEXT NOT NULL DEFAULT 'auto',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,             -- 'user' | 'assistant'
    content TEXT NOT NULL,
    model TEXT,                     -- concrete model id (assistant messages only)
    complexity TEXT,                -- classifier verdict (assistant messages only)
    input_tokens INTEGER,
    output_tokens INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, id);

CREATE TABLE IF NOT EXISTS attachments (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    message_id INTEGER,              -- filled once the message is inserted
    kind TEXT NOT NULL,              -- 'image' | 'document' | 'text'
    mime_type TEXT NOT NULL,
    filename TEXT NOT NULL,
    byte_size INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_attachments_conv ON attachments(conversation_id, id);
CREATE INDEX IF NOT EXISTS idx_attachments_msg ON attachments(message_id);

-- Knowledge base: registered source folders
CREATE TABLE IF NOT EXISTS kb_sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    enabled INTEGER NOT NULL DEFAULT 1,
    last_scanned_at TEXT,
    file_count INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

-- Knowledge base: one row per source file
CREATE TABLE IF NOT EXISTS kb_documents (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    relpath TEXT NOT NULL,
    mtime REAL NOT NULL,
    byte_size INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    indexed_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES kb_sources(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_kb_docs_source ON kb_documents(source_id);

-- Knowledge base: chunks + embeddings (blob, cosine-normalized float32)
CREATE TABLE IF NOT EXISTS kb_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding BLOB NOT NULL,
    FOREIGN KEY (document_id) REFERENCES kb_documents(id) ON DELETE CASCADE,
    FOREIGN KEY (source_id) REFERENCES kb_sources(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_kb_chunks_doc ON kb_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_kb_chunks_source ON kb_chunks(source_id);

-- Per-conversation opt-in flag for RAG (default off).
-- Stored as an extra column on conversations via ALTER — see migrations
-- block in init_schema.

-- Full-text search index over messages.content. `content=messages` +
-- `content_rowid=id` keeps the actual text in `messages` (no duplication);
-- FTS just holds the search index.
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content,
    content='messages',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content)
      VALUES ('delete', old.id, old.content);
END;
CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content)
      VALUES ('delete', old.id, old.content);
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;
"""

_init_lock = threading.Lock()
_initialized = False


def _now() -> str:
    return datetime.now().isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema() -> None:
    global _initialized
    with _init_lock:
        if _initialized:
            return
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _connect() as conn:
            # Detect whether FTS index needs a backfill BEFORE running the
            # schema (which creates the empty FTS table if missing).
            existed = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='messages_fts'"
            ).fetchone() is not None

            conn.executescript(_SCHEMA)

            if not existed:
                # First time this DB gets an FTS index — backfill.
                conn.execute(
                    "INSERT INTO messages_fts(rowid, content) "
                    "SELECT id, content FROM messages"
                )

            # Idempotent column additions for older DBs.
            cols = {
                r[1] for r in conn.execute(
                    "PRAGMA table_info(conversations)"
                ).fetchall()
            }
            if "kb_enabled" not in cols:
                conn.execute(
                    "ALTER TABLE conversations "
                    "ADD COLUMN kb_enabled INTEGER NOT NULL DEFAULT 0"
                )
            if "pinned" not in cols:
                conn.execute(
                    "ALTER TABLE conversations "
                    "ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0"
                )
            if "archived" not in cols:
                conn.execute(
                    "ALTER TABLE conversations "
                    "ADD COLUMN archived INTEGER NOT NULL DEFAULT 0"
                )
            if "summary" not in cols:
                conn.execute(
                    "ALTER TABLE conversations ADD COLUMN summary TEXT"
                )
            if "summary_up_to_id" not in cols:
                conn.execute(
                    "ALTER TABLE conversations "
                    "ADD COLUMN summary_up_to_id INTEGER"
                )
        _initialized = True


# ── Conversations ─────────────────────────────────────────

def create_conversation(
    title: str = "New chat",
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    model_alias: str = "auto",
) -> Dict:
    init_schema()
    conv_id = str(uuid.uuid4())
    ts = _now()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO conversations "
            "(id, title, system_prompt, model_alias, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (conv_id, title, system_prompt, model_alias, ts, ts),
        )
    return get_conversation(conv_id)


def list_conversations() -> List[Dict]:
    init_schema()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, title, model_alias, kb_enabled, pinned, archived, "
            "       created_at, updated_at "
            "FROM conversations "
            "ORDER BY pinned DESC, archived ASC, updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_conversation(conv_id: str) -> Optional[Dict]:
    init_schema()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
    return dict(row) if row else None


def update_conversation(
    conv_id: str,
    title: Optional[str] = None,
    system_prompt: Optional[str] = None,
    model_alias: Optional[str] = None,
    kb_enabled: Optional[bool] = None,
    pinned: Optional[bool] = None,
    archived: Optional[bool] = None,
) -> Optional[Dict]:
    init_schema()
    fields, values = [], []
    if title is not None:
        fields.append("title = ?")
        values.append(title)
    if system_prompt is not None:
        fields.append("system_prompt = ?")
        values.append(system_prompt)
    if model_alias is not None:
        fields.append("model_alias = ?")
        values.append(model_alias)
    if kb_enabled is not None:
        fields.append("kb_enabled = ?")
        values.append(1 if kb_enabled else 0)
    if pinned is not None:
        fields.append("pinned = ?")
        values.append(1 if pinned else 0)
    if archived is not None:
        fields.append("archived = ?")
        values.append(1 if archived else 0)
    if not fields:
        return get_conversation(conv_id)

    fields.append("updated_at = ?")
    values.append(_now())
    values.append(conv_id)

    with _connect() as conn:
        cur = conn.execute(
            f"UPDATE conversations SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        if cur.rowcount == 0:
            return None
    return get_conversation(conv_id)


def delete_conversation(conv_id: str) -> bool:
    init_schema()
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM conversations WHERE id = ?", (conv_id,)
        )
        return cur.rowcount > 0


def touch_conversation(conv_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (_now(), conv_id),
        )


# ── Messages ──────────────────────────────────────────────

def add_message(
    conv_id: str,
    role: str,
    content: str,
    model: Optional[str] = None,
    complexity: Optional[str] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
) -> Dict:
    init_schema()
    ts = _now()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO messages "
            "(conversation_id, role, content, model, complexity, "
            " input_tokens, output_tokens, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (conv_id, role, content, model, complexity,
             input_tokens, output_tokens, ts),
        )
        msg_id = cur.lastrowid
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (ts, conv_id),
        )
    return get_message(msg_id)


def get_message(msg_id: int) -> Optional[Dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM messages WHERE id = ?", (msg_id,)
        ).fetchone()
    return dict(row) if row else None


def list_messages(conv_id: str, limit: Optional[int] = None) -> List[Dict]:
    init_schema()
    query = ("SELECT * FROM messages WHERE conversation_id = ? "
             "ORDER BY id ASC")
    params = [conv_id]
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def recent_messages_for_context(conv_id: str, limit: int) -> List[Dict]:
    """
    Return the most recent `limit` messages in chronological order.
    Used to build the model context window.
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages "
            "WHERE conversation_id = ? ORDER BY id DESC LIMIT ?",
            (conv_id, limit),
        ).fetchall()
    return list(reversed([dict(r) for r in rows]))


# ── Attachments ───────────────────────────────────────────

def create_attachment(
    attachment_id: str,
    conv_id: str,
    kind: str,
    mime_type: str,
    filename: str,
    byte_size: int,
    sha256: str,
    storage_path: str,
) -> Dict:
    init_schema()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO attachments "
            "(id, conversation_id, message_id, kind, mime_type, filename, "
            " byte_size, sha256, storage_path, created_at) "
            "VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?)",
            (attachment_id, conv_id, kind, mime_type, filename,
             byte_size, sha256, storage_path, _now()),
        )
    return get_attachment(attachment_id)


def get_attachment(attachment_id: str) -> Optional[Dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM attachments WHERE id = ?", (attachment_id,)
        ).fetchone()
    return dict(row) if row else None


def list_attachments_for_conversation(conv_id: str) -> List[Dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM attachments WHERE conversation_id = ? "
            "ORDER BY created_at ASC",
            (conv_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_attachments_for_message(msg_id: int) -> List[Dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM attachments WHERE message_id = ? ORDER BY id",
            (msg_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def attach_to_message(attachment_ids: List[str], msg_id: int) -> None:
    """Bind previously-uploaded attachments to a freshly-inserted message."""
    if not attachment_ids:
        return
    placeholders = ",".join("?" * len(attachment_ids))
    with _connect() as conn:
        conn.execute(
            f"UPDATE attachments SET message_id = ? WHERE id IN ({placeholders})",
            (msg_id, *attachment_ids),
        )


# ── Edit / truncate ──────────────────────────────────────

def set_conversation_summary(conv_id: str, summary: str,
                             summary_up_to_id: int) -> None:
    """Store the rolling summary text + the id of the last message it covers."""
    init_schema()
    with _connect() as conn:
        conn.execute(
            "UPDATE conversations SET summary = ?, summary_up_to_id = ? "
            "WHERE id = ?",
            (summary, summary_up_to_id, conv_id),
        )

def edit_user_message_and_truncate(
    conv_id: str,
    message_id: int,
    new_content: str,
) -> Optional[Dict]:
    """
    Rewrite a user message's content and delete every message with a
    larger id in the same conversation, so the model can re-answer with
    the edited turn as the latest one.

    Returns the updated message row, or None if not found / wrong role /
    wrong conversation.
    """
    init_schema()
    new_content = (new_content or "").strip()
    if not new_content:
        raise ValueError("new content cannot be empty")

    with _connect() as conn:
        row = conn.execute(
            "SELECT id, conversation_id, role FROM messages WHERE id = ?",
            (message_id,),
        ).fetchone()
        if row is None or row["conversation_id"] != conv_id or row["role"] != "user":
            return None

        conn.execute(
            "UPDATE messages SET content = ? WHERE id = ?",
            (new_content, message_id),
        )
        conn.execute(
            "DELETE FROM messages WHERE conversation_id = ? AND id > ?",
            (conv_id, message_id),
        )
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (_now(), conv_id),
        )
    return get_message(message_id)


# ── Fork ─────────────────────────────────────────────────

def fork_conversation(
    source_conv_id: str,
    up_to_message_id: int,
    include_target: bool,
    new_title: Optional[str] = None,
) -> Optional[Dict]:
    """
    Duplicate a conversation up to a given message boundary.

    Args:
        source_conv_id: The conversation to fork from.
        up_to_message_id: The message that anchors the fork.
        include_target: If True, the target message is copied into the
            fork (use case: "continue from this assistant reply"). If
            False, the target and everything after are dropped (use case:
            "ask this user question again with a fresh answer").
        new_title: Optional override for the new conversation's title.
            Defaults to `<original title> (fork)`.

    Returns the new conversation row, or None if the source or target
    isn't found.
    """
    src = get_conversation(source_conv_id)
    if src is None:
        return None

    init_schema()
    with _connect() as conn:
        target = conn.execute(
            "SELECT id, conversation_id FROM messages WHERE id = ?",
            (up_to_message_id,),
        ).fetchone()
        if target is None or target["conversation_id"] != source_conv_id:
            return None

        boundary_op = "<=" if include_target else "<"
        rows = conn.execute(
            f"SELECT * FROM messages WHERE conversation_id = ? "
            f"  AND id {boundary_op} ? ORDER BY id ASC",
            (source_conv_id, up_to_message_id),
        ).fetchall()

    title = new_title or f"{src['title']} (fork)"
    new_conv = create_conversation(
        title=title,
        system_prompt=src["system_prompt"],
        model_alias=src["model_alias"],
    )

    id_remap: Dict[int, int] = {}
    ts_now = _now()
    with _connect() as conn:
        for row in rows:
            cur = conn.execute(
                "INSERT INTO messages "
                "(conversation_id, role, content, model, complexity, "
                " input_tokens, output_tokens, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (new_conv["id"], row["role"], row["content"], row["model"],
                 row["complexity"], row["input_tokens"], row["output_tokens"],
                 row["created_at"]),
            )
            id_remap[row["id"]] = cur.lastrowid

        # Clone attachments too — content-addressed on disk, so we just
        # insert new DB rows pointing at the same storage_path.
        for old_msg_id, new_msg_id in id_remap.items():
            atts = conn.execute(
                "SELECT * FROM attachments WHERE message_id = ?",
                (old_msg_id,),
            ).fetchall()
            for a in atts:
                new_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO attachments "
                    "(id, conversation_id, message_id, kind, mime_type, "
                    " filename, byte_size, sha256, storage_path, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (new_id, new_conv["id"], new_msg_id, a["kind"],
                     a["mime_type"], a["filename"], a["byte_size"],
                     a["sha256"], a["storage_path"], ts_now),
                )

        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (ts_now, new_conv["id"]),
        )

    return get_conversation(new_conv["id"])


# ── Usage stats ───────────────────────────────────────────

def usage_totals() -> Dict:
    """
    Return aggregate token usage across the whole DB.
    All-time totals + today + last 7 days, plus per-model breakdown.
    """
    init_schema()
    with _connect() as conn:
        overall = conn.execute(
            "SELECT COALESCE(SUM(input_tokens), 0) AS input, "
            "       COALESCE(SUM(output_tokens), 0) AS output, "
            "       COUNT(*) AS message_count "
            "FROM messages WHERE role='assistant'"
        ).fetchone()
        today = conn.execute(
            "SELECT COALESCE(SUM(input_tokens), 0) AS input, "
            "       COALESCE(SUM(output_tokens), 0) AS output, "
            "       COUNT(*) AS message_count "
            "FROM messages WHERE role='assistant' "
            "AND date(created_at) = date('now', 'localtime')"
        ).fetchone()
        last7 = conn.execute(
            "SELECT COALESCE(SUM(input_tokens), 0) AS input, "
            "       COALESCE(SUM(output_tokens), 0) AS output, "
            "       COUNT(*) AS message_count "
            "FROM messages WHERE role='assistant' "
            "AND date(created_at) >= date('now', '-6 days', 'localtime')"
        ).fetchone()
        by_model = conn.execute(
            "SELECT model, "
            "       COALESCE(SUM(input_tokens), 0) AS input, "
            "       COALESCE(SUM(output_tokens), 0) AS output, "
            "       COUNT(*) AS message_count "
            "FROM messages WHERE role='assistant' AND model IS NOT NULL "
            "GROUP BY model ORDER BY output DESC"
        ).fetchall()
        conv_count = conn.execute(
            "SELECT COUNT(*) AS n FROM conversations"
        ).fetchone()["n"]
    return {
        "conversation_count": conv_count,
        "overall": dict(overall),
        "today": dict(today),
        "last_7_days": dict(last7),
        "by_model": [dict(r) for r in by_model],
    }


def usage_for_conversation(conv_id: str) -> Dict:
    with _connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(input_tokens), 0) AS input, "
            "       COALESCE(SUM(output_tokens), 0) AS output, "
            "       COUNT(*) AS message_count "
            "FROM messages WHERE role='assistant' AND conversation_id = ?",
            (conv_id,),
        ).fetchone()
        by_model = conn.execute(
            "SELECT model, "
            "       COALESCE(SUM(input_tokens), 0) AS input, "
            "       COALESCE(SUM(output_tokens), 0) AS output, "
            "       COUNT(*) AS message_count "
            "FROM messages "
            "WHERE role='assistant' AND model IS NOT NULL "
            "  AND conversation_id = ? "
            "GROUP BY model ORDER BY output DESC",
            (conv_id,),
        ).fetchall()
    return {
        "overall": dict(row),
        "by_model": [dict(r) for r in by_model],
    }


def _build_fts_query(user_query: str) -> str:
    """
    Turn a casual search string into an FTS5 MATCH expression.

    Rules:
      - If the user included FTS operators (", *, OR, NEAR, AND, -),
        pass through as-is (power-user mode).
      - Otherwise split on whitespace and AND the terms together with
        prefix matching, so `foo bar` matches messages containing both
        `foo*` and `bar*`.
      - Non-alphanumeric characters other than CJK letters are dropped
        so shell-punctuation doesn't break the parse.
    """
    q = user_query.strip()
    if not q:
        return ""
    if any(op in q for op in ('"', '*', ' OR ', ' AND ', ' NEAR', '-', ':')):
        return q

    def clean(token: str) -> str:
        return "".join(
            ch for ch in token
            if ch.isalnum() or '一' <= ch <= '鿿'
        )
    terms = [clean(t) for t in q.split()]
    terms = [t for t in terms if t]
    if not terms:
        return ""
    return " AND ".join(f'"{t}"*' for t in terms)


def search_messages(user_query: str, limit: int = 30) -> List[Dict]:
    """
    Full-text search across all conversations. Returns hit rows shaped for
    the UI: conversation title/id, message id, role, snippet, timestamp,
    plus the raw score (bm25 — lower is better).
    """
    init_schema()
    fts_query = _build_fts_query(user_query)
    if not fts_query:
        return []

    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT m.id AS message_id, "
                "       m.conversation_id, "
                "       c.title AS conversation_title, "
                "       m.role, "
                "       m.created_at, "
                "       m.model, "
                "       snippet(messages_fts, 0, '<mark>', '</mark>', '…', 15) AS snippet, "
                "       bm25(messages_fts) AS score "
                "FROM messages_fts "
                "JOIN messages m ON m.id = messages_fts.rowid "
                "JOIN conversations c ON c.id = m.conversation_id "
                "WHERE messages_fts MATCH ? "
                "ORDER BY score ASC "
                "LIMIT ?",
                (fts_query, limit),
            ).fetchall()
    except sqlite3.OperationalError:
        # Malformed FTS expression — fall back to a plain LIKE scan so the
        # user still gets something instead of a 500.
        like = f"%{user_query.strip()}%"
        with _connect() as conn:
            rows = conn.execute(
                "SELECT m.id AS message_id, "
                "       m.conversation_id, "
                "       c.title AS conversation_title, "
                "       m.role, "
                "       m.created_at, "
                "       m.model, "
                "       substr(m.content, 1, 240) AS snippet, "
                "       0.0 AS score "
                "FROM messages m "
                "JOIN conversations c ON c.id = m.conversation_id "
                "WHERE m.content LIKE ? "
                "ORDER BY m.created_at DESC "
                "LIMIT ?",
                (like, limit),
            ).fetchall()
    return [dict(r) for r in rows]
