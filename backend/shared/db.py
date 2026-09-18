import os
import sqlite3

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_DB_PATH = os.path.join(_BACKEND_DIR, 'data', 'script_orchestra.db')


def get_db_path() -> str:
    return os.environ.get('DB_PATH', _DEFAULT_DB_PATH)


def get_conn() -> sqlite3.Connection:
    path = get_db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn
