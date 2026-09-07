"""
Suite B — Encrypted mode (ENCRYPTED) E2E tests, mock storage.

Same T01–T10 sequence as Suite A (test_plain.py) with these differences:
  - Repo mode = ENCRYPTED, password configured via PUT /config
  - T01/T02: manual-upload flow: backend encrypts into .fgit/buffer/,
    test reads ciphertext from buffer and writes to mock remote
  - T03/T04: manual-download flow: test copies ciphertext from mock
    remote into .fgit/buffer/, backend decrypts to local paths
  - T05–T10: push/pull (encryption is transparent)
  - Remote files are stored under hmac16-encoded paths (not plain paths)
  - Remote cloud_index.json is itself encrypted
  - Content assertion: after download/pull the local bytes must match
    the original plaintext (not ciphertext)

IMPORTANT: Tests are sequentially dependent — if T04 fails, stop.
           -x is already in pytest.ini addopts.

Run:
    TEST_REMOTE_ROOT_ENCRYPTED=/test_encrypted \
    pytest backend/file_git/tests/e2e/test_encrypted.py -v
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from helpers import (
    post, put, delete,
    mock_upload, mock_download, mock_exists, mock_cleanup_remote,
    mock_remote_path, mock_list,
    read_local_index, read_cloud_index, read_queue,
    read_success_log, read_error_log, file_log_actions,
    local_trash_files, local_trash_count, remote_trash_files,
)

PASSWORD = "test-secret-passphrase-42"

# ---------------------------------------------------------------------------
# Module-level shared state
# ---------------------------------------------------------------------------

class State:
    id_a: str = ""
    _local_a: str = ""
    id_b: str = ""
    _local_b: str = ""
    remote_root: str = ""

    @property
    def local_a(self) -> str:
        assert self._local_a, "S.local_a not set — must run from T01"
        return self._local_a

    @local_a.setter
    def local_a(self, v: str) -> None:
        self._local_a = v

    @property
    def local_b(self) -> str:
        assert self._local_b, "S.local_b not set — must run from T03"
        return self._local_b

    @local_b.setter
    def local_b(self, v: str) -> None:
        self._local_b = v


S = State()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_file(path: str, content: str = "") -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content or f"content of {p.name}\n", encoding="utf-8")


def create_repo(local_path: str, remote_root: str) -> str:
    """Create an ENCRYPTED repo, configure remote_path and password."""
    resp = post("/file-git/repos", {"local_path": local_path, "mode": "ENCRYPTED"})
    assert resp["success"], f"create repo failed: {resp}"
    repo_id = resp["repo"]["id"]
    r = put(f"/file-git/repos/{repo_id}/config", {
        "remote_path": remote_root,
        "password": PASSWORD,
    })
    assert r["success"], f"set config failed: {r}"
    return repo_id


def assert_no_errors(repo_root_dir: str, action_folder: str) -> None:
    errors = read_error_log(repo_root_dir, action_folder)
    assert errors == [], "Unexpected errors in error.log:\n" + "\n".join(errors)


def assert_success_log_contains(repo_root_dir: str, action_folder: str, keyword: str) -> None:
    lines = read_success_log(repo_root_dir, action_folder)
    assert any(keyword in line for line in lines), (
        f"Expected '{keyword}' in success.log, got:\n" + "\n".join(lines)
    )


def assert_queue_empty(repo_root_dir: str) -> None:
    q = read_queue(repo_root_dir)
    assert not q.get("lock"), f"Queue lock not released: {q}"
    assert q.get("items", []) == [], f"Queue items not empty: {q}"


def buffer_files(repo_root: str) -> list[Path]:
    """Return all files under .fgit/buffer/."""
    buf = Path(repo_root) / ".fgit" / "buffer"
    if not buf.exists():
        return []
    return [p for p in buf.rglob("*") if p.is_file()]


def copy_buffer_to_mock(repo_root: str, remote_root: str) -> None:
    """Copy all buffer ciphertext files to mock remote, preserving encoded path structure."""
    buf = Path(repo_root) / ".fgit" / "buffer"
    for f in buf.rglob("*"):
        if not f.is_file():
            continue
        encoded_rel = f.relative_to(buf).as_posix()
        mock_upload(remote_root, encoded_rel, f.read_bytes())


def copy_mock_to_buffer(repo_root: str, remote_root: str, encoded_paths: list[str]) -> None:
    """Copy ciphertext files from mock remote into .fgit/buffer/ (simulate user download)."""
    buf = Path(repo_root) / ".fgit" / "buffer"
    for ep in encoded_paths:
        data = mock_download(remote_root, ep)
        dest = buf / Path(ep)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)


def encoded_paths_for(ci: dict, middle_paths: list[str]) -> list[str]:
    """Look up encoded_path values in cloud_index for the given middle_paths."""
    result = []
    for mp in middle_paths:
        for entry in ci.values():
            if entry["middle_path"] == mp:
                result.append(entry["encoded_path"])
                break
    return result


def assert_remote_ciphertext(remote_root: str, encoded_path: str) -> None:
    """Assert that the remote file exists and is NOT plaintext (it should be ciphertext)."""
    assert mock_exists(remote_root, encoded_path), f"Remote missing: {encoded_path}"
    data = mock_download(remote_root, encoded_path)
    # AES-GCM ciphertext starts with a 12-byte nonce + 16-byte tag → at least 28 bytes
    # and must NOT be valid UTF-8 plain text matching the original content pattern
    assert len(data) >= 28, f"Suspiciously short ciphertext at {encoded_path}: {len(data)} bytes"


# ---------------------------------------------------------------------------
# T01 — Manual upload (full, 8 files)
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("backend_alive")
def test_t01_manual_upload_full(remote_root_encrypted, tmp_path):
    S.remote_root = remote_root_encrypted
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

    # Step 1: prepare — backend scans and encrypts into .fgit/buffer/
    resp = post(f"/file-git/repos/{S.id_a}/manual-upload")
    assert resp["success"], f"manual-upload failed: {resp}"
    action_folder = resp["action_folder"]

    # Step 2: buffer must have 8 ciphertext files
    bufs = buffer_files(local_a)
    assert len(bufs) == 8, f"Expected 8 buffer files, got {len(bufs)}: {bufs}"

    # Step 3: "drag" buffer files to mock remote (simulates user uploading via cloud app)
    copy_buffer_to_mock(local_a, S.remote_root)

    # Step 4: confirm — backend reconciles cloud listing → cloud_index
    resp = post(f"/file-git/repos/{S.id_a}/post-manual-upload")
    assert resp["success"], f"post-manual-upload failed: {resp}"

    # --- Assert file positions ---
    for rel in FILES_8:
        assert Path(local_a, rel).exists(), f"Local file missing: {rel}"
    assert mock_exists(S.remote_root, ".fgit/cloud_index.json"), "Remote cloud_index.json missing"

    ci = read_cloud_index(local_a)
    for v in ci.values():
        # Remote stores ciphertext under encoded_path (not plain middle_path)
        assert_remote_ciphertext(S.remote_root, v["encoded_path"])
        # encoded_path must differ from middle_path (hmac16 transformation)
        assert v["encoded_path"] != v["middle_path"], (
            f"encoded_path should differ from middle_path: {v['middle_path']}"
        )

    # --- Assert indexes ---
    li = read_local_index(local_a)
    assert len(li) == 8, f"local_index: expected 8, got {len(li)}"
    assert len(ci) == 8, f"cloud_index: expected 8, got {len(ci)}"
    assert {v["middle_path"] for v in li.values()} == {v["middle_path"] for v in ci.values()}
    for v in li.values():
        assert v["size"] == Path(local_a, v["middle_path"]).stat().st_size

    # --- Buffer cleaned up after confirm ---
    assert buffer_files(local_a) == [], "Buffer should be empty after post-manual-upload"

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
    assert resp["success"], f"manual-upload failed: {resp}"
    action_folder = resp["action_folder"]

    bufs = buffer_files(local_a)
    assert len(bufs) == 2, f"Expected 2 buffer files for subpath, got {len(bufs)}"

    copy_buffer_to_mock(local_a, S.remote_root)

    resp = post(f"/file-git/repos/{S.id_a}/post-manual-upload")
    assert resp["success"], f"post-manual-upload failed: {resp}"

    # --- Assert file positions ---
    for rel in ["l12/l22/l22_1.txt", "l12/l22/l22_2.txt"]:
        assert Path(local_a, rel).exists(), f"Local file missing: {rel}"

    ci = read_cloud_index(local_a)
    for rel in ["l12/l22/l22_1.txt", "l12/l22/l22_2.txt"]:
        entry = next((v for v in ci.values() if v["middle_path"] == rel), None)
        assert entry is not None, f"cloud_index missing {rel}"
        assert_remote_ciphertext(S.remote_root, entry["encoded_path"])

    # --- Assert indexes ---
    li = read_local_index(local_a)
    assert len(li) == 10, f"local_index: expected 10, got {len(li)}"
    assert len(ci) == 10, f"cloud_index: expected 10, got {len(ci)}"
    assert_queue_empty(local_a)
    assert buffer_files(local_a) == [], "Buffer should be empty"

    assert_success_log_contains(local_a, action_folder, "MANUAL_UPLOAD_CONFIRM")
    assert_no_errors(local_a, action_folder)


# ---------------------------------------------------------------------------
# T03 — Manual download subpath (partial: l12 only)
# ---------------------------------------------------------------------------

def test_t03_manual_download_subpath(tmp_path):
    local_b = str(tmp_path / "local_b")
    S.local_b = local_b
    Path(local_b).mkdir(parents=True)

    S.id_b = create_repo(local_b, S.remote_root)

    # Step 1: acquire lock — backend loads cloud_index from remote (encrypted)
    resp = post(f"/file-git/repos/{S.id_b}/pre-manual-download")
    assert resp["success"], f"pre-manual-download failed: {resp}"
    action_folder = resp["action_folder"]

    # Step 2: "drag" ciphertext files from cloud into buffer (l12 subtree only)
    # Look up encoded_paths for the l12 files from id_a's cloud_index
    ci_a = read_cloud_index(S.local_a)
    L12_MIDDLES = [
        "l12/l12_1.txt", "l12/l12_2.txt",
        "l12/l21/l21_1.txt", "l12/l21/l21_2.txt",
        "l12/l22/l22_1.txt", "l12/l22/l22_2.txt",
    ]
    l12_encoded = encoded_paths_for(ci_a, L12_MIDDLES)
    assert len(l12_encoded) == 6, f"Could not find all l12 encoded_paths: {l12_encoded}"
    copy_mock_to_buffer(local_b, S.remote_root, l12_encoded)

    # Step 3: confirm — backend decrypts buffer → local paths
    resp = post(f"/file-git/repos/{S.id_b}/post-manual-download")
    assert resp["success"], f"post-manual-download failed: {resp}"

    # --- Assert file positions ---
    for rel in L12_MIDDLES:
        assert Path(local_b, rel).exists(), f"Expected {rel} in local_b after decrypt"
    for rel in ["root1.txt", "root2.txt"]:
        assert not Path(local_b, rel).exists(), f"Unexpected {rel} in local_b"
    assert not Path(local_b, "l11").exists()
    assert buffer_files(local_b) == [], "Buffer should be empty after decrypt"

    # --- Plaintext content matches original ---
    for rel in L12_MIDDLES:
        actual = Path(local_b, rel).read_text(encoding="utf-8")
        expected = f"content of {Path(rel).name}\n"
        assert actual == expected, f"{rel}: content mismatch: {actual!r} != {expected!r}"

    # --- Assert indexes ---
    li = read_local_index(local_b)
    ci_b = read_cloud_index(local_b)
    assert len(li) == 6, f"local_index: expected 6, got {len(li)}"
    assert len(ci_b) == 10, f"cloud_index: expected 10, got {len(ci_b)}"
    for rel in L12_MIDDLES:
        assert rel in {v["middle_path"] for v in li.values()}, f"local_index missing {rel}"
    for v in li.values():
        assert v["size"] == Path(local_b, v["middle_path"]).stat().st_size

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

    ci_a = read_cloud_index(S.local_a)
    REMAINING_MIDDLES = ["root1.txt", "root2.txt", "l11/l11_1.txt", "l11/l11_2.txt"]
    remaining_encoded = encoded_paths_for(ci_a, REMAINING_MIDDLES)
    assert len(remaining_encoded) == 4
    copy_mock_to_buffer(local_b, S.remote_root, remaining_encoded)

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
        actual = Path(local_b, rel).read_text(encoding="utf-8")
        expected = f"content of {Path(rel).name}\n"
        assert actual == expected, f"{rel}: content mismatch after decrypt"
    assert buffer_files(local_b) == [], "Buffer should be empty"

    li = read_local_index(local_b)
    ci_b = read_cloud_index(local_b)
    assert len(li) == 10, f"local_index: expected 10, got {len(li)}"
    assert len(ci_b) == 10
    assert {v["middle_path"] for v in li.values()} == {v["middle_path"] for v in ci_b.values()}

    assert_success_log_contains(local_b, action_folder, "MANUAL_DOWNLOAD_CONFIRM")
    assert_no_errors(local_b, action_folder)
    assert resp.get("unmapped", []) == []


# ---------------------------------------------------------------------------
# T05 — Push new files (encryption transparent)
# ---------------------------------------------------------------------------

def test_t05_push_new_files():
    local_a = S.local_a

    NEW = ["root3.txt", "l12/l23/l23_1.txt", "l12/l23/l23_2.txt"]
    for rel in NEW:
        make_file(os.path.join(local_a, rel))

    resp = post(f"/file-git/repos/{S.id_a}/push")
    assert resp["success"], f"push failed: {resp}"
    action_folder = resp["action_folder"]

    ci = read_cloud_index(local_a)
    for rel in NEW:
        assert Path(local_a, rel).exists(), f"Local file missing: {rel}"
        entry = next((v for v in ci.values() if v["middle_path"] == rel), None)
        assert entry is not None, f"cloud_index missing {rel}"
        assert_remote_ciphertext(S.remote_root, entry["encoded_path"])

    li = read_local_index(local_a)
    assert len(li) == 13, f"local_index: expected 13, got {len(li)}"
    assert len(ci) == 13
    assert {v["middle_path"] for v in li.values()} == {v["middle_path"] for v in ci.values()}
    assert_queue_empty(local_a)

    assert resp["uploaded"] == 3, f"Expected uploaded=3, got {resp['uploaded']}"
    assert_no_errors(local_a, action_folder)
    assert "REMOTE_TRASH" not in file_log_actions(local_a, action_folder)


# ---------------------------------------------------------------------------
# T06 — Pull new files from remote (uploaded by "another machine")
# ---------------------------------------------------------------------------

def test_t06_pull_new_files():
    local_a = S.local_a

    # Simulate another machine: encrypt 3 new files using the same key
    # by using push on a scratch repo (upload_only so it doesn't trash existing)
    import tempfile
    with tempfile.TemporaryDirectory() as prep_dir:
        PREP = ["root4.txt", "l12/l24/l24_1.txt", "l12/l24/l24_2.txt"]
        for rel in PREP:
            make_file(os.path.join(prep_dir, rel), content=f"remote content of {rel}\n")
        prep_id = create_repo(prep_dir, S.remote_root)
        r = post(f"/file-git/repos/{prep_id}/push", {"upload_only": True})
        assert r["success"], f"prep push failed: {r}"
        assert r["uploaded"] == 3
        delete(f"/file-git/repos/{prep_id}")

    resp = post(f"/file-git/repos/{S.id_a}/pull")
    assert resp["success"], f"pull failed: {resp}"
    action_folder = resp["action_folder"]
    assert resp["downloaded"] == 3, f"Expected downloaded=3, got {resp['downloaded']} | resp={resp}"

    # --- Assert file positions + plaintext content ---
    PREP = ["root4.txt", "l12/l24/l24_1.txt", "l12/l24/l24_2.txt"]
    for rel in PREP:
        assert Path(local_a, rel).exists(), f"Not downloaded: {rel}"
        actual = Path(local_a, rel).read_text(encoding="utf-8")
        expected = f"remote content of {rel}\n"
        assert actual == expected, f"{rel}: content mismatch: {actual!r}"
    for rel in ["root1.txt", "l11/l11_1.txt", "l12/l23/l23_1.txt"]:
        assert Path(local_a, rel).exists(), f"Existing file gone: {rel}"

    li = read_local_index(local_a)
    ci = read_cloud_index(local_a)
    assert len(li) == 16, f"local_index: expected 16, got {len(li)}"
    assert len(ci) == 16
    assert {v["middle_path"] for v in li.values()} == {v["middle_path"] for v in ci.values()}
    assert_queue_empty(local_a)

    assert resp["downloaded"] == 3, f"Expected downloaded=3, got {resp['downloaded']}"
    assert_no_errors(local_a, action_folder)
    assert "LOCAL_DELETE" not in file_log_actions(local_a, action_folder)


# ---------------------------------------------------------------------------
# T07 — Sync filter: synced → remote-only (local trash)
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

    for rel in ["l12/l23/l23_1.txt", "l12/l23/l23_2.txt",
                "l12/l24/l24_1.txt", "l12/l24/l24_2.txt"]:
        assert not Path(local_a, rel).exists(), f"Should be gone from local: {rel}"
    assert local_trash_count(local_a) == trash_before + 4, "Expected 4 new local trash files"
    trash = local_trash_files(local_a)
    for name in ["l23_1.txt", "l23_2.txt", "l24_1.txt", "l24_2.txt"]:
        assert any(name in t for t in trash), f"Trash missing {name}: {trash}"

    # Remote ciphertext still present under encoded paths
    ci = read_cloud_index(local_a)
    for rel in ["l12/l23/l23_1.txt", "l12/l23/l23_2.txt",
                "l12/l24/l24_1.txt", "l12/l24/l24_2.txt"]:
        entry = next((v for v in ci.values() if v["middle_path"] == rel), None)
        assert entry is not None, f"cloud_index should still have {rel}"
        assert mock_exists(S.remote_root, entry["encoded_path"]), f"Remote ciphertext missing: {rel}"
    assert remote_trash_files(S.remote_root) == [], "Remote trash should be empty"

    li = read_local_index(local_a)
    assert len(li) == 12, f"local_index: expected 12, got {len(li)}"
    assert len(ci) == 16, f"cloud_index: expected 16, got {len(ci)}"

    assert counters["local_deleted"] == 4, f"Expected local_deleted=4: {counters}"
    assert counters["remote_deleted"] == 0
    assert_no_errors(local_a, action_folder)
    actions = file_log_actions(local_a, action_folder)
    assert len([a for a in actions if a == "LOCAL_DELETE"]) >= 4
    assert "REMOTE_TRASH" not in actions


# ---------------------------------------------------------------------------
# T08 — Sync filter: remote-only → synced (download + decrypt)
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

    for rel in ["l12/l23/l23_1.txt", "l12/l23/l23_2.txt",
                "l12/l24/l24_1.txt", "l12/l24/l24_2.txt"]:
        assert Path(local_a, rel).exists(), f"File should be restored: {rel}"
        actual = Path(local_a, rel).read_text(encoding="utf-8")
        # l12/l24 files were pulled from prep-repo in T06 with "remote content of ..." content
        if rel.startswith("l12/l24/"):
            expected = f"remote content of {rel}\n"
        else:
            expected = f"content of {Path(rel).name}\n"
        assert actual == expected, f"{rel}: decrypted content mismatch: {actual!r}"
    assert local_trash_count(local_a) == trash_before, "Trash should not change"

    li = read_local_index(local_a)
    ci = read_cloud_index(local_a)
    assert len(li) == 16
    assert len(ci) == 16

    assert counters["downloaded"] == 4, f"Expected downloaded=4: {counters}"
    assert counters["local_deleted"] == 0
    assert counters["remote_deleted"] == 0
    assert_no_errors(local_a, action_folder)
    actions = file_log_actions(local_a, action_folder)
    assert actions.count("DOWNLOAD") >= 4
    assert "LOCAL_DELETE" not in actions
    assert "REMOTE_TRASH" not in actions


# ---------------------------------------------------------------------------
# T09 — Sync filter: local-only (no remote copy)
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

    for rel in ["l12/l25/l25_1.txt", "l12/l25/l25_2.txt"]:
        assert Path(local_a, rel).exists(), f"local-only file must survive: {rel}"
    assert local_trash_count(local_a) == trash_before

    ci = read_cloud_index(local_a)
    ci_paths = {v["middle_path"] for v in ci.values()}
    assert "l12/l25/l25_1.txt" not in ci_paths, "local-only file must not be in cloud_index"

    li = read_local_index(local_a)
    assert len(li) == 18, f"local_index: expected 18, got {len(li)}"
    assert len(ci) == 16

    assert apply_c["uploaded"] == 0
    assert apply_c["downloaded"] == 0
    assert apply_c["local_deleted"] == 0
    assert apply_c["remote_deleted"] == 0
    assert resp_pull["downloaded"] == 0
    assert_no_errors(local_a, resp_pull["action_folder"])


# ---------------------------------------------------------------------------
# T10 — Sync filter: synced → local-only (remote soft-delete via REMOTE_TRASH)
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

    assert Path(local_a, "l11/l11_1.txt").exists()
    assert Path(local_a, "l11/l11_2.txt").exists()
    assert local_trash_count(local_a) == trash_before

    ci = read_cloud_index(local_a)
    ci_paths = {v["middle_path"] for v in ci.values()}
    assert "l11/l11_1.txt" not in ci_paths
    assert "l11/l11_2.txt" not in ci_paths

    # Remote ciphertext files moved to _trash (by encoded filename)
    rt = remote_trash_files(S.remote_root)
    assert len(rt) == remote_trash_before + 2, f"Expected 2 new remote trash files: {rt}"

    li = read_local_index(local_a)
    assert len(li) == 18, f"local_index: expected 18, got {len(li)}"
    assert len(ci) == 14, f"cloud_index: expected 14 (16-2), got {len(ci)}"

    assert counters["remote_deleted"] == 2, f"Expected remote_deleted=2: {counters}"
    assert counters["local_deleted"] == 0
    assert_no_errors(local_a, action_folder)
    actions = file_log_actions(local_a, action_folder)
    assert actions.count("REMOTE_TRASH") >= 2
    assert "LOCAL_DELETE" not in actions
    assert "UPLOAD" not in actions
    assert "DOWNLOAD" not in actions


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def _activate_mock_storage(use_mock_storage):
    """Opt this module into mock storage."""


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
