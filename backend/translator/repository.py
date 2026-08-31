"""Translator — SQLite persistence.

translation_history holds one row per translation (both scenes, distinguished
by the `scene` column). learning_point holds AI-extracted English learning
notes for the zh2en scene, each FK'd to a history row. Cleanup deletes history
older than N days and cascades to the associated learning points (no orphans).

Tables self-heal on every connection (CREATE TABLE IF NOT EXISTS), matching the
knowledge_vault pattern.
"""
import json
import sqlite3
from datetime import datetime, timedelta
from typing import List, Optional

from .entity import TranslationHistory, LearningPoint
from . import settings_manager

_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS translation_history (
        id INTEGER PRIMARY KEY,
        scene TEXT NOT NULL,                 -- 'zh2en' | 'en2zh'
        source_text TEXT NOT NULL,
        result_text TEXT NOT NULL,
        back_translation TEXT DEFAULT '',
        model TEXT DEFAULT '',
        created_at TEXT,
        usage_json TEXT DEFAULT '{}'         -- aggregated Copilot usage for this row
    )""",
    """CREATE TABLE IF NOT EXISTS learning_point (
        id INTEGER PRIMARY KEY,
        history_id INTEGER NOT NULL,
        original TEXT NOT NULL,
        suggestion TEXT DEFAULT '',
        explanation TEXT DEFAULT '',
        created_at TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_history_scene ON translation_history(scene)",
    "CREATE INDEX IF NOT EXISTS idx_lp_history ON learning_point(history_id)",
]

_HIST_COLS = "id, scene, source_text, result_text, back_translation, model, created_at, usage_json"
_LP_COLS = "id, history_id, original, suggestion, explanation, created_at"


def _migrate(conn) -> None:
    """Idempotent column-level migrations (self-healing schema can't add columns
    to a table that already exists). Cheap: PRAGMA reads are in-memory. Mirrors
    knowledge_vault/repository.py._migrate."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(translation_history)")}
    if "usage_json" not in cols:
        conn.execute("ALTER TABLE translation_history ADD COLUMN usage_json TEXT DEFAULT '{}'")


def _conn():
    conn = sqlite3.connect(settings_manager.get_db_path())
    for stmt in _SCHEMA:
        conn.execute(stmt)
    _migrate(conn)
    return conn


def init_db() -> None:
    conn = _conn()
    conn.commit()
    conn.close()


# ---- history ----------------------------------------------------------

def insert_history(h: TranslationHistory) -> TranslationHistory:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO translation_history
           (scene, source_text, result_text, back_translation, model, created_at, usage_json)
           VALUES (?,?,?,?,?,?,?)""",
        (h.scene, h.source_text, h.result_text, h.back_translation, h.model,
         h.created_at, json.dumps(h.usage or {})),
    )
    h.id = cur.lastrowid
    conn.commit()
    conn.close()
    return h


def get_history(scene: Optional[str] = None, limit: int = 100) -> List[TranslationHistory]:
    """Newest-first history, optionally filtered by scene. zh2en rows are
    hydrated with their learning points."""
    conn = _conn()
    cur = conn.cursor()
    q = f"SELECT {_HIST_COLS} FROM translation_history"
    params = []
    if scene:
        q += " WHERE scene = ?"
        params.append(scene)
    q += " ORDER BY id DESC LIMIT ?"
    params.append(int(limit))
    cur.execute(q, params)
    rows = cur.fetchall()
    hist = [TranslationHistory.from_row(r) for r in rows]

    # Bulk-load learning points for the fetched history ids (avoid N+1).
    ids = [h.id for h in hist]
    lp_map = {}
    if ids:
        placeholders = ",".join("?" * len(ids))
        cur.execute(
            f"SELECT {_LP_COLS} FROM learning_point WHERE history_id IN ({placeholders}) ORDER BY id",
            ids,
        )
        for r in cur.fetchall():
            lp = LearningPoint.from_row(r)
            lp_map.setdefault(lp.history_id, []).append(lp)
    conn.close()
    for h in hist:
        h.learning_points = lp_map.get(h.id, [])
    return hist


def usage_summary(scene: Optional[str] = None) -> dict:
    """Aggregate cumulative usage across history. Optionally scoped to one scene.
    Returns totals plus a per-scene breakdown (always both scenes present)."""
    conn = _conn()
    cur = conn.cursor()
    q = "SELECT scene, usage_json FROM translation_history"
    params = []
    if scene:
        q += " WHERE scene = ?"
        params.append(scene)
    cur.execute(q, params)
    rows = cur.fetchall()
    conn.close()

    def _blank():
        return {"count": 0, "total_credits": 0.0, "total_input_tokens": 0,
                "total_output_tokens": 0}

    total = _blank()
    by_scene = {"zh2en": _blank(), "en2zh": _blank()}
    for sc, uj in rows:
        try:
            u = json.loads(uj) if uj else {}
        except (ValueError, TypeError):
            u = {}
        bucket = by_scene.setdefault(sc, _blank())
        for target in (total, bucket):
            target["count"] += 1
            target["total_credits"] += float(u.get("credits") or 0)
            target["total_input_tokens"] += int(u.get("input_tokens") or 0)
            target["total_output_tokens"] += int(u.get("output_tokens") or 0)
    total["total_credits"] = round(total["total_credits"], 4)
    for b in by_scene.values():
        b["total_credits"] = round(b["total_credits"], 4)
    return {**total, "by_scene": by_scene}


# ---- learning points --------------------------------------------------

def insert_learning_points(history_id: int, points: List[LearningPoint]) -> List[LearningPoint]:
    conn = _conn()
    cur = conn.cursor()
    for p in points:
        p.history_id = history_id
        cur.execute(
            """INSERT INTO learning_point
               (history_id, original, suggestion, explanation, created_at)
               VALUES (?,?,?,?,?)""",
            (p.history_id, p.original, p.suggestion, p.explanation, p.created_at),
        )
        p.id = cur.lastrowid
    conn.commit()
    conn.close()
    return points


# ---- cleanup ----------------------------------------------------------

def cleanup_older_than(days: int) -> int:
    """Delete history (both scenes) older than `days`, cascading to learning
    points. Returns the number of history rows deleted."""
    cutoff = (datetime.now() - timedelta(days=int(days))).isoformat()
    conn = _conn()
    cur = conn.cursor()
    # Find victims first so we can cascade learning points explicitly (no FK
    # pragma reliance — keeps behavior identical across sqlite builds).
    cur.execute("SELECT id FROM translation_history WHERE created_at < ?", (cutoff,))
    victim_ids = [r[0] for r in cur.fetchall()]
    if victim_ids:
        placeholders = ",".join("?" * len(victim_ids))
        cur.execute(f"DELETE FROM learning_point WHERE history_id IN ({placeholders})", victim_ids)
        cur.execute(f"DELETE FROM translation_history WHERE id IN ({placeholders})", victim_ids)
    conn.commit()
    conn.close()
    return len(victim_ids)
