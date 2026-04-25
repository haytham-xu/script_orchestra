"""
File-Git Repository Manager - Multi-repository management service
"""
import json
import os
import uuid
from datetime import datetime
from typing import List, Dict, Optional


class RepositoryManager:
    """Manages multiple file-git repositories"""

    REPOS_FILE = os.path.join(os.path.dirname(__file__), 'repos.json')

    @staticmethod
    def _load_repos() -> List[Dict]:
        """Load repositories from repos.json"""
        if not os.path.exists(RepositoryManager.REPOS_FILE):
            return []
        with open(RepositoryManager.REPOS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def _save_repos(repos: List[Dict]):
        """Save repositories to repos.json"""
        with open(RepositoryManager.REPOS_FILE, 'w', encoding='utf-8') as f:
            json.dump(repos, f, indent=2, ensure_ascii=False)

    @staticmethod
    def list_repos() -> List[Dict]:
        """List all repositories"""
        return RepositoryManager._load_repos()

    @staticmethod
    def get_repo_by_id(repo_id: str) -> Optional[Dict]:
        """Get repository by ID"""
        repos = RepositoryManager._load_repos()
        for repo in repos:
            if repo['id'] == repo_id:
                return repo
        return None

    @staticmethod
    def add_repo(local_path: str, mode: str, skip_init: bool = False) -> Dict:
        """
        Add new repository and optionally initialize .fgit folder

        Args:
            local_path: Absolute path to local folder
            mode: "ORIGINAL" or "ENCRYPTED"
            skip_init: If True, skip .fgit initialization (for existing repos)

        Returns:
            Created repository dict
        """
        # Validate path
        if not os.path.isabs(local_path):
            raise ValueError("local_path must be an absolute path")

        if not os.path.exists(local_path):
            raise ValueError(f"Path does not exist: {local_path}")

        if not os.path.isdir(local_path):
            raise ValueError(f"Path is not a directory: {local_path}")

        # Validate mode
        if mode not in ["ORIGINAL", "ENCRYPTED"]:
            raise ValueError("mode must be 'ORIGINAL' or 'ENCRYPTED'")

        # Check if repo already exists
        repos = RepositoryManager._load_repos()
        for repo in repos:
            if repo['local_path'] == local_path:
                raise ValueError(f"Repository already exists for path: {local_path}")

        # Generate repo ID and name
        repo_id = str(uuid.uuid4())
        repo_name = os.path.basename(local_path)
        now = datetime.now().isoformat()

        # Check if .fgit already exists
        fgit_path = os.path.join(local_path, '.fgit')
        fgit_exists = os.path.exists(fgit_path)

        if skip_init and not fgit_exists:
            raise ValueError(f".fgit folder not found at {local_path}. Cannot import repo without initialization.")

        if not skip_init:
            # Initialize .fgit folder structure
            os.makedirs(fgit_path, exist_ok=True)
            os.makedirs(os.path.join(fgit_path, 'buffer'), exist_ok=True)
            os.makedirs(os.path.join(fgit_path, 'trash'), exist_ok=True)
            os.makedirs(os.path.join(fgit_path, 'action'), exist_ok=True)

            # Create initial config.json (only if not exists or not skipping init)
            config_path = os.path.join(fgit_path, 'config.json')
            if not os.path.exists(config_path):
                initial_config = {
                    "mode": mode,
                    "password": "",  # To be set by user during initialization
                    "local_path": local_path,
                    "remote_path": "",  # To be set by user
                    "app_id": "",
                    "secret_key": "",
                    "app_key": "",
                    "sign_code": "",
                    "expires_in": "",
                    "refresh_token": "",
                    "access_token": ""
                }
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(initial_config, f, indent=2, ensure_ascii=False)
        else:
            # If skipping init, read mode from existing config
            config_path = os.path.join(fgit_path, 'config.json')
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    mode = config.get('mode', mode)  # Use existing mode from config

        # Create repo entry
        repo = {
            "id": repo_id,
            "name": repo_name,
            "local_path": local_path,
            "mode": mode,
            "created_at": now,
            "last_updated": now,
            "initialized": True,  # Now always true since we just initialized it or it already exists
            "status": "ready"  # ready, syncing, error
        }

        # Save
        repos.append(repo)
        RepositoryManager._save_repos(repos)

        return repo
        initial_config = {
            "mode": mode,
            "password": "",  # To be set by user during initialization
            "local_path": local_path,
            "remote_path": "",  # To be set by user
            "app_id": "",
            "secret_key": "",
            "app_key": "",
            "sign_code": "",
            "expires_in": "",
            "refresh_token": "",
            "access_token": ""
        }
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(initial_config, f, indent=2, ensure_ascii=False)

        # Create repo entry
        repo = {
            "id": repo_id,
            "name": repo_name,
            "local_path": local_path,
            "mode": mode,
            "created_at": now,
            "last_updated": now,
            "initialized": True,  # Now always true since we just initialized it
            "status": "ready"  # ready, syncing, error
        }

        # Save
        repos.append(repo)
        RepositoryManager._save_repos(repos)

        return repo

    @staticmethod
    def delete_repo(repo_id: str) -> bool:
        """
        Delete repository from registry and remove .fgit folder

        Args:
            repo_id: Repository ID

        Returns:
            True if deleted, False if not found
        """
        import shutil

        repos = RepositoryManager._load_repos()
        repo_to_delete = None

        # Find the repo
        for repo in repos:
            if repo['id'] == repo_id:
                repo_to_delete = repo
                break

        if not repo_to_delete:
            return False

        # Remove .fgit folder if it exists
        local_path = repo_to_delete['local_path']
        fgit_path = os.path.join(local_path, '.fgit')
        if os.path.exists(fgit_path):
            try:
                shutil.rmtree(fgit_path)
            except Exception as e:
                print(f"Warning: Failed to delete .fgit folder: {e}")

        # Remove from repos list
        repos = [r for r in repos if r['id'] != repo_id]
        RepositoryManager._save_repos(repos)
        return True

    @staticmethod
    def update_repo_status(repo_id: str, initialized: bool):
        """Update repository initialization status"""
        repos = RepositoryManager._load_repos()
        for repo in repos:
            if repo['id'] == repo_id:
                repo['initialized'] = initialized
                repo['last_updated'] = datetime.now().isoformat()
                RepositoryManager._save_repos(repos)
                return True
        return False

    @staticmethod
    def update_last_updated(repo_id: str):
        """Update repository last_updated timestamp"""
        repos = RepositoryManager._load_repos()
        for repo in repos:
            if repo['id'] == repo_id:
                repo['last_updated'] = datetime.now().isoformat()
                RepositoryManager._save_repos(repos)
                return True
        return False

    @staticmethod
    def update_status(repo_id: str, status: str):
        """
        Update repository status

        Args:
            repo_id: Repository ID
            status: One of "ready", "syncing", "error"
        """
        repos = RepositoryManager._load_repos()
        for repo in repos:
            if repo['id'] == repo_id:
                repo['status'] = status
                repo['last_updated'] = datetime.now().isoformat()
                RepositoryManager._save_repos(repos)
                return True
        return False
