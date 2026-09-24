import json
from shared.db import get_conn
from .entity import Tool, Pipeline, Password

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
    """CREATE TABLE IF NOT EXISTS file_pipeline_password (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        value TEXT NOT NULL,
        note TEXT NOT NULL DEFAULT '',
        sort_order INTEGER NOT NULL DEFAULT 0
    )""",
]


def _conn():
    conn = get_conn()
    for stmt in _SCHEMA:
        conn.execute(stmt)
    conn.commit()
    # add run_config column if missing (SQLite has no IF NOT EXISTS for ALTER TABLE)
    try:
        conn.execute("ALTER TABLE file_pipeline_pipeline ADD COLUMN run_config TEXT NOT NULL DEFAULT '{}'")
        conn.commit()
    except Exception:
        pass
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
        rows = c.execute('SELECT id, name, steps, run_config FROM file_pipeline_pipeline ORDER BY id').fetchall()
    return [Pipeline.from_row(r) for r in rows]


def get_pipeline(pipeline_id):
    with _conn() as c:
        row = c.execute('SELECT id, name, steps, run_config FROM file_pipeline_pipeline WHERE id=?', (pipeline_id,)).fetchone()
    return Pipeline.from_row(row) if row else None


def add_pipeline(name, steps):
    with _conn() as c:
        cur = c.execute("INSERT INTO file_pipeline_pipeline (name, steps, run_config) VALUES (?,?,'{}')", (name, steps))
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


# --- Run config ---

def get_run_config(pipeline_id):
    with _conn() as c:
        row = c.execute('SELECT run_config FROM file_pipeline_pipeline WHERE id=?', (pipeline_id,)).fetchone()
    if not row:
        return {}
    try:
        return json.loads(row[0] or '{}')
    except Exception:
        return {}


def save_run_config(pipeline_id, config: dict):
    with _conn() as c:
        c.execute('UPDATE file_pipeline_pipeline SET run_config=? WHERE id=?',
                  (json.dumps(config), pipeline_id))
        c.commit()


# --- Password CRUD ---

def get_passwords():
    with _conn() as c:
        rows = c.execute('SELECT id, value, note FROM file_pipeline_password ORDER BY sort_order, id').fetchall()
    return [Password.from_row(r) for r in rows]


def add_password(value, note=''):
    with _conn() as c:
        cur = c.execute('INSERT INTO file_pipeline_password (value, note) VALUES (?,?)', (value, note))
        c.commit()
    return cur.lastrowid


def update_password(pwd_id, value, note=''):
    with _conn() as c:
        c.execute('UPDATE file_pipeline_password SET value=?, note=? WHERE id=?', (value, note, pwd_id))
        c.commit()


def delete_password(pwd_id):
    with _conn() as c:
        c.execute('DELETE FROM file_pipeline_password WHERE id=?', (pwd_id,))
        c.commit()


def reorder_passwords(ordered_ids: list):
    with _conn() as c:
        for i, pid in enumerate(ordered_ids):
            c.execute('UPDATE file_pipeline_password SET sort_order=? WHERE id=?', (i, pid))
        c.commit()
