import sqlite3

from shared.db import get_conn

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS clean_keyword_keyword (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT    UNIQUE NOT NULL
);
"""


def _conn():
    c = get_conn()
    c.execute(_CREATE_SQL)
    c.commit()
    return c


def init_db():
    with _conn():
        pass


def get_all() -> list:
    with _conn() as c:
        rows = c.execute("SELECT keyword FROM clean_keyword_keyword ORDER BY keyword COLLATE NOCASE").fetchall()
    return [r['keyword'] for r in rows]


def add(kw: str) -> bool:
    try:
        with _conn() as c:
            c.execute("INSERT INTO clean_keyword_keyword (keyword) VALUES (?)", (kw,))
        return True
    except sqlite3.IntegrityError:
        return False


def delete(kw: str):
    with _conn() as c:
        c.execute("DELETE FROM clean_keyword_keyword WHERE keyword = ?", (kw,))


def import_bulk(kw_list: list) -> int:
    added = 0
    with _conn() as c:
        for kw in kw_list:
            try:
                c.execute("INSERT INTO clean_keyword_keyword (keyword) VALUES (?)", (kw,))
                added += 1
            except sqlite3.IntegrityError:
                pass
    return added
