"""
File-Git Repository Manager - Multi-repository management service.

Manages the registry of repositories (repos.json) and initializes
each repo's .fgit/ structure as defined in REQUIREMENTS §3.6.
"""
import json
import os
import shutil
import uuid
from datetime import datetime
from typing import Dict, List, Optional


REPOS_FILE = os.path.join(os.path.dirname(__file__), 'repos.json')

VALID_MODES = ("ORIGINAL", "ENCRYPTED")
VALID_STATUSES = ("ready", "syncing", "error", "locked")


def _load_repos() -> List[Dict]:
    if not os.path.exists(REPOS_FILE):
        return []
    with open(REPOS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def _save_repos(repos: List[Dict]) -> None:
    with open(REPOS_FILE, 'w', encoding='utf-8') as f:
        json.dump(repos, f, indent=2, ensure_ascii=False)


def _default_config(mode: str, local_path: str) -> Dict:
    """Initial .fgit/config.json content (see REQUIREMENTS §3.6)."""
    return {
        "mode": mode,
        "password": "",              # ENCRYPTED repo only; set later via UI
        "local_path": local_path,
        "remote_path": "",           # cloud root path; set later via UI
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

    _write_json_if_absent(
        os.path.join(fgit, 'config.json'),
        _default_config(mode, local_path),
    )
    _write_json_if_absent(
        os.path.join(fgit, 'queue.json'),
        _default_queue(),
    )
    _write_json_if_absent(
        os.path.join(fgit, 'local_index.json'),
        _default_index(),
    )
    _write_json_if_absent(
        os.path.join(fgit, 'cloud_index.json'),
        _default_index(),
    )


def _write_json_if_absent(path: str, data: Dict) -> None:
    if os.path.exists(path):
        return
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


class RepositoryManager:
    """Manages the global repos.json registry."""

    @staticmethod
    def list_repos() -> List[Dict]:
        return _load_repos()

    @staticmethod
    def get_repo_by_id(repo_id: str) -> Optional[Dict]:
        for repo in _load_repos():
            if repo['id'] == repo_id:
                return repo
        return None

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

        repos = _load_repos()
        for repo in repos:
            if repo['local_path'] == local_path:
                raise ValueError(f"Repository already registered: {local_path}")

        fgit_path = os.path.join(local_path, '.fgit')
        fgit_exists = os.path.exists(fgit_path)

        if skip_init:
            if not fgit_exists:
                raise ValueError(
                    f".fgit folder not found at {local_path}. "
                    "Cannot import a repo without initialization."
                )
            # Trust existing config's mode for imported repos.
            config_path = os.path.join(fgit_path, 'config.json')
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                mode = config.get('mode', mode)
        else:
            _init_fgit_structure(local_path, mode)

        repo_id = str(uuid.uuid4())
        repo_name = os.path.basename(local_path.rstrip('/\\'))
        now = datetime.now().isoformat()

        repo = {
            "id": repo_id,
            "name": repo_name,
            "local_path": local_path,
            "mode": mode,
            "created_at": now,
            "last_updated": now,
            "initialized": True,
            "status": "ready",
        }
        repos.append(repo)
        _save_repos(repos)
        return repo

    @staticmethod
    def delete_repo(repo_id: str) -> bool:
        """Remove a repo from the registry AND delete its .fgit/ folder."""
        repos = _load_repos()
        target = next((r for r in repos if r['id'] == repo_id), None)
        if not target:
            return False

        fgit_path = os.path.join(target['local_path'], '.fgit')
        if os.path.exists(fgit_path):
            try:
                shutil.rmtree(fgit_path)
            except Exception as exc:
                print(f"[RepositoryManager] Failed to remove .fgit at {fgit_path}: {exc}")

        _save_repos([r for r in repos if r['id'] != repo_id])
        return True

    @staticmethod
    def update_status(repo_id: str, status: str) -> bool:
        if status not in VALID_STATUSES:
            raise ValueError(f"status must be one of {VALID_STATUSES}")
        return RepositoryManager._patch_repo(repo_id, {"status": status})

    @staticmethod
    def update_last_updated(repo_id: str) -> bool:
        return RepositoryManager._patch_repo(repo_id, {})  # touch timestamp

    @staticmethod
    def _patch_repo(repo_id: str, patch: Dict) -> bool:
        repos = _load_repos()
        for repo in repos:
            if repo['id'] == repo_id:
                repo.update(patch)
                repo['last_updated'] = datetime.now().isoformat()
                _save_repos(repos)
                return True
        return False
