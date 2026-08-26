"""
Knowledge Base service — sources, scan, retrieval.

Data model recap:
  kb_sources    (id, name, path, enabled, last_scanned_at, counts)
  kb_documents  (id, source_id, relpath, mtime, byte_size, sha256, indexed_at)
  kb_chunks     (id, document_id, source_id, ordinal, text, embedding blob)

`refresh_source(source_id)` walks the folder, compares mtime + sha256
against `kb_documents`, deletes stale rows, adds new ones. Embeddings
are computed only for changed / new chunks.

`retrieve(query, top_k)` embeds the query and does a cosine-similarity
scan over `kb_chunks.embedding`. For small knowledge bases (<50k chunks)
a plain scan is fast enough and avoids adding an FAISS/pgvector
dependency.
"""
import hashlib
import logging
import sqlite3
import struct
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .. import db as adb
from .config import (
    DEFAULT_MIN_SCORE,
    DEFAULT_TOP_K,
    MAX_FILE_BYTES,
    SUPPORTED_CODE_EXT,
    SUPPORTED_PDF_EXT,
    SUPPORTED_TEXT_EXT,
)
from . import chunker, embed

logger = logging.getLogger("assistant.knowledge.service")


def _now() -> str:
    return datetime.now().isoformat()


def _supported_exts() -> set:
    return SUPPORTED_TEXT_EXT | SUPPORTED_CODE_EXT | SUPPORTED_PDF_EXT


# ── Sources CRUD ─────────────────────────────────────────

