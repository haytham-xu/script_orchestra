"""Memory Curve — SQLite persistence for cards + scheduling state."""
import sqlite3
from datetime import datetime, date
from typing import List, Optional

from .entity import Card
from . import settings_manager

TABLE = "card"


def _conn():
    return sqlite3.connect(settings_manager.get_db_path())


def init_db() -> None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            id INTEGER PRIMARY KEY,
            front TEXT NOT NULL,
            back TEXT DEFAULT '',
            deck TEXT DEFAULT '',
            created_at TEXT,
            updated_at TEXT,
            interval REAL DEFAULT 0,
            ease REAL DEFAULT 2.5,
            reps INTEGER DEFAULT 0,
            due_date TEXT,
            last_reviewed TEXT,
            suspended INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


_COLS = ("id, front, back, deck, created_at, updated_at, interval, ease, "
         "reps, due_date, last_reviewed, suspended")


def insert(card: Card) -> Card:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"""
        INSERT INTO {TABLE}
        (front, back, deck, created_at, updated_at, interval, ease, reps,
         due_date, last_reviewed, suspended)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (card.front, card.back, card.deck, card.created_at, card.updated_at,
          card.interval, card.ease, card.reps, card.due_date,
          card.last_reviewed, card.suspended))
    card.id = cur.lastrowid
    conn.commit()
    conn.close()
    return card


def get_all() -> List[Card]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"SELECT {_COLS} FROM {TABLE} ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()
    return [Card.from_row(r) for r in rows]


def get_by_id(card_id) -> Optional[Card]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"SELECT {_COLS} FROM {TABLE} WHERE id = ?", (card_id,))
    row = cur.fetchone()
    conn.close()
    return Card.from_row(row) if row else None


def get_due(today: str = None) -> List[Card]:
    today = today or date.today().isoformat()
    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"""SELECT {_COLS} FROM {TABLE}
                    WHERE suspended = 0 AND due_date <= ?
                    ORDER BY due_date ASC, id ASC""", (today,))
    rows = cur.fetchall()
    conn.close()
    return [Card.from_row(r) for r in rows]


def update(card: Card) -> None:
    card.updated_at = datetime.now().isoformat()
    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"""
        UPDATE {TABLE} SET
            front=?, back=?, deck=?, updated_at=?, interval=?, ease=?, reps=?,
            due_date=?, last_reviewed=?, suspended=?
        WHERE id=?
    """, (card.front, card.back, card.deck, card.updated_at, card.interval,
          card.ease, card.reps, card.due_date, card.last_reviewed,
          card.suspended, card.id))
    conn.commit()
    conn.close()


def delete(card_id) -> None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM {TABLE} WHERE id = ?", (card_id,))
    conn.commit()
    conn.close()
