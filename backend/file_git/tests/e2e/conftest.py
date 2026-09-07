"""
conftest.py — pytest fixtures for file_git E2E tests.

Helpers (non-fixture functions) live in helpers.py.

Storage fixtures
----------------
Two mutually exclusive fixtures control which CloudStorage the backend uses:

  use_mock_storage   — flips use_mock_baidu=True + sets mock_root.
                       Used by test_plain.py (default CI path).

  use_real_storage   — flips use_mock_baidu=False.
                       Used by test_plain_real.py (requires real Baidu token).

Each test module declares exactly one of these via a module-scoped autouse
fixture defined in that file. Neither is autouse here so they don't
interfere with each other.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import requests

from helpers import BASE_URL, api

# Default mock cloud root: next to this file so it's gitignored by **/test_data/.
# Override with FILE_GIT_MOCK_ROOT env when you need a different location.
_DEFAULT_MOCK_ROOT = str(Path(__file__).parent / "test_data" / "mock_cloud")

# ---------------------------------------------------------------------------
# Backend reachability
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def backend_alive():
    """Fail fast if the backend is not reachable."""
    try:
        r = requests.get(BASE_URL + "/health", timeout=5)
        r.raise_for_status()
    except Exception as exc:
        pytest.fail(f"Backend not reachable at {BASE_URL}: {exc}")


# ---------------------------------------------------------------------------
# Remote root fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def remote_root_plain() -> str:
    root = os.environ.get("TEST_REMOTE_ROOT")
    assert root, (
        "TEST_REMOTE_ROOT is not set. "
        "Export it before running e2e tests."
    )
    import time
    ts = time.strftime("%Y%m%d_%H%M%S")
    return f"{root}/{ts}"


@pytest.fixture(scope="session")
def remote_root_encrypted() -> str:
    root = os.environ.get("TEST_REMOTE_ROOT_ENCRYPTED")
    assert root, (
        "TEST_REMOTE_ROOT_ENCRYPTED is not set. "
        "Export it before running e2e tests."
    )
    return root


# ---------------------------------------------------------------------------
# Storage-mode fixtures  (NOT autouse — each test module opts in explicitly)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def use_mock_storage():
    """Switch backend to MockCloudStorage.

    Uses test_data/mock_cloud next to this file by default.
    Override with FILE_GIT_MOCK_ROOT env when needed.
    """
    mock_root = os.environ.get("FILE_GIT_MOCK_ROOT") or _DEFAULT_MOCK_ROOT
    Path(mock_root).mkdir(parents=True, exist_ok=True)

    orig = api("GET", "/file-git/settings")["settings"]
    api("PUT", "/file-git/settings", json={"use_mock_baidu": True, "mock_root": mock_root})

    yield

    api("PUT", "/file-git/settings", json={
        "use_mock_baidu": orig.get("use_mock_baidu", False),
        "mock_root": orig.get("mock_root", ""),
    })


@pytest.fixture(scope="session")
def use_real_storage():
    """Switch backend to real BaiduCloudStorage. Restores original setting after."""
    orig = api("GET", "/file-git/settings")["settings"]
    api("PUT", "/file-git/settings", json={"use_mock_baidu": False})

    yield

    api("PUT", "/file-git/settings", json={
        "use_mock_baidu": orig.get("use_mock_baidu", True),
    })
