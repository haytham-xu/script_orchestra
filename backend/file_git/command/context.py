"""
Shared command setup: load repo metadata + config, derive key,
choose the CloudStorage backend.

Commands should never touch ``.fgit/config.json`` directly — they go
through ``build_context(repo_id)`` and use the returned ``RepoContext``.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

from ..cloud import CloudStorage, MockCloudStorage
from ..crypto import derive_key
from ..repository_manager import RepositoryManager
from ..settings_manager import SettingsManager


CLOUD_INDEX_REMOTE_FILENAME = "cloud_index.json"


@dataclass
class RepoContext:
    repo_id: str
    repo_root: str
    mode: str                    # "ORIGINAL" or "ENCRYPTED"
    remote_root: str             # e.g. "/backup/photos"
    storage: CloudStorage
    key: Optional[bytes]         # None for ORIGINAL, 32 bytes for ENCRYPTED
    config: dict                 # full config.json (for advanced uses)

    def cloud_index_remote_path(self) -> str:
        """The remote path of the cloud_index.json blob (§3.9)."""
        return f"{self.remote_root.rstrip('/')}/{CLOUD_INDEX_REMOTE_FILENAME}"


def build_context(repo_id: str) -> RepoContext:
    """Assemble the runtime context for ``repo_id``.

    Raises:
        LookupError: repo doesn't exist
        ValueError: config is missing required fields
    """
    repo = RepositoryManager.get_repo_by_id(repo_id)
    if not repo:
        raise LookupError(f"repo not found: {repo_id}")

    config_path = os.path.join(repo["local_path"], ".fgit", "config.json")
    if not os.path.isfile(config_path):
        raise ValueError(f"missing config.json in {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    remote_root = config.get("remote_path", "").strip()
    if not remote_root:
        raise ValueError(
            f"remote_path is not configured for repo '{repo['name']}'. "
            "Set it in the UI first."
        )

    mode = config.get("mode") or repo["mode"]
    key = None
    if mode == "ENCRYPTED":
        password = config.get("password", "")
        if not password:
            raise ValueError(
                f"ENCRYPTED repo '{repo['name']}' has no password set. "
                "Set it in the UI first."
            )
        # Use remote_path as the KDF salt so any two machines pointing at
        # the same cloud folder with the same password derive the same
        # key. repo_id is per-machine and would break cross-machine sync.
        key = derive_key(password, remote_root)

    storage = _build_storage()

    return RepoContext(
        repo_id=repo_id,
        repo_root=repo["local_path"],
        mode=mode,
        remote_root=remote_root,
        storage=storage,
        key=key,
        config=config,
    )


def _build_storage() -> CloudStorage:
    """Pick a CloudStorage backend based on global settings.

    For now only MockCloudStorage is available; BaiduStorage will land
    in phase 6. Falls back to a local mock root under
    ``<file_git>/mock_cloud_storage/`` for development.
    """
    settings = SettingsManager.get_settings()
    # In phase 1-5 the only backend is mock. Point it at a stable
    # per-installation folder so restarts see the same "cloud".
    mock_root = os.environ.get("FILE_GIT_MOCK_ROOT")
    if not mock_root:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        mock_root = os.path.join(base, "mock_cloud_storage")
    return MockCloudStorage(mock_root)
