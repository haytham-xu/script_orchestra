"""
Suite A — Original mode (ORIGINAL = plain-text, no encryption) E2E tests.

All tests run serially and share state via the module-level State object.
Each test picks up where the previous one left off.

IMPORTANT: Tests are sequentially dependent. If T04 fails, T05 onwards are
meaningless because they assume T04's filesystem state. Run the full suite
together; do not cherry-pick individual tests. A failure in test N is the
only one worth diagnosing — subsequent failures are cascading noise.

Run:
    TEST_REMOTE_ROOT=/test_plain \
    pytest backend/file_git/tests/e2e/test_plain.py -v -x
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from helpers import (
    api, post, put, delete,
    mock_upload, mock_download, mock_exists, mock_cleanup_remote,
    read_local_index, read_cloud_index, read_queue,
    read_success_log, read_error_log, file_log_actions,
    local_trash_files, local_trash_count, remote_trash_files,
)

# ---------------------------------------------------------------------------
# Module-level shared state
# ---------------------------------------------------------------------------

class State:
    id_a: str = ""
    local_a: str = ""
    id_b: str = ""
    local_b: str = ""
    remote_root: str = ""


S = State()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_file(path: str, content: str = "") -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content or f"content of {p.name}\n", encoding="utf-8")


def create_repo(local_path: str, remote_root: str) -> str:
    """Create a repo and configure its remote_path. Returns repo_id."""
    resp = post("/file-git/repos", {"local_path": local_path, "mode": "ORIGINAL"})
    assert resp["success"], f"create repo failed: {resp}"
    repo_id = resp["repo"]["id"]
    # remote_path lives in .fgit/config.json, set via PUT /config
    r = put(f"/file-git/repos/{repo_id}/config", {"remote_path": remote_root})
    assert r["success"], f"set config failed: {r}"
    return repo_id


def assert_no_errors(repo_root_dir: str, action_folder: str) -> None:
    errors = read_error_log(repo_root_dir, action_folder)
    assert errors == [], f"Unexpected errors in error.log:\n" + "\n".join(errors)


def assert_success_log_contains(repo_root_dir: str, action_folder: str, keyword: str) -> None:
    lines = read_success_log(repo_root_dir, action_folder)
    assert any(keyword in line for line in lines), (
        f"Expected '{keyword}' in success.log, got:\n" + "\n".join(lines)
    )


def assert_queue_empty(repo_root_dir: str) -> None:
    q = read_queue(repo_root_dir)
    assert not q.get("lock"), f"Queue lock not released: {q}"
    assert q.get("items", []) == [], f"Queue items not empty: {q}"


# ---------------------------------------------------------------------------
# T01 — Initial manual upload (full)
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("backend_alive")
def test_t01_manual_upload_full(remote_root_plain, tmp_path):
    S.remote_root = remote_root_plain
    mock_cleanup_remote(S.remote_root)

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

    # Prepare
    resp = post(f"/file-git/repos/{S.id_a}/manual-upload")
    assert resp["success"], f"manual-upload pre failed: {resp}"
    action_folder = resp["action_folder"]

    # Upload 8 files to mock remote
    for rel in FILES_8:
        mock_upload(S.remote_root, rel, Path(local_a, rel).read_bytes())

    # Confirm
    resp = post(f"/file-git/repos/{S.id_a}/post-manual-upload")
    assert resp["success"], f"post-manual-upload failed: {resp}"

    # --- Assert file positions ---
    for rel in FILES_8:
        assert Path(local_a, rel).exists(), f"Local file missing: {rel}"
        assert mock_exists(S.remote_root, rel), f"Remote file missing: {rel}"
    assert mock_exists(S.remote_root, ".fgit/cloud_index.json"), "Remote cloud_index.json missing"

    # --- Assert indexes ---
    li = read_local_index(local_a)
    ci = read_cloud_index(local_a)
    assert len(li) == 8, f"local_index: expected 8, got {len(li)}"
    assert len(ci) == 8, f"cloud_index: expected 8, got {len(ci)}"
    li_paths = {v["middle_path"] for v in li.values()}
    ci_paths = {v["middle_path"] for v in ci.values()}
    assert li_paths == ci_paths
    for v in li.values():
        assert v["size"] == Path(local_a, v["middle_path"]).stat().st_size

    # --- Assert action log ---
    assert_success_log_contains(local_a, action_folder, "MANUAL_UPLOAD_CONFIRM")
    assert_no_errors(local_a, action_folder)


# ---------------------------------------------------------------------------
# T02 — Manual upload subpath (incremental)
# ---------------------------------------------------------------------------

def test_t02_manual_upload_subpath():
    local_a = S.local_a

    for rel in ["l12/l22/l22_1.txt", "l12/l22/l22_2.txt"]:
        make_file(os.path.join(local_a, rel))

    resp = post(f"/file-git/repos/{S.id_a}/manual-upload", {"subpath": "l12/l22"})
    assert resp["success"], f"manual-upload pre failed: {resp}"
    action_folder = resp["action_folder"]

    for rel in ["l12/l22/l22_1.txt", "l12/l22/l22_2.txt"]:
        mock_upload(S.remote_root, rel, Path(local_a, rel).read_bytes())

    resp = post(f"/file-git/repos/{S.id_a}/post-manual-upload")
    assert resp["success"], f"post-manual-upload failed: {resp}"

    # --- Assert file positions ---
    for rel in ["l12/l22/l22_1.txt", "l12/l22/l22_2.txt"]:
        assert Path(local_a, rel).exists()
        assert mock_exists(S.remote_root, rel)

    # --- Assert indexes ---
    li = read_local_index(local_a)
    ci = read_cloud_index(local_a)
    assert len(li) == 10, f"local_index: expected 10, got {len(li)}"
    assert len(ci) == 10, f"cloud_index: expected 10, got {len(ci)}"
    for rel in ["l12/l22/l22_1.txt", "l12/l22/l22_2.txt"]:
        assert any(v["middle_path"] == rel for v in ci.values()), f"cloud_index missing {rel}"
    assert_queue_empty(local_a)

    # --- Assert action log ---
    assert_success_log_contains(local_a, action_folder, "MANUAL_UPLOAD_CONFIRM")
    assert_no_errors(local_a, action_folder)


# ---------------------------------------------------------------------------
# T03 — Manual download subpath (partial)
# ---------------------------------------------------------------------------

def test_t03_manual_download_subpath(tmp_path):
    local_b = str(tmp_path / "local_b")
    S.local_b = local_b
    Path(local_b).mkdir(parents=True)

    S.id_b = create_repo(local_b, S.remote_root)

    resp = post(f"/file-git/repos/{S.id_b}/pre-manual-download")
    assert resp["success"], f"pre-manual-download failed: {resp}"
    action_folder = resp["action_folder"]

    L12_FILES = [
        "l12/l12_1.txt", "l12/l12_2.txt",
        "l12/l21/l21_1.txt", "l12/l21/l21_2.txt",
        "l12/l22/l22_1.txt", "l12/l22/l22_2.txt",
    ]
    for rel in L12_FILES:
        dest = Path(local_b, rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(mock_download(S.remote_root, rel))

    resp = post(f"/file-git/repos/{S.id_b}/post-manual-download")
    assert resp["success"], f"post-manual-download failed: {resp}"

    # --- Assert file positions ---
    for rel in L12_FILES:
        assert Path(local_b, rel).exists(), f"Expected {rel} in local_b"
    for rel in ["root1.txt", "root2.txt"]:
        assert not Path(local_b, rel).exists(), f"Unexpected {rel} in local_b"
    assert not Path(local_b, "l11").exists()
    buf = Path(local_b, ".fgit", "buffer")
    assert not any(True for _ in buf.rglob("*") if buf.exists()), "buffer/ not empty"

    # --- Assert indexes ---
    li = read_local_index(local_b)
    ci = read_cloud_index(local_b)
    assert len(li) == 6, f"local_index: expected 6, got {len(li)}"
    assert len(ci) == 10, f"cloud_index: expected 10, got {len(ci)}"
    li_paths = {v["middle_path"] for v in li.values()}
    for rel in L12_FILES:
        assert rel in li_paths, f"local_index missing {rel}"
    for v in li.values():
        assert v["size"] == Path(local_b, v["middle_path"]).stat().st_size

    # --- Assert action log ---
    assert_success_log_contains(local_b, action_folder, "MANUAL_DOWNLOAD_CONFIRM")
    assert_no_errors(local_b, action_folder)
    assert resp.get("unmapped", []) == [], f"Unexpected unmapped: {resp.get('unmapped')}"


# ---------------------------------------------------------------------------
# T04 — Manual download remaining files
# ---------------------------------------------------------------------------

def test_t04_manual_download_remaining():
    local_b = S.local_b

    resp = post(f"/file-git/repos/{S.id_b}/pre-manual-download")
    assert resp["success"], f"pre-manual-download failed: {resp}"
    action_folder = resp["action_folder"]

    REMAINING = ["root1.txt", "root2.txt", "l11/l11_1.txt", "l11/l11_2.txt"]
    for rel in REMAINING:
        dest = Path(local_b, rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(mock_download(S.remote_root, rel))

    resp = post(f"/file-git/repos/{S.id_b}/post-manual-download")
    assert resp["success"], f"post-manual-download failed: {resp}"

    ALL_10 = [
        "root1.txt", "root2.txt",
        "l11/l11_1.txt", "l11/l11_2.txt",
        "l12/l12_1.txt", "l12/l12_2.txt",
        "l12/l21/l21_1.txt", "l12/l21/l21_2.txt",
        "l12/l22/l22_1.txt", "l12/l22/l22_2.txt",
    ]
    for rel in ALL_10:
        assert Path(local_b, rel).exists(), f"Missing: {rel}"

    li = read_local_index(local_b)
    ci = read_cloud_index(local_b)
    assert len(li) == 10, f"local_index: expected 10, got {len(li)}"
    assert len(ci) == 10
    assert {v["middle_path"] for v in li.values()} == {v["middle_path"] for v in ci.values()}

    assert_success_log_contains(local_b, action_folder, "MANUAL_DOWNLOAD_CONFIRM")
    assert_no_errors(local_b, action_folder)
    assert resp.get("unmapped", []) == []


# ---------------------------------------------------------------------------
# T05 — Push (new files)
# ---------------------------------------------------------------------------

def test_t05_push_new_files():
    local_a = S.local_a

    for rel in ["root3.txt", "l12/l23/l23_1.txt", "l12/l23/l23_2.txt"]:
        make_file(os.path.join(local_a, rel))

    resp = post(f"/file-git/repos/{S.id_a}/push")
    assert resp["success"], f"push failed: {resp}"
    action_folder = resp["action_folder"]

    # --- Assert file positions ---
    for rel in ["root3.txt", "l12/l23/l23_1.txt", "l12/l23/l23_2.txt"]:
        assert mock_exists(S.remote_root, rel), f"Remote missing: {rel}"
        assert Path(local_a, rel).exists(), f"Local file missing: {rel}"

    # --- Assert indexes ---
    li = read_local_index(local_a)
    ci = read_cloud_index(local_a)
    assert len(li) == 13, f"local_index: expected 13, got {len(li)}"
    assert len(ci) == 13
    assert {v["middle_path"] for v in li.values()} == {v["middle_path"] for v in ci.values()}
    assert_queue_empty(local_a)

    # --- Assert action log ---
    assert resp["uploaded"] == 3, f"Expected uploaded=3, got {resp['uploaded']}"
    assert_no_errors(local_a, action_folder)
    assert "REMOTE_TRASH" not in file_log_actions(local_a, action_folder)


# ---------------------------------------------------------------------------
# T06 — Pull (new files from remote)
# ---------------------------------------------------------------------------

def test_t06_pull_new_files():
    local_a = S.local_a

    for rel in ["root4.txt", "l12/l24/l24_1.txt", "l12/l24/l24_2.txt"]:
        mock_upload(S.remote_root, rel, f"remote content of {rel}\n".encode())

    resp = post(f"/file-git/repos/{S.id_a}/rebuild-cloud-index")
    assert resp["success"], f"rebuild-cloud-index failed: {resp}"

    resp = post(f"/file-git/repos/{S.id_a}/pull")
    assert resp["success"], f"pull failed: {resp}"
    action_folder = resp["action_folder"]

    # --- Assert file positions ---
    for rel in ["root4.txt", "l12/l24/l24_1.txt", "l12/l24/l24_2.txt"]:
        assert Path(local_a, rel).exists(), f"Not downloaded: {rel}"
        assert Path(local_a, rel).read_bytes() == mock_download(S.remote_root, rel)
    for rel in ["root1.txt", "l11/l11_1.txt", "l12/l23/l23_1.txt"]:
        assert Path(local_a, rel).exists(), f"Existing file gone: {rel}"

    # --- Assert indexes ---
    li = read_local_index(local_a)
    ci = read_cloud_index(local_a)
    assert len(li) == 16, f"local_index: expected 16, got {len(li)}"
    assert len(ci) == 16
    assert {v["middle_path"] for v in li.values()} == {v["middle_path"] for v in ci.values()}
    assert_queue_empty(local_a)

    # --- Assert action log ---
    assert resp["downloaded"] == 3, f"Expected downloaded=3, got {resp['downloaded']}"
    assert_no_errors(local_a, action_folder)
    assert "LOCAL_DELETE" not in file_log_actions(local_a, action_folder)


# ---------------------------------------------------------------------------
# T07 — Sync filter: synced → remote-only (local files to trash)
# ---------------------------------------------------------------------------

def test_t07_syncfilter_synced_to_remote_only():
    local_a = S.local_a
    trash_before = local_trash_count(local_a)

    for path in ["l12/l23", "l12/l24"]:
        r = put(f"/file-git/repos/{S.id_a}/sync-filter", {"path": path, "mode": "remote-only"})
        assert r["success"], f"set sync filter failed: {r}"

    resp = post(f"/file-git/repos/{S.id_a}/sync-filter/apply")
    assert resp["success"], f"apply failed: {resp}"
    action_folder = resp["action_folder"]
    counters = resp["counters"]

    # --- Assert file positions ---
    for rel in ["l12/l23/l23_1.txt", "l12/l23/l23_2.txt",
                "l12/l24/l24_1.txt", "l12/l24/l24_2.txt"]:
        assert not Path(local_a, rel).exists(), f"Should be gone from local: {rel}"
    assert local_trash_count(local_a) == trash_before + 4, "Expected 4 new local trash files"
    trash = local_trash_files(local_a)
    for name in ["l23_1.txt", "l23_2.txt", "l24_1.txt", "l24_2.txt"]:
        assert any(name in t for t in trash), f"Trash missing {name}: {trash}"
    for rel in ["l12/l23/l23_1.txt", "l12/l23/l23_2.txt",
                "l12/l24/l24_1.txt", "l12/l24/l24_2.txt"]:
        assert mock_exists(S.remote_root, rel), f"Remote file should still exist: {rel}"
    assert remote_trash_files(S.remote_root) == [], "Remote trash should be empty"

    # --- Assert indexes ---
    li = read_local_index(local_a)
    ci = read_cloud_index(local_a)
    assert len(li) == 12, f"local_index: expected 12, got {len(li)}"
    assert len(ci) == 16, f"cloud_index: expected 16, got {len(ci)}"
    li_paths = {v["middle_path"] for v in li.values()}
    for rel in ["l12/l23/l23_1.txt", "l12/l23/l23_2.txt",
                "l12/l24/l24_1.txt", "l12/l24/l24_2.txt"]:
        assert rel not in li_paths

    # --- Assert action log ---
    assert counters["local_deleted"] == 4, f"Expected local_deleted=4: {counters}"
    assert counters["remote_deleted"] == 0
    assert_no_errors(local_a, action_folder)
    actions = file_log_actions(local_a, action_folder)
    local_del = [a for a in actions if a == "LOCAL_DELETE"]
    assert len(local_del) >= 4, f"Expected at least 4 LOCAL_DELETE entries: {actions}"
    assert "REMOTE_TRASH" not in actions


# ---------------------------------------------------------------------------
# T08 — Sync filter: remote-only → synced (download from cloud)
# ---------------------------------------------------------------------------

def test_t08_syncfilter_remote_only_to_synced():
    local_a = S.local_a
    trash_before = local_trash_count(local_a)

    for path in ["l12/l23", "l12/l24"]:
        r = put(f"/file-git/repos/{S.id_a}/sync-filter", {"path": path, "mode": "synced"})
        assert r["success"], f"set sync filter failed: {r}"

    resp = post(f"/file-git/repos/{S.id_a}/sync-filter/apply")
    assert resp["success"], f"apply failed: {resp}"
    action_folder = resp["action_folder"]
    counters = resp["counters"]

    # --- Assert file positions ---
    for rel in ["l12/l23/l23_1.txt", "l12/l23/l23_2.txt",
                "l12/l24/l24_1.txt", "l12/l24/l24_2.txt"]:
        assert Path(local_a, rel).exists(), f"File should be restored: {rel}"
        assert Path(local_a, rel).read_bytes() == mock_download(S.remote_root, rel)
    assert local_trash_count(local_a) == trash_before, "Trash should not change"

    # --- Assert indexes ---
    li = read_local_index(local_a)
    ci = read_cloud_index(local_a)
    assert len(li) == 16, f"local_index: expected 16, got {len(li)}"
    assert len(ci) == 16

    # --- Assert action log ---
    assert counters["downloaded"] == 4, f"Expected downloaded=4: {counters}"
    assert counters["local_deleted"] == 0
    assert counters["remote_deleted"] == 0
    assert_no_errors(local_a, action_folder)
    actions = file_log_actions(local_a, action_folder)
    assert actions.count("DOWNLOAD") >= 4, f"Expected at least 4 DOWNLOAD: {actions}"
    assert "LOCAL_DELETE" not in actions
    assert "REMOTE_TRASH" not in actions


# ---------------------------------------------------------------------------
# T09 — Sync filter: local-only, no remote copy (no-op apply + pull)
# ---------------------------------------------------------------------------

def test_t09_syncfilter_local_only_no_remote():
    local_a = S.local_a
    trash_before = local_trash_count(local_a)

    for rel in ["l12/l25/l25_1.txt", "l12/l25/l25_2.txt"]:
        make_file(os.path.join(local_a, rel))

    r = put(f"/file-git/repos/{S.id_a}/sync-filter", {"path": "l12/l25", "mode": "local-only"})
    assert r["success"], f"set sync filter failed: {r}"

    resp = post(f"/file-git/repos/{S.id_a}/sync-filter/apply")
    assert resp["success"], f"apply failed: {resp}"
    apply_af = resp["action_folder"]
    apply_c = resp["counters"]

    resp_pull = post(f"/file-git/repos/{S.id_a}/pull")
    assert resp_pull["success"], f"pull failed: {resp_pull}"
    pull_af = resp_pull["action_folder"]

    # --- Assert file positions ---
    for rel in ["l12/l25/l25_1.txt", "l12/l25/l25_2.txt"]:
        assert Path(local_a, rel).exists(), f"local-only file must survive: {rel}"
    assert local_trash_count(local_a) == trash_before
    assert not mock_exists(S.remote_root, "l12/l25/l25_1.txt")

    # --- Assert indexes ---
    li = read_local_index(local_a)
    ci = read_cloud_index(local_a)
    assert len(li) == 18, f"local_index: expected 18, got {len(li)}"
    assert len(ci) == 16
    ci_paths = {v["middle_path"] for v in ci.values()}
    assert "l12/l25/l25_1.txt" not in ci_paths

    # --- Assert action log (apply) ---
    assert apply_c["uploaded"] == 0
    assert apply_c["downloaded"] == 0
    assert apply_c["local_deleted"] == 0
    assert apply_c["remote_deleted"] == 0

    # --- Assert action log (pull) ---
    assert resp_pull["downloaded"] == 0
    assert_no_errors(local_a, pull_af)


# ---------------------------------------------------------------------------
# T10 — Sync filter: synced (both sides) → local-only (remote soft-delete)
# ---------------------------------------------------------------------------

def test_t10_syncfilter_synced_to_local_only():
    local_a = S.local_a
    trash_before = local_trash_count(local_a)
    remote_trash_before = len(remote_trash_files(S.remote_root))

    r = put(f"/file-git/repos/{S.id_a}/sync-filter", {"path": "l11", "mode": "local-only"})
    assert r["success"], f"set sync filter failed: {r}"

    resp = post(f"/file-git/repos/{S.id_a}/sync-filter/apply")
    assert resp["success"], f"apply failed: {resp}"
    action_folder = resp["action_folder"]
    counters = resp["counters"]

    # --- Assert file positions ---
    assert Path(local_a, "l11/l11_1.txt").exists(), "local-only: local file must survive"
    assert Path(local_a, "l11/l11_2.txt").exists()
    assert local_trash_count(local_a) == trash_before, "Local trash must not grow"
    assert not mock_exists(S.remote_root, "l11/l11_1.txt"), "l11_1 should be remote-trashed"
    assert not mock_exists(S.remote_root, "l11/l11_2.txt"), "l11_2 should be remote-trashed"
    rt = remote_trash_files(S.remote_root)
    assert len(rt) == remote_trash_before + 2, f"Expected 2 new remote trash files: {rt}"
    assert "l11_1.txt" in rt, f"l11_1.txt not in remote trash: {rt}"
    assert "l11_2.txt" in rt, f"l11_2.txt not in remote trash: {rt}"

    # --- Assert indexes ---
    li = read_local_index(local_a)
    ci = read_cloud_index(local_a)
    assert len(li) == 18, f"local_index: expected 18 (unchanged), got {len(li)}"
    assert len(ci) == 14, f"cloud_index: expected 14 (16-2), got {len(ci)}"
    ci_paths = {v["middle_path"] for v in ci.values()}
    assert "l11/l11_1.txt" not in ci_paths
    assert "l11/l11_2.txt" not in ci_paths

    # --- Assert action log ---
    assert counters["remote_deleted"] == 2, f"Expected remote_deleted=2: {counters}"
    assert counters["local_deleted"] == 0
    assert_no_errors(local_a, action_folder)
    actions = file_log_actions(local_a, action_folder)
    assert actions.count("REMOTE_TRASH") >= 2, f"Expected at least 2 REMOTE_TRASH: {actions}"
    assert "LOCAL_DELETE" not in actions
    assert "UPLOAD" not in actions
    assert "DOWNLOAD" not in actions


# ---------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def _activate_mock_storage(use_mock_storage):
    """Opt this module into mock storage (session fixture from conftest)."""


@pytest.fixture(scope="module", autouse=True)
def cleanup_after_suite():
    yield
    for repo_id in [S.id_a, S.id_b]:
        if repo_id:
            try:
                delete(f"/file-git/repos/{repo_id}")
            except Exception:
                pass
    if S.remote_root:
        mock_cleanup_remote(S.remote_root)
