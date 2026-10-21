"""
Manual Upload — fill-gaps mode E2E tests.

Tests the batch-scan granularity and fill-gaps behavior:
  * subpath="" / "/" → batch by first-level subdirs of repo root
  * subpath="3d"     → batch by first-level subdirs under 3d/
  * A batch is SKIPPED if ANY of its files already exist on cloud.
  * Files sitting directly in subpath (no subfolder) are excluded entirely.

These tests use MockCloudStorage. The test manages its own remote_root so no
environment variables are required.

Run:
    pytest backend/file_git/tests/e2e/test_manual_upload.py -v
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from helpers import (
    api, post, put, delete,
    read_queue,
)

# ---------------------------------------------------------------------------
# Module-level remote root (fixed for mock; no env var needed)
# ---------------------------------------------------------------------------

REMOTE_ROOT = "/test_manual_upload_e2e"

# Module-level mock_root: set by fixture, used by our local helpers.
_MOCK_ROOT: str = ""


# ---------------------------------------------------------------------------
# Local mock helpers (operate on _MOCK_ROOT, not the helpers.MOCK_ROOT constant)
# ---------------------------------------------------------------------------

def _mock_remote_path(remote_root: str) -> Path:
    stripped = remote_root.lstrip("/")
    return Path(_MOCK_ROOT) / stripped


def local_mock_upload(remote_root: str, middle_path: str, content: bytes) -> None:
    dest = _mock_remote_path(remote_root) / middle_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)


def local_mock_cleanup(remote_root: str) -> None:
    p = _mock_remote_path(remote_root)
    if p.exists():
        shutil.rmtree(p)


# ---------------------------------------------------------------------------
# Module-scope: use mock storage for all tests in this file
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def use_mock_storage_for_module(tmp_path_factory):
    """Switch to MockCloudStorage using a temp dir OUTSIDE backend/ to avoid
    triggering PM2 file-watcher restarts when mock cloud files are written.
    """
    global _MOCK_ROOT
    # Use a system temp directory — guaranteed to be outside backend/
    mock_root = str(tmp_path_factory.mktemp("fg_mock_cloud"))
    _MOCK_ROOT = mock_root

    orig = api("GET", "/file-git/settings")["settings"]
    api("PUT", "/file-git/settings", json={"use_mock_baidu": True, "mock_root": mock_root})
    yield mock_root
    api("PUT", "/file-git/settings", json={
        "use_mock_baidu": orig.get("use_mock_baidu", False),
        "mock_root": orig.get("mock_root", ""),
    })
    _MOCK_ROOT = ""


# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

class State:
    repo_id: str = ""
    local_root: str = ""


S = State()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_file(path: str, content: str = "") -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content or f"content of {p.name}\n", encoding="utf-8")


def read_pending(local_root: str) -> dict:
    path = Path(local_root) / ".fgit" / "pending_upload.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def pending_middle_paths(local_root: str) -> list[str]:
    data = read_pending(local_root)
    return sorted(e["middle_path"] for e in data.get("entries", []))


def abandon(repo_id: str) -> None:
    r = post(f"/file-git/repos/{repo_id}/abandon-manual-upload")
    assert r.get("success"), f"abandon failed: {r}"


def prepare(repo_id: str, subpath: str = "") -> dict:
    r = post(f"/file-git/repos/{repo_id}/manual-upload", {"subpath": subpath})
    return r


# ---------------------------------------------------------------------------
# T00 — setup: create repo + local files
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("backend_alive")
def test_t00_setup(tmp_path):
    """Create repo, populate local files, configure remote_path."""
    local_mock_cleanup(REMOTE_ROOT)

    local_root = str(tmp_path / "testrepo")
    S.local_root = local_root

    # Local file structure:
    #   3d/model1/file1.obj       ← batch 3d/model1 (under subpath=3d)
    #   3d/model1/file2.mtl
    #   3d/model2/file3.obj       ← batch 3d/model2 — will be pre-seeded on cloud
    #   3d/model3/file4.obj       ← batch 3d/model3
    #   photos/2024/photo1.jpg    ← batch photos/2024 — will be pre-seeded on cloud
    #   photos/2024/photo2.jpg
    #   photos/2025/photo3.jpg    ← batch photos/2025
    #   docs/readme.txt           ← batch docs
    #   notes.txt                 ← directly in root, excluded by design
    FILES = [
        "3d/model1/file1.obj",
        "3d/model1/file2.mtl",
        "3d/model2/file3.obj",
        "3d/model3/file4.obj",
        "photos/2024/photo1.jpg",
        "photos/2024/photo2.jpg",
        "photos/2025/photo3.jpg",
        "docs/readme.txt",
        "notes.txt",
    ]
    for f in FILES:
        make_file(os.path.join(local_root, f))

    resp = post("/file-git/repos", {"local_path": local_root, "mode": "ORIGINAL"})
    assert resp.get("success"), f"create repo failed: {resp}"
    S.repo_id = resp["repo"]["id"]

    r = put(f"/file-git/repos/{S.repo_id}/config", {"remote_path": REMOTE_ROOT})
    assert r.get("success"), f"set remote_path failed: {r}"


# ---------------------------------------------------------------------------
# T01 — subpath="" (root): all cloud empty → all batches included
# ---------------------------------------------------------------------------

def test_t01_root_clean_cloud():
    """With empty cloud, all first-level batches are queued."""
    assert S.repo_id, "T00 did not run"
    local_mock_cleanup(REMOTE_ROOT)

    r = prepare(S.repo_id, subpath="")
    assert r.get("success"), f"prepare failed: {r}"

    paths = pending_middle_paths(S.local_root)
    # notes.txt is excluded (no subfolder)
    assert "notes.txt" not in paths, f"notes.txt should be excluded, got: {paths}"
    # All subdir files present
    expected_batch_files = [
        "3d/model1/file1.obj", "3d/model1/file2.mtl",
        "3d/model2/file3.obj",
        "3d/model3/file4.obj",
        "photos/2024/photo1.jpg", "photos/2024/photo2.jpg",
        "photos/2025/photo3.jpg",
        "docs/readme.txt",
    ]
    for f in expected_batch_files:
        assert f in paths, f"Expected {f!r} in pending, got: {paths}"

    abandon(S.repo_id)


# ---------------------------------------------------------------------------
# T02 — subpath="" with partial cloud: batches with ANY file on cloud skipped
# ---------------------------------------------------------------------------

def test_t02_root_partial_cloud():
    """With some batches pre-seeded, those batches are skipped entirely."""
    assert S.repo_id, "T00 did not run"

    # Pre-seed cloud: one file from 3d/model2 and one file from photos/2024
    local_mock_upload(REMOTE_ROOT, "3d/model2/file3.obj", b"cloud-version")
    local_mock_upload(REMOTE_ROOT, "photos/2024/photo1.jpg", b"cloud-version")

    r = prepare(S.repo_id, subpath="")
    assert r.get("success"), f"prepare failed: {r}"

    paths = pending_middle_paths(S.local_root)

    # 3d batch: has file3.obj on cloud → entire 3d batch skipped
    assert "3d/model1/file1.obj" not in paths, f"3d should be skipped, got: {paths}"
    assert "3d/model2/file3.obj" not in paths
    assert "3d/model3/file4.obj" not in paths

    # photos batch: has photo1.jpg on cloud → entire photos batch skipped
    assert "photos/2024/photo1.jpg" not in paths
    assert "photos/2025/photo3.jpg" not in paths

    # docs batch: nothing on cloud → included
    assert "docs/readme.txt" in paths, f"docs should be included, got: {paths}"

    # notes.txt always excluded
    assert "notes.txt" not in paths

    abandon(S.repo_id)
    local_mock_cleanup(REMOTE_ROOT)


# ---------------------------------------------------------------------------
# T03 — subpath="/" treated as root (no ValueError)
# ---------------------------------------------------------------------------

def test_t03_slash_input_same_as_root():
    """Input '/' should behave identically to '' (root scan)."""
    assert S.repo_id, "T00 did not run"
    local_mock_cleanup(REMOTE_ROOT)

    r = prepare(S.repo_id, subpath="/")
    assert r.get("success"), f"prepare with '/' failed: {r}"

    paths = pending_middle_paths(S.local_root)
    # Same as T01: all files from batches, notes.txt excluded
    assert "notes.txt" not in paths
    assert "3d/model1/file1.obj" in paths
    assert "docs/readme.txt" in paths

    abandon(S.repo_id)


# ---------------------------------------------------------------------------
# T04 — subpath="3d": batches by model-level subdir
# ---------------------------------------------------------------------------

def test_t04_subpath_3d_clean_cloud():
    """With subpath=3d and clean cloud, all model batches are queued."""
    assert S.repo_id, "T00 did not run"
    local_mock_cleanup(REMOTE_ROOT)

    r = prepare(S.repo_id, subpath="3d")
    assert r.get("success"), f"prepare failed: {r}"

    paths = pending_middle_paths(S.local_root)
    # Only 3d files (photos/docs are outside the subpath)
    assert "3d/model1/file1.obj" in paths
    assert "3d/model1/file2.mtl" in paths
    assert "3d/model2/file3.obj" in paths
    assert "3d/model3/file4.obj" in paths
    assert "photos/2024/photo1.jpg" not in paths
    assert "docs/readme.txt" not in paths

    abandon(S.repo_id)


# ---------------------------------------------------------------------------
# T05 — subpath="3d" with model2 on cloud: model2 batch skipped
# ---------------------------------------------------------------------------

def test_t05_subpath_3d_partial_cloud():
    """With 3d/model2 pre-seeded, only model1 and model3 are queued."""
    assert S.repo_id, "T00 did not run"

    local_mock_upload(REMOTE_ROOT, "3d/model2/file3.obj", b"cloud-version")

    r = prepare(S.repo_id, subpath="3d")
    assert r.get("success"), f"prepare failed: {r}"

    paths = pending_middle_paths(S.local_root)

    # model1 and model3 batches have no cloud files → included
    assert "3d/model1/file1.obj" in paths
    assert "3d/model1/file2.mtl" in paths
    assert "3d/model3/file4.obj" in paths

    # model2 has a cloud file → skipped
    assert "3d/model2/file3.obj" not in paths

    # nothing from outside subpath
    assert "photos/2024/photo1.jpg" not in paths

    abandon(S.repo_id)
    local_mock_cleanup(REMOTE_ROOT)


# ---------------------------------------------------------------------------
# T06 — subpath="photos": batches by year
# ---------------------------------------------------------------------------

def test_t06_subpath_photos_partial_cloud():
    """With photos/2024 on cloud, only photos/2025 is queued."""
    assert S.repo_id, "T00 did not run"

    local_mock_upload(REMOTE_ROOT, "photos/2024/photo1.jpg", b"cloud-version")

    r = prepare(S.repo_id, subpath="photos")
    assert r.get("success"), f"prepare failed: {r}"

    paths = pending_middle_paths(S.local_root)

    # 2024 has a cloud file → skipped
    assert "photos/2024/photo1.jpg" not in paths
    assert "photos/2024/photo2.jpg" not in paths

    # 2025 has no cloud file → included
    assert "photos/2025/photo3.jpg" in paths

    # nothing from outside subpath
    assert "3d/model1/file1.obj" not in paths

    abandon(S.repo_id)
    local_mock_cleanup(REMOTE_ROOT)


# ---------------------------------------------------------------------------
# T07 — cleanup: delete the test repo
# ---------------------------------------------------------------------------

def test_t07_cleanup():
    """Remove the test repo from the registry."""
    if not S.repo_id:
        return
    r = delete(f"/file-git/repos/{S.repo_id}")
    assert r.get("success"), f"delete repo failed: {r}"
    if S.local_root and Path(S.local_root).exists():
        shutil.rmtree(S.local_root, ignore_errors=True)
