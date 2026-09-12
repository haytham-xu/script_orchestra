"""
File-Git Repository Manager - Multi-repository management service.

Manages the registry of repositories and initializes
each repo's .fgit/ structure as defined in REQUIREMENTS §3.6.
"""
import json
import os
import shutil
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, List, Optional


_DB_PATH = os.path.join(os.path.dirname(__file__), 'file_git.db')

VALID_MODES = ("ORIGINAL", "ENCRYPTED")
VALID_STATUSES = ("ready", "syncing", "error", "locked")


def init_db() -> None:
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS repos (
                id           TEXT PRIMARY KEY,
                name         TEXT NOT NULL,
                local_path   TEXT NOT NULL UNIQUE,
                mode         TEXT NOT NULL,
                created_at   TEXT NOT NULL,
                last_updated TEXT NOT NULL,
                initialized  INTEGER NOT NULL DEFAULT 1,
                status       TEXT NOT NULL DEFAULT 'ready'
            )
        """)


@contextmanager
def _conn():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _row_to_dict(row) -> Dict:
    d = dict(row)
    d['initialized'] = bool(d['initialized'])
    return d


def _load_repos() -> List[Dict]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM repos ORDER BY created_at").fetchall()
    return [_row_to_dict(r) for r in rows]


def _save_repo(repo: Dict) -> None:
    with _conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO repos
                (id, name, local_path, mode, created_at, last_updated, initialized, status)
            VALUES
                (:id, :name, :local_path, :mode, :created_at, :last_updated, :initialized, :status)
        """, {**repo, 'initialized': int(repo.get('initialized', True))})


def _delete_repo_row(repo_id: str) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM repos WHERE id = ?", (repo_id,))


def _default_config(mode: str, local_path: str) -> Dict:
    """Initial .fgit/config.json content (see REQUIREMENTS §3.6)."""
    return {
        "mode": mode,
        "password": "",
        "local_path": local_path,
        "remote_path": "",
        "baidu_cloud": {
            "app_id": "",
            "secret_key": "",
            "app_key": "",
            "sign_code": "",
            "expires_in": "",
            "refresh_token": "",
            "access_token": "",
        },
        "hook_retention_days": 7,
    }


def _default_queue() -> Dict:
    """Initial .fgit/queue.json content (empty, unlocked)."""
    return {
        "lock": False,
        "action_folder": None,
        "action_type": None,
        "queue": {},
    }


def _default_index() -> Dict:
    """Initial empty index (local/cloud share the same shape)."""
    return {}


def _init_fgit_structure(local_path: str, mode: str) -> None:
    """Create .fgit/ directory tree required by REQUIREMENTS §3.6."""
    fgit = os.path.join(local_path, '.fgit')
    os.makedirs(fgit, exist_ok=True)
    os.makedirs(os.path.join(fgit, 'buffer'), exist_ok=True)
    os.makedirs(os.path.join(fgit, 'trash'), exist_ok=True)
    os.makedirs(os.path.join(fgit, 'action'), exist_ok=True)

    _write_json_if_absent(os.path.join(fgit, 'config.json'), _default_config(mode, local_path))
    _write_json_if_absent(os.path.join(fgit, 'queue.json'), _default_queue())
    _write_json_if_absent(os.path.join(fgit, 'local_index.json'), _default_index())
    _write_json_if_absent(os.path.join(fgit, 'cloud_index.json'), _default_index())


def _write_json_if_absent(path: str, data: Dict) -> None:
    if os.path.exists(path):
        return
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


class RepositoryManager:
    """Manages the file-git repository registry (SQLite-backed)."""

    @staticmethod
    def list_repos() -> List[Dict]:
        return _load_repos()

    @staticmethod
    def get_repo_by_id(repo_id: str) -> Optional[Dict]:
        with _conn() as conn:
            row = conn.execute("SELECT * FROM repos WHERE id = ?", (repo_id,)).fetchone()
        return _row_to_dict(row) if row else None

    @staticmethod
    def add_repo(local_path: str, mode: str, skip_init: bool = False) -> Dict:
        """Register a new repository.

        Args:
            local_path: absolute path to the local folder
            mode: "ORIGINAL" or "ENCRYPTED" (immutable after creation)
            skip_init: if True, treat as import — .fgit/ must already exist

        Returns:
            The created repo entry.

        Raises:
            ValueError on invalid arguments or existing registration.
        """
        if not os.path.isabs(local_path):
            raise ValueError("local_path must be an absolute path")
        if not os.path.exists(local_path):
            raise ValueError(f"Path does not exist: {local_path}")
        if not os.path.isdir(local_path):
            raise ValueError(f"Path is not a directory: {local_path}")
        if mode not in VALID_MODES:
            raise ValueError(f"mode must be one of {VALID_MODES}")

        with _conn() as conn:
            existing = conn.execute(
                "SELECT id FROM repos WHERE local_path = ?", (local_path,)
            ).fetchone()
        if existing:
            raise ValueError(f"Repository already registered: {local_path}")

        fgit_path = os.path.join(local_path, '.fgit')

        if skip_init:
            if not os.path.exists(fgit_path):
                raise ValueError(
                    f".fgit folder not found at {local_path}. "
                    "Cannot import a repo without initialization."
                )
            config_path = os.path.join(fgit_path, 'config.json')
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                mode = config.get('mode', mode)
        else:
            _init_fgit_structure(local_path, mode)

        now = datetime.now().isoformat()
        repo = {
            "id": str(uuid.uuid4()),
            "name": os.path.basename(local_path.rstrip('/\\')),
            "local_path": local_path,
            "mode": mode,
            "created_at": now,
            "last_updated": now,
            "initialized": True,
            "status": "ready",
        }
        _save_repo(repo)
        return repo

    @staticmethod
    def delete_repo(repo_id: str) -> bool:
        """Remove a repo from the registry AND delete its .fgit/ folder."""
        repo = RepositoryManager.get_repo_by_id(repo_id)
        if not repo:
            return False

        fgit_path = os.path.join(repo['local_path'], '.fgit')
        if os.path.exists(fgit_path):
            try:
                shutil.rmtree(fgit_path)
            except Exception as exc:
                print(f"[RepositoryManager] Failed to remove .fgit at {fgit_path}: {exc}")

        _delete_repo_row(repo_id)
        return True

    @staticmethod
    def update_status(repo_id: str, status: str) -> bool:
        if status not in VALID_STATUSES:
            raise ValueError(f"status must be one of {VALID_STATUSES}")
        return RepositoryManager._patch_repo(repo_id, {"status": status})

    @staticmethod
    def update_last_updated(repo_id: str) -> bool:
        return RepositoryManager._patch_repo(repo_id, {})

    @staticmethod
    def _patch_repo(repo_id: str, patch: Dict) -> bool:
        with _conn() as conn:
            row = conn.execute("SELECT * FROM repos WHERE id = ?", (repo_id,)).fetchone()
            if not row:
                return False
            repo = _row_to_dict(row)
            repo.update(patch)
            repo['last_updated'] = datetime.now().isoformat()
        _save_repo(repo)
        return True
