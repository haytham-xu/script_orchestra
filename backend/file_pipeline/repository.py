from shared.db import get_conn
from .entity import Tool, Pipeline

_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS file_pipeline_tool (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        exe_path TEXT NOT NULL,
        args_template TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS file_pipeline_pipeline (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        steps TEXT NOT NULL
    )""",
]


def _conn():
    conn = get_conn()
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
        rows = c.execute('SELECT id, name, exe_path, args_template FROM file_pipeline_tool ORDER BY id').fetchall()
    return [Tool.from_row(r) for r in rows]


def get_tool(tool_id):
    with _conn() as c:
        row = c.execute('SELECT id, name, exe_path, args_template FROM file_pipeline_tool WHERE id=?', (tool_id,)).fetchone()
    return Tool.from_row(row) if row else None


def add_tool(name, exe_path, args_template):
    with _conn() as c:
        cur = c.execute('INSERT INTO file_pipeline_tool (name, exe_path, args_template) VALUES (?,?,?)',
                        (name, exe_path, args_template))
        c.commit()
    return cur.lastrowid


def update_tool(tool_id, name, exe_path, args_template):
    with _conn() as c:
        c.execute('UPDATE file_pipeline_tool SET name=?, exe_path=?, args_template=? WHERE id=?',
                  (name, exe_path, args_template, tool_id))
        c.commit()
    return c.rowcount if hasattr(c, 'rowcount') else 1


def delete_tool(tool_id):
    with _conn() as c:
        c.execute('DELETE FROM file_pipeline_tool WHERE id=?', (tool_id,))
        c.commit()


# --- Pipeline CRUD ---

def get_pipelines():
    with _conn() as c:
        rows = c.execute('SELECT id, name, steps FROM file_pipeline_pipeline ORDER BY id').fetchall()
    return [Pipeline.from_row(r) for r in rows]


def get_pipeline(pipeline_id):
    with _conn() as c:
        row = c.execute('SELECT id, name, steps FROM file_pipeline_pipeline WHERE id=?', (pipeline_id,)).fetchone()
    return Pipeline.from_row(row) if row else None


def add_pipeline(name, steps):
    with _conn() as c:
        cur = c.execute('INSERT INTO file_pipeline_pipeline (name, steps) VALUES (?,?)', (name, steps))
        c.commit()
    return cur.lastrowid


def update_pipeline(pipeline_id, name, steps):
    with _conn() as c:
        c.execute('UPDATE file_pipeline_pipeline SET name=?, steps=? WHERE id=?', (name, steps, pipeline_id))
        c.commit()


def delete_pipeline(pipeline_id):
    with _conn() as c:
        c.execute('DELETE FROM file_pipeline_pipeline WHERE id=?', (pipeline_id,))
        c.commit()