def list_sources() -> List[Dict]:
    adb.init_schema()
    with sqlite3.connect(str(adb.DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM kb_sources ORDER BY created_at ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_source(source_id: str) -> Optional[Dict]:
    adb.init_schema()
    with sqlite3.connect(str(adb.DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM kb_sources WHERE id = ?", (source_id,)
        ).fetchone()
    return dict(row) if row else None


def create_source(name: str, path: str) -> Dict:
    adb.init_schema()
    folder = Path(path).expanduser().resolve()
    if not folder.exists() or not folder.is_dir():
        raise ValueError(f"Not a directory: {folder}")

    source_id = str(uuid.uuid4())
    with sqlite3.connect(str(adb.DB_PATH)) as conn:
        try:
            conn.execute(
                "INSERT INTO kb_sources "
                "(id, name, path, enabled, last_scanned_at, "
                " file_count, chunk_count, created_at) "
                "VALUES (?, ?, ?, 1, NULL, 0, 0, ?)",
                (source_id, name or folder.name, str(folder), _now()),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Path already registered: {folder}") from exc
    return get_source(source_id)


def update_source(source_id: str, **fields) -> Optional[Dict]:
    allowed = {"name", "enabled"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return get_source(source_id)
    with sqlite3.connect(str(adb.DB_PATH)) as conn:
        sets = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE kb_sources SET {sets} WHERE id = ?",
            (*updates.values(), source_id),
        )
    return get_source(source_id)


def delete_source(source_id: str) -> bool:
    with sqlite3.connect(str(adb.DB_PATH)) as conn:
        cur = conn.execute("DELETE FROM kb_sources WHERE id = ?", (source_id,))
        return cur.rowcount > 0


# ── Scan / refresh ───────────────────────────────────────

def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(64 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _walk_source(source_root: Path) -> List[Path]:
    exts = _supported_exts()
    out: List[Path] = []
    for p in source_root.rglob("*"):
        # Skip hidden dirs & common noise folders.
        if any(part.startswith('.') for part in p.parts):
            continue
        if any(part in {"node_modules", "__pycache__", "venv", ".venv",
                        "dist", "build", "target"} for part in p.parts):
            continue
        if not p.is_file():
            continue
        if p.suffix.lower() not in exts:
            continue
        try:
            if p.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        out.append(p)
    return out


def refresh_source(source_id: str) -> Dict:
    """
    Scan the source directory, upsert changed/new files, drop deleted
    ones, and (re)embed anything that changed. Returns a summary.
    """
    src = get_source(source_id)
    if src is None:
        raise LookupError(f"source not found: {source_id}")

    root = Path(src["path"])
    if not root.exists():
        raise FileNotFoundError(f"source path missing: {root}")

    logger.info(f"[kb] refresh source {src['name']} at {root}")

    scanned = _walk_source(root)
    seen_relpaths: set = set()
    changed = 0
    added = 0
    unchanged = 0

    with sqlite3.connect(str(adb.DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        existing = {
            row["relpath"]: dict(row) for row in conn.execute(
                "SELECT * FROM kb_documents WHERE source_id = ?",
                (source_id,),
            ).fetchall()
        }

    for path in scanned:
        relpath = str(path.relative_to(root))
        seen_relpaths.add(relpath)
        stat = path.stat()
        prior = existing.get(relpath)

        if prior:
            # Fast path: mtime + size match → skip embed entirely.
            if (abs(prior["mtime"] - stat.st_mtime) < 1.0
                    and prior["byte_size"] == stat.st_size):
                unchanged += 1
                continue

        try:
            sha = _sha256_of(path)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[kb] hash failed for {path}: {exc}")
            continue

        if prior and prior["sha256"] == sha:
            # Content actually unchanged (mtime lied); update stat only.
            with sqlite3.connect(str(adb.DB_PATH)) as conn:
                conn.execute(
                    "UPDATE kb_documents SET mtime = ?, byte_size = ?, "
                    "indexed_at = ? WHERE id = ?",
                    (stat.st_mtime, stat.st_size, _now(), prior["id"]),
                )
            unchanged += 1
            continue

        text = chunker.extract_text(path)
        if not text.strip():
            continue
        chunks = chunker.chunk_text(text)
        if not chunks:
            continue

        vectors = embed.embed_texts(chunks)

        doc_id = prior["id"] if prior else str(uuid.uuid4())
        with sqlite3.connect(str(adb.DB_PATH)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            if prior:
                conn.execute(
                    "DELETE FROM kb_chunks WHERE document_id = ?",
                    (doc_id,),
                )
                conn.execute(
                    "UPDATE kb_documents SET mtime = ?, byte_size = ?, "
                    "sha256 = ?, indexed_at = ? WHERE id = ?",
                    (stat.st_mtime, stat.st_size, sha, _now(), doc_id),
                )
                changed += 1
            else:
                conn.execute(
                    "INSERT INTO kb_documents "
                    "(id, source_id, relpath, mtime, byte_size, sha256, "
                    " indexed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (doc_id, source_id, relpath, stat.st_mtime,
                     stat.st_size, sha, _now()),
                )
                added += 1
            for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
                conn.execute(
                    "INSERT INTO kb_chunks "
                    "(document_id, source_id, ordinal, text, embedding) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (doc_id, source_id, i, chunk, vec),
                )

    # Drop rows whose files vanished from disk.
    deleted = 0
    for relpath, prior in existing.items():
        if relpath not in seen_relpaths:
            with sqlite3.connect(str(adb.DB_PATH)) as conn:
                conn.execute("PRAGMA foreign_keys = ON")
                conn.execute(
                    "DELETE FROM kb_documents WHERE id = ?", (prior["id"],)
                )
            deleted += 1

    # Recount and update the source row.
    with sqlite3.connect(str(adb.DB_PATH)) as conn:
        file_count = conn.execute(
            "SELECT COUNT(*) FROM kb_documents WHERE source_id = ?",
            (source_id,),
        ).fetchone()[0]
        chunk_count = conn.execute(
            "SELECT COUNT(*) FROM kb_chunks WHERE source_id = ?",
            (source_id,),
        ).fetchone()[0]
        conn.execute(
            "UPDATE kb_sources SET last_scanned_at = ?, "
            "file_count = ?, chunk_count = ? WHERE id = ?",
            (_now(), file_count, chunk_count, source_id),
        )

    return {
        "source_id": source_id,
        "added": added,
        "changed": changed,
        "unchanged": unchanged,
        "deleted": deleted,
        "file_count": file_count,
        "chunk_count": chunk_count,
    }


# ── Retrieval ────────────────────────────────────────────

def retrieve(query: str,
             top_k: int = DEFAULT_TOP_K,
             min_score: float = DEFAULT_MIN_SCORE) -> List[Dict]:
    """
    Return the top-K chunks whose (normalized) embedding has the highest
    cosine similarity with the query. Only enabled sources contribute.
    """
    q = (query or "").strip()
    if not q:
        return []

    adb.init_schema()

    with sqlite3.connect(str(adb.DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT c.id, c.document_id, c.source_id, c.ordinal, c.text, "
            "       c.embedding, d.relpath, s.name AS source_name, "
            "       s.path AS source_path "
            "FROM kb_chunks c "
            "JOIN kb_documents d ON d.id = c.document_id "
            "JOIN kb_sources s ON s.id = c.source_id "
            "WHERE s.enabled = 1"
        ).fetchall()

    if not rows:
        return []

    import numpy as np
    q_vec = np.frombuffer(embed.embed_query(q), dtype=np.float32)

    scored: List[Dict] = []
    for row in rows:
        v = np.frombuffer(row["embedding"], dtype=np.float32)
        # Both vectors are L2-normalized → dot product == cosine.
        score = float(np.dot(q_vec, v))
        if score < min_score:
            continue
        scored.append({
            "chunk_id": row["id"],
            "document_id": row["document_id"],
            "source_id": row["source_id"],
            "source_name": row["source_name"],
            "relpath": row["relpath"],
            "ordinal": row["ordinal"],
            "text": row["text"],
            "score": round(score, 4),
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


# ── Prompt integration ───────────────────────────────────

def format_context_block(hits: List[Dict]) -> str:
    """
    Build a system-prompt-suffix string that presents retrieved chunks
    to Claude with clear provenance so it can cite sources.
    """
    if not hits:
        return ""
    parts = [
        "You have access to the following knowledge-base excerpts, "
        "retrieved from local files the user has registered. Use them "
        "when they're relevant, and cite the source path in brackets. "
        "If they don't help, ignore them silently.",
        "",
    ]
    for i, hit in enumerate(hits, start=1):
        parts.append(
            f"[{i}] source: {hit['source_name']}/{hit['relpath']} "
            f"(chunk {hit['ordinal']}, score={hit['score']})"
        )
        parts.append(hit["text"].strip())
        parts.append("")
    return "\n".join(parts)
