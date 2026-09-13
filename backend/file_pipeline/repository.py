import sqlite3
import os
from .entity import Tool, Pipeline

_DB_PATH = os.path.join(os.path.dirname(__file__), 'file_pipeline.db')

_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS tool (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        exe_path TEXT NOT NULL,
        args_template TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS pipeline (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        steps TEXT NOT NULL
    )""",
]


def _conn():
    conn = sqlite3.connect(_DB_PATH)
    for stmt in _SCHEMA:
        conn.execute(stmt)
    conn.commit()
    return conn


def init_db():
    conn = _conn()
    conn.close()


# --- Tool CRUD ---

def get_tools():
    with _conn() as c:
        rows = c.execute('SELECT id, name, exe_path, args_template FROM tool ORDER BY id').fetchall()
    return [Tool.from_row(r) for r in rows]


def get_tool(tool_id):
    with _conn() as c:
        row = c.execute('SELECT id, name, exe_path, args_template FROM tool WHERE id=?', (tool_id,)).fetchone()
    return Tool.from_row(row) if row else None


def add_tool(name, exe_path, args_template):
    with _conn() as c:
        cur = c.execute('INSERT INTO tool (name, exe_path, args_template) VALUES (?,?,?)',
                        (name, exe_path, args_template))
        c.commit()
    return cur.lastrowid


def update_tool(tool_id, name, exe_path, args_template):
    with _conn() as c:
        c.execute('UPDATE tool SET name=?, exe_path=?, args_template=? WHERE id=?',
                  (name, exe_path, args_template, tool_id))
        c.commit()
    return c.rowcount if hasattr(c, 'rowcount') else 1


def delete_tool(tool_id):
    with _conn() as c:
        c.execute('DELETE FROM tool WHERE id=?', (tool_id,))
        c.commit()


# --- Pipeline CRUD ---

def get_pipelines():
    with _conn() as c:
        rows = c.execute('SELECT id, name, steps FROM pipeline ORDER BY id').fetchall()
    return [Pipeline.from_row(r) for r in rows]


def get_pipeline(pipeline_id):
    with _conn() as c:
        row = c.execute('SELECT id, name, steps FROM pipeline WHERE id=?', (pipeline_id,)).fetchone()
    return Pipeline.from_row(row) if row else None


def add_pipeline(name, steps):
    with _conn() as c:
        cur = c.execute('INSERT INTO pipeline (name, steps) VALUES (?,?)', (name, steps))
        c.commit()
    return cur.lastrowid


def update_pipeline(pipeline_id, name, steps):
    with _conn() as c:
        c.execute('UPDATE pipeline SET name=?, steps=? WHERE id=?', (name, steps, pipeline_id))
        c.commit()


def delete_pipeline(pipeline_id):
    with _conn() as c:
        c.execute('DELETE FROM pipeline WHERE id=?', (pipeline_id,))
        c.commit()
