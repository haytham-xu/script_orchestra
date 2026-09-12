"""
Shared fixtures and helpers for file_git E2E tests.

Environment / config:
    TEST_REMOTE_ROOT            remote path for PLAIN suite (mandatory)
    TEST_REMOTE_ROOT_ENCRYPTED  remote path for ENCRYPTED suite (optional)
    FILE_GIT_BASE_URL           defaults to http://127.0.0.1:50001
    FILE_GIT_MOCK_ROOT          override for mock cloud root (default: test_runtime/mock_cloud)

Reading either from env vars or from config_local values injected at import time.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import tempfile
from pathlib import Path
from typing import Optional

import pytest
import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL = os.environ.get("FILE_GIT_BASE_URL", "http://127.0.0.1:50001")

TEST_REMOTE_ROOT = os.environ.get("TEST_REMOTE_ROOT")
TEST_REMOTE_ROOT_ENCRYPTED = os.environ.get("TEST_REMOTE_ROOT_ENCRYPTED")

# Mock cloud root: fixed path next to this file (gitignored via **/test_runtime/).
# Override with FILE_GIT_MOCK_ROOT env when needed.
_DEFAULT_MOCK_ROOT = str(Path(__file__).parent / "test_runtime" / "mock_cloud")
MOCK_ROOT = os.environ.get("FILE_GIT_MOCK_ROOT") or _DEFAULT_MOCK_ROOT


# ---------------------------------------------------------------------------
# Low-level HTTP helpers
# ---------------------------------------------------------------------------

def api(method: str, path: str, timeout: int = 30, **kwargs) -> dict:
    """Make a request and return the parsed JSON body.  Raises on HTTP errors."""
    url = BASE_URL + path
    resp = requests.request(method, url, timeout=timeout, **kwargs)
    resp.raise_for_status()
    return resp.json()


def post(path: str, body: Optional[dict] = None, timeout: int = 30) -> dict:
    return api("POST", path, timeout=timeout, json=body or {})


def put(path: str, body: dict, timeout: int = 30) -> dict:
    return api("PUT", path, timeout=timeout, json=body)


def delete(path: str, timeout: int = 30) -> dict:
    return api("DELETE", path, timeout=timeout)


# ---------------------------------------------------------------------------
# Mock cloud helpers (filesystem-based, mirrors MockCloudStorage)
# ---------------------------------------------------------------------------

def mock_remote_path(remote_root: str) -> Path:
    """Resolve the on-disk directory that backs remote_root in MockCloudStorage.

    MockCloudStorage stores files at:
        <MOCK_ROOT>/<remote_root_stripped_leading_slash>/
    """
    stripped = remote_root.lstrip("/")
    return Path(MOCK_ROOT) / stripped


def mock_upload(remote_root: str, middle_path: str, content: bytes) -> None:
    """Write content to the mock remote at remote_root/middle_path."""
    dest = mock_remote_path(remote_root) / middle_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)


def mock_download(remote_root: str, relative_path: str) -> bytes:
    """Read content from the mock remote."""
    src = mock_remote_path(remote_root) / relative_path
    return src.read_bytes()


def mock_list(remote_root: str) -> list[str]:
    """Return all relative paths under the mock remote root (non-.fgit files)."""
    base = mock_remote_path(remote_root)
    if not base.exists():
        return []
    results = []
    for p in base.rglob("*"):
        if p.is_file():
            rel = p.relative_to(base).as_posix()
            if not rel.startswith(".fgit/"):
                results.append(rel)
    return results


def mock_exists(remote_root: str, relative_path: str) -> bool:
    return (mock_remote_path(remote_root) / relative_path).exists()


def mock_cleanup_remote(remote_root: str) -> None:
    """Remove the entire mock remote directory for this root."""
    p = mock_remote_path(remote_root)
    if p.exists():
        shutil.rmtree(p)


# ---------------------------------------------------------------------------
# Local index / cloud index readers
# ---------------------------------------------------------------------------

def read_local_index(repo_root: str) -> dict:
    path = Path(repo_root) / ".fgit" / "local_index.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_cloud_index(repo_root: str) -> dict:
    path = Path(repo_root) / ".fgit" / "cloud_index.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_queue(repo_root: str) -> dict:
    path = Path(repo_root) / ".fgit" / "queue.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Action log readers
# ---------------------------------------------------------------------------

def read_success_log(repo_root: str, action_folder: str) -> list[str]:
    """Return lines from success.log for the given action folder."""
    p = Path(repo_root) / ".fgit" / "action" / action_folder / "log" / "success.log"
    if not p.exists():
        return []
    return [line for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_error_log(repo_root: str, action_folder: str) -> list[str]:
    p = Path(repo_root) / ".fgit" / "action" / action_folder / "log" / "error.log"
    if not p.exists():
        return []
    return [line for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_file_log(repo_root: str, action_folder: str) -> list[dict]:
    """Return parsed records from file_log.jsonl."""
    p = Path(repo_root) / ".fgit" / "action" / action_folder / "log" / "file_log.jsonl"
    if not p.exists():
        return []
    records = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def file_log_actions(repo_root: str, action_folder: str) -> list[str]:
    """Return the 'action' field of every file_log.jsonl record."""
    return [r["action"] for r in read_file_log(repo_root, action_folder)]


# ---------------------------------------------------------------------------
# Trash helpers
# ---------------------------------------------------------------------------

def local_trash_files(repo_root: str) -> list[str]:
    """Return relative paths of all files currently in .fgit/trash/."""
    base = Path(repo_root) / ".fgit" / "trash"
    if not base.exists():
        return []
    return [p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()]


def local_trash_count(repo_root: str) -> int:
    return len(local_trash_files(repo_root))


def remote_trash_files(remote_root: str) -> list[str]:
    """Return filenames (flat) under remote .fgit/_trash/ for mock storage."""
    base = mock_remote_path(remote_root) / ".fgit" / "_trash"
    if not base.exists():
        return []
    return [p.name for p in base.rglob("*") if p.is_file()]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def remote_root_plain() -> str:
    root = TEST_REMOTE_ROOT
    assert root, (
        "TEST_REMOTE_ROOT is not set. "
        "Export it as an env var or add it to config_local.py before running e2e tests."
    )
    return root


@pytest.fixture(scope="session")
def remote_root_encrypted() -> str:
    root = TEST_REMOTE_ROOT_ENCRYPTED
    assert root, (
        "TEST_REMOTE_ROOT_ENCRYPTED is not set. "
        "Export it or add to config_local.py."
    )
    return root


@pytest.fixture(scope="session")
def backend_alive():
    """Fail fast if the backend is not reachable."""
    try:
        r = requests.get(BASE_URL + "/health", timeout=5)
        r.raise_for_status()
    except Exception as exc:
        pytest.fail(f"Backend not reachable at {BASE_URL}: {exc}")


@pytest.fixture()
def tmp_local_dir(tmp_path):
    """Return a freshly created temporary directory for a repo root."""
    return str(tmp_path)
