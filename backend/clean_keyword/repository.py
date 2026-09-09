import os
import sqlite3

_DB_PATH = os.path.join(os.path.dirname(__file__), 'clean_keyword.db')

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS keyword (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT    UNIQUE NOT NULL
);
"""


def _conn():
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute(_CREATE_SQL)
    c.commit()
    return c


def init_db():
    with _conn():
        pass


def get_all() -> list:
    with _conn() as c:
        rows = c.execute("SELECT keyword FROM keyword ORDER BY keyword COLLATE NOCASE").fetchall()
    return [r['keyword'] for r in rows]


def add(kw: str) -> bool:
    try:
        with _conn() as c:
            c.execute("INSERT INTO keyword (keyword) VALUES (?)", (kw,))
        return True
    except sqlite3.IntegrityError:
        return False


def delete(kw: str):
    with _conn() as c:
        c.execute("DELETE FROM keyword WHERE keyword = ?", (kw,))


def import_bulk(kw_list: list) -> int:
    added = 0
    with _conn() as c:
        for kw in kw_list:
            try:
                c.execute("INSERT INTO keyword (keyword) VALUES (?)", (kw,))
                added += 1
            except sqlite3.IntegrityError:
                pass
    return added
