"""
Suite A (Real) — same T01–T10 logic as test_plain.py but against real BaiduCloudStorage.

This suite calls the actual Baidu Pan API. It requires:
  - A running backend with valid Baidu credentials in settings.json
  - TEST_REMOTE_ROOT set to a path under the app's root_prefix that exists on Baidu Pan
    (e.g. /apps/sync-assistant/fgit_e2e_real). The suite creates and deletes files there.

IMPORTANT: Tests are sequentially dependent — if T04 fails, stop immediately.
           Use -x (already in pytest.ini addopts) to halt at first failure.

Run:
    TEST_REMOTE_ROOT=/apps/sync-assistant/fgit_e2e_real \\
    pytest backend/tests/e2e/test_plain_real.py -v

Step-by-step mode (pauses after each test for manual inspection):
    STEP_PAUSE=1 TEST_REMOTE_ROOT=... pytest backend/tests/e2e/test_plain_real.py -v -s

Do NOT run this in CI without a dedicated test path on Baidu Pan.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import requests

from helpers import (
    api, post, put, delete,
    read_local_index, read_cloud_index, read_queue,
    read_success_log, read_error_log, file_log_actions,
    local_trash_files, local_trash_count,
    BASE_URL,
)

# Real Baidu API calls can be slow — use a longer timeout throughout.
TIMEOUT = 300


def rpost(path: str, body: dict | None = None) -> dict:
    return post(path, body, timeout=TIMEOUT)


def rput(path: str, body: dict) -> dict:
    return put(path, body, timeout=TIMEOUT)


def pause(step: str) -> None:
    """Wait for Enter before continuing to the next test step.

    Only active when STEP_PAUSE=1 is set in the environment.
    This lets you inspect local files and Baidu Pan state between steps.
    """
    if not os.environ.get("STEP_PAUSE"):
        return
    local_a = S.local_a or "(not set yet)"
    remote = S.remote_root or "(not set yet)"
    print(f"\n{'─' * 60}")
    print(f"  {step} done")
    print(f"  local_a : {local_a}")
    print(f"  remote  : {remote}")
    print(f"{'─' * 60}")
    input("  Press Enter to continue to the next step... ")

# ---------------------------------------------------------------------------
# Real-storage remote helpers (replace mock_* functions)
# ---------------------------------------------------------------------------

def real_upload(remote_root: str, middle_path: str, content: bytes) -> None:
    """Upload content to the real cloud via the backend's manual-upload flow.

    For simplicity we use the backend's own upload endpoint with a temp repo
    pointing at remote_root. The test suite does NOT call this for its own
    repos — it only uses it to pre-populate remote state for pull/rebuild tests
    (T06). For those cases we just write a temp local file and push via the API.
    """
    raise NotImplementedError(
        "real_upload is not used directly — pre-populate remote state via push."
    )


def real_exists(remote_root: str, relative_path: str) -> bool:
    """Check if a path exists on the real cloud by querying cloud_index."""
    raise NotImplementedError(
        "Use cloud_index checks instead of real_exists for real storage."
    )


def real_cleanup_remote(remote_root: str) -> None:
    """Delete the remote_root folder on Baidu Pan (including all contents)."""
    from file_git.settings_manager import SettingsManager
    from file_git.cloud.baidu import BaiduCloudStorage

    token_provider = lambda: SettingsManager.get_baidu_credentials()["access_token"]
    root_prefix = SettingsManager.get_baidu_root_prefix()
    storage = BaiduCloudStorage(token_provider, root_prefix=root_prefix)
    storage.delete(remote_root)


# ---------------------------------------------------------------------------
# Module-level shared state
# ---------------------------------------------------------------------------

class State:
    id_a: str = ""
    local_a: str = ""
    id_b: str = ""
    local_b: str = ""
    remote_root: str = ""
    id_prep: str = ""     # scratch repo used to pre-populate remote in T06


S = State()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_file(path: str, content: str = "") -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content or f"content of {p.name}\n", encoding="utf-8")


def create_repo(local_path: str, remote_root: str) -> str:
    resp = rpost("/file-git/repos", {"local_path": local_path, "mode": "ORIGINAL"})
    assert resp["success"], f"create repo failed: {resp}"
    repo_id = resp["repo"]["id"]
    r = rput(f"/file-git/repos/{repo_id}/config", {"remote_path": remote_root})
    assert r["success"], f"set config failed: {r}"
    return repo_id


def assert_no_errors(repo_root_dir: str, action_folder: str) -> None:
    errors = read_error_log(repo_root_dir, action_folder)
    assert errors == [], f"Unexpected errors in error.log:\n" + "\n".join(errors)


def assert_queue_empty(repo_root_dir: str) -> None:
    q = read_queue(repo_root_dir)
    assert not q.get("lock"), f"Queue lock not released: {q}"
    assert q.get("items", []) == [], f"Queue items not empty: {q}"


def assert_success_log_contains(repo_root_dir: str, action_folder: str, keyword: str) -> None:
    lines = read_success_log(repo_root_dir, action_folder)
    assert any(keyword in line for line in lines), (
        f"Expected '{keyword}' in success.log, got:\n" + "\n".join(lines)
    )


# ---------------------------------------------------------------------------
# T01 — Initial manual upload (full)
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("backend_alive")
def test_t01_manual_upload_full(remote_root_plain, tmp_path):
    S.remote_root = remote_root_plain

    local_a = str(tmp_path / "local_a")
    S.local_a = local_a
    FILES_8 = [
        "root1.txt", "root2.txt",
        "l11/l11_1.txt", "l11/l11_2.txt",
        "l12/l12_1.txt", "l12/l12_2.txt",
        "l12/l21/l21_1.txt", "l12/l21/l21_2.txt",
    ]
    for rel in FILES_8:
        make_file(os.path.join(local_a, rel))

    S.id_a = create_repo(local_a, S.remote_root)

    # Step 1: push uploads all files and builds indexes in one shot
    resp = rpost(f"/file-git/repos/{S.id_a}/push")
    assert resp["success"], f"push failed: {resp}"
    action_folder = resp["action_folder"]

    # --- Assert file positions ---
    for rel in FILES_8:
        assert Path(local_a, rel).exists(), f"Local file missing: {rel}"

    # --- Assert indexes ---
    li = read_local_index(local_a)
    ci = read_cloud_index(local_a)
    assert len(li) == 8, f"local_index: expected 8, got {len(li)}"
    assert len(ci) == 8, f"cloud_index: expected 8, got {len(ci)}"
    assert {v["middle_path"] for v in li.values()} == {v["middle_path"] for v in ci.values()}
    for v in li.values():
        assert v["size"] == Path(local_a, v["middle_path"]).stat().st_size

    assert_no_errors(local_a, action_folder)
    assert resp["uploaded"] == 8, f"Expected uploaded=8, got {resp['uploaded']}"
    pause("T01 — initial push (8 files uploaded)")


# ---------------------------------------------------------------------------
# T02 — Push new subpath (incremental)
# ---------------------------------------------------------------------------

def test_t02_push_subpath():
    local_a = S.local_a

    for rel in ["l12/l22/l22_1.txt", "l12/l22/l22_2.txt"]:
        make_file(os.path.join(local_a, rel))

    resp = rpost(f"/file-git/repos/{S.id_a}/push")
    assert resp["success"], f"push failed: {resp}"
    action_folder = resp["action_folder"]

    li = read_local_index(local_a)
    ci = read_cloud_index(local_a)
    assert len(li) == 10, f"local_index: expected 10, got {len(li)}"
    assert len(ci) == 10, f"cloud_index: expected 10, got {len(ci)}"
    assert {v["middle_path"] for v in li.values()} == {v["middle_path"] for v in ci.values()}
    assert_queue_empty(local_a)
    assert resp["uploaded"] == 2
    assert_no_errors(local_a, action_folder)
    pause("T02 — incremental push (2 new files)")


# ---------------------------------------------------------------------------
# T03 — Pull into a fresh repo (partial: l12 subtree only)
# ---------------------------------------------------------------------------

def test_t03_pull_subpath(tmp_path):
    local_b = str(tmp_path / "local_b")
    S.local_b = local_b
    Path(local_b).mkdir(parents=True)

    S.id_b = create_repo(local_b, S.remote_root)

    # Pull everything — real storage has no subpath pull, so pull all then check
    resp = rpost(f"/file-git/repos/{S.id_b}/pull")
    assert resp["success"], f"pull failed: {resp}"
    action_folder = resp["action_folder"]

    ALL_10 = [
        "root1.txt", "root2.txt",
        "l11/l11_1.txt", "l11/l11_2.txt",
        "l12/l12_1.txt", "l12/l12_2.txt",
        "l12/l21/l21_1.txt", "l12/l21/l21_2.txt",
        "l12/l22/l22_1.txt", "l12/l22/l22_2.txt",
    ]
    for rel in ALL_10:
        assert Path(local_b, rel).exists(), f"Missing after pull: {rel}"

    li = read_local_index(local_b)
    ci = read_cloud_index(local_b)
    assert len(li) == 10, f"local_index: expected 10, got {len(li)}"
    assert len(ci) == 10
    assert {v["middle_path"] for v in li.values()} == {v["middle_path"] for v in ci.values()}

    assert resp["downloaded"] == 10
    assert_no_errors(local_b, action_folder)
    assert resp.get("unmapped", []) == []
    pause("T03 — pull into fresh repo local_b (10 files downloaded)")


# ---------------------------------------------------------------------------
# T04 — Pull is idempotent (nothing to download)
# ---------------------------------------------------------------------------

def test_t04_pull_idempotent():
    local_b = S.local_b

    resp = rpost(f"/file-git/repos/{S.id_b}/pull")
    assert resp["success"], f"pull failed: {resp}"
    action_folder = resp["action_folder"]

    li = read_local_index(local_b)
    ci = read_cloud_index(local_b)
    assert len(li) == 10
    assert len(ci) == 10

    assert resp["downloaded"] == 0
    assert_no_errors(local_b, action_folder)
    pause("T04 — pull idempotent (0 downloaded)")


# ---------------------------------------------------------------------------
# T05 — Push new files
# ---------------------------------------------------------------------------

def test_t05_push_new_files():
    local_a = S.local_a

    for rel in ["root3.txt", "l12/l23/l23_1.txt", "l12/l23/l23_2.txt"]:
        make_file(os.path.join(local_a, rel))

    resp = rpost(f"/file-git/repos/{S.id_a}/push")
    assert resp["success"], f"push failed: {resp}"
    action_folder = resp["action_folder"]

    li = read_local_index(local_a)
    ci = read_cloud_index(local_a)
    assert len(li) == 13, f"local_index: expected 13, got {len(li)}"
    assert len(ci) == 13
    assert {v["middle_path"] for v in li.values()} == {v["middle_path"] for v in ci.values()}
    assert_queue_empty(local_a)

    assert resp["uploaded"] == 3
    assert_no_errors(local_a, action_folder)
    assert "REMOTE_TRASH" not in file_log_actions(local_a, action_folder)
    pause("T05 — push 3 new files (local_a now 13 files)")


# ---------------------------------------------------------------------------
# T06 — Pull new files from remote (uploaded by another machine)
# ---------------------------------------------------------------------------

def test_t06_pull_new_files(tmp_path):
    local_a = S.local_a

    # Simulate another machine: create a scratch repo, push 3 new files
    local_prep = str(tmp_path / "local_prep")
    Path(local_prep).mkdir()
    for rel in ["root4.txt", "l12/l24/l24_1.txt", "l12/l24/l24_2.txt"]:
        make_file(os.path.join(local_prep, rel), content=f"remote content of {rel}\n")

    S.id_prep = create_repo(local_prep, S.remote_root)
    # upload_only=True: add 3 files without trashing the 13 already on remote
    r = rpost(f"/file-git/repos/{S.id_prep}/push", {"upload_only": True})
    assert r["success"], f"prep push failed: {r}"
    assert r["uploaded"] == 3

    # Now pull into id_a
    resp = rpost(f"/file-git/repos/{S.id_a}/rebuild-cloud-index")
    assert resp["success"], f"rebuild-cloud-index failed: {resp}"

    resp = rpost(f"/file-git/repos/{S.id_a}/pull")
    assert resp["success"], f"pull failed: {resp}"
    action_folder = resp["action_folder"]

    for rel in ["root4.txt", "l12/l24/l24_1.txt", "l12/l24/l24_2.txt"]:
        assert Path(local_a, rel).exists(), f"Not downloaded: {rel}"
    for rel in ["root1.txt", "l11/l11_1.txt", "l12/l23/l23_1.txt"]:
        assert Path(local_a, rel).exists(), f"Existing file gone: {rel}"

    li = read_local_index(local_a)
    ci = read_cloud_index(local_a)
    assert len(li) == 16, f"local_index: expected 16, got {len(li)}"
    assert len(ci) == 16
    assert {v["middle_path"] for v in li.values()} == {v["middle_path"] for v in ci.values()}
    assert_queue_empty(local_a)

    assert resp["downloaded"] == 3
    assert_no_errors(local_a, action_folder)
    assert "LOCAL_DELETE" not in file_log_actions(local_a, action_folder)
    pause("T06 — pull 3 new files from remote (local_a now 16 files)")


# ---------------------------------------------------------------------------
# T07 — Sync filter: synced → remote-only (local files to trash)
# ---------------------------------------------------------------------------

def test_t07_syncfilter_synced_to_remote_only():
    local_a = S.local_a
    trash_before = local_trash_count(local_a)

    for path in ["l12/l23", "l12/l24"]:
        r = rput(f"/file-git/repos/{S.id_a}/sync-filter", {"path": path, "mode": "remote-only"})
        assert r["success"], f"set sync filter failed: {r}"

    resp = rpost(f"/file-git/repos/{S.id_a}/sync-filter/apply")
    assert resp["success"], f"apply failed: {resp}"
    action_folder = resp["action_folder"]
    counters = resp["counters"]

    for rel in ["l12/l23/l23_1.txt", "l12/l23/l23_2.txt",
                "l12/l24/l24_1.txt", "l12/l24/l24_2.txt"]:
        assert not Path(local_a, rel).exists(), f"Should be gone from local: {rel}"
    assert local_trash_count(local_a) == trash_before + 4, "Expected 4 new local trash files"
    trash = local_trash_files(local_a)
    for name in ["l23_1.txt", "l23_2.txt", "l24_1.txt", "l24_2.txt"]:
        assert any(name in t for t in trash), f"Trash missing {name}: {trash}"

    li = read_local_index(local_a)
    ci = read_cloud_index(local_a)
    assert len(li) == 12, f"local_index: expected 12, got {len(li)}"
    assert len(ci) == 16, f"cloud_index: expected 16, got {len(ci)}"

    assert counters["local_deleted"] == 4, f"Expected local_deleted=4: {counters}"
    assert counters["remote_deleted"] == 0
    assert_no_errors(local_a, action_folder)
    actions = file_log_actions(local_a, action_folder)
    assert [a for a in actions if a == "LOCAL_DELETE"] >= ["LOCAL_DELETE"] * 4
    assert "REMOTE_TRASH" not in actions
    pause("T07 — l12/l23 + l12/l24 → remote-only (4 files trashed locally)")


# ---------------------------------------------------------------------------
# T08 — Sync filter: remote-only → synced (download from cloud)
# ---------------------------------------------------------------------------

def test_t08_syncfilter_remote_only_to_synced():
    local_a = S.local_a
    trash_before = local_trash_count(local_a)

    for path in ["l12/l23", "l12/l24"]:
        r = rput(f"/file-git/repos/{S.id_a}/sync-filter", {"path": path, "mode": "synced"})
        assert r["success"], f"set sync filter failed: {r}"

    resp = rpost(f"/file-git/repos/{S.id_a}/sync-filter/apply")
    assert resp["success"], f"apply failed: {resp}"
    action_folder = resp["action_folder"]
    counters = resp["counters"]

    for rel in ["l12/l23/l23_1.txt", "l12/l23/l23_2.txt",
                "l12/l24/l24_1.txt", "l12/l24/l24_2.txt"]:
        assert Path(local_a, rel).exists(), f"File should be restored: {rel}"
    assert local_trash_count(local_a) == trash_before

    li = read_local_index(local_a)
    ci = read_cloud_index(local_a)
    assert len(li) == 16
    assert len(ci) == 16

    assert counters["downloaded"] == 4
    assert counters["local_deleted"] == 0
    assert counters["remote_deleted"] == 0
    assert_no_errors(local_a, action_folder)
    actions = file_log_actions(local_a, action_folder)
    assert actions.count("DOWNLOAD") >= 4
    assert "LOCAL_DELETE" not in actions
    assert "REMOTE_TRASH" not in actions
    pause("T08 — l12/l23 + l12/l24 → synced again (4 files downloaded back)")


# ---------------------------------------------------------------------------
# T09 — Sync filter: local-only (no remote copy; pull leaves it alone)
# ---------------------------------------------------------------------------

def test_t09_syncfilter_local_only_no_remote():
    local_a = S.local_a
    trash_before = local_trash_count(local_a)

    for rel in ["l12/l25/l25_1.txt", "l12/l25/l25_2.txt"]:
        make_file(os.path.join(local_a, rel))

    r = rput(f"/file-git/repos/{S.id_a}/sync-filter", {"path": "l12/l25", "mode": "local-only"})
    assert r["success"], f"set sync filter failed: {r}"

    resp = rpost(f"/file-git/repos/{S.id_a}/sync-filter/apply")
    assert resp["success"], f"apply failed: {resp}"
    apply_af = resp["action_folder"]
    apply_c = resp["counters"]

    resp_pull = rpost(f"/file-git/repos/{S.id_a}/pull")
    assert resp_pull["success"], f"pull failed: {resp_pull}"

    for rel in ["l12/l25/l25_1.txt", "l12/l25/l25_2.txt"]:
        assert Path(local_a, rel).exists(), f"local-only file must survive: {rel}"
    assert local_trash_count(local_a) == trash_before

    li = read_local_index(local_a)
    ci = read_cloud_index(local_a)
    assert len(li) == 18, f"local_index: expected 18, got {len(li)}"
    assert len(ci) == 16
    ci_paths = {v["middle_path"] for v in ci.values()}
    assert "l12/l25/l25_1.txt" not in ci_paths

    assert apply_c["uploaded"] == 0
    assert apply_c["downloaded"] == 0
    assert apply_c["local_deleted"] == 0
    assert apply_c["remote_deleted"] == 0
    assert resp_pull["downloaded"] == 0
    assert_no_errors(local_a, resp_pull["action_folder"])
    pause("T09 — l12/l25 → local-only (not uploaded, pull ignores it)")


# ---------------------------------------------------------------------------
# T10 — Sync filter: synced (both sides) → local-only (remote soft-delete)
# ---------------------------------------------------------------------------

def test_t10_syncfilter_synced_to_local_only():
    local_a = S.local_a
    trash_before = local_trash_count(local_a)

    r = rput(f"/file-git/repos/{S.id_a}/sync-filter", {"path": "l11", "mode": "local-only"})
    assert r["success"], f"set sync filter failed: {r}"

    resp = rpost(f"/file-git/repos/{S.id_a}/sync-filter/apply")
    assert resp["success"], f"apply failed: {resp}"
    action_folder = resp["action_folder"]
    counters = resp["counters"]

    assert Path(local_a, "l11/l11_1.txt").exists()
    assert Path(local_a, "l11/l11_2.txt").exists()
    assert local_trash_count(local_a) == trash_before

    li = read_local_index(local_a)
    ci = read_cloud_index(local_a)
    assert len(li) == 18, f"local_index: expected 18, got {len(li)}"
    assert len(ci) == 14, f"cloud_index: expected 14 (16-2), got {len(ci)}"
    ci_paths = {v["middle_path"] for v in ci.values()}
    assert "l11/l11_1.txt" not in ci_paths
    assert "l11/l11_2.txt" not in ci_paths

    assert counters["remote_deleted"] == 2
    assert counters["local_deleted"] == 0
    assert_no_errors(local_a, action_folder)
    actions = file_log_actions(local_a, action_folder)
    assert actions.count("REMOTE_TRASH") >= 2
    assert "LOCAL_DELETE" not in actions
    assert "UPLOAD" not in actions
    assert "DOWNLOAD" not in actions
    pause("T10 — l11 → local-only (2 files REMOTE_TRASH'd, cloud_index=14)")


# ---------------------------------------------------------------------------
# Fixtures: storage mode + teardown
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def _activate_real_storage(use_real_storage):
    """Opt this module into real BaiduCloudStorage."""


@pytest.fixture(scope="module", autouse=True)
def cleanup_after_suite():
    yield
    for repo_id in [S.id_a, S.id_b, S.id_prep]:
        if repo_id:
            try:
                delete(f"/file-git/repos/{repo_id}")
            except Exception:
                pass
    if S.remote_root:
        try:
            real_cleanup_remote(S.remote_root)
        except Exception:
            pass
