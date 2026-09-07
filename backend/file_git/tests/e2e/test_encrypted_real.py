"""
Suite B (Real) — Encrypted mode E2E tests against real BaiduCloudStorage.

Same T01–T10 logic as test_encrypted.py (mock) but against the real Baidu Pan API.
Buffer files (ciphertext) are uploaded/downloaded programmatically via BaiduCloudStorage
— no manual user interaction required.

Requires:
  - A running backend with valid Baidu credentials in settings.json
  - TEST_REMOTE_ROOT_ENCRYPTED set to a path under the app's root_prefix
    e.g. /apps/sync-assistant/fgit_selftest/e2e_enc

Run:
    TEST_REMOTE_ROOT_ENCRYPTED=/apps/sync-assistant/fgit_selftest/e2e_enc \\
        pytest backend/tests/e2e/test_encrypted_real.py -v -s

Do NOT run this in CI — it calls real Baidu Pan.
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import pytest

# Make sure the backend package is importable (tests/e2e → backend/)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from helpers import (
    post, put, delete,
    read_local_index, read_cloud_index, read_queue,
    read_success_log, read_error_log, file_log_actions,
    local_trash_files, local_trash_count,
    BASE_URL,
)

PASSWORD = "test-secret-passphrase-42"
TIMEOUT = 300


def rpost(path: str, body: dict | None = None) -> dict:
    return post(path, body, timeout=TIMEOUT)


def rput(path: str, body: dict) -> dict:
    return put(path, body, timeout=TIMEOUT)


def rpost_raw(path: str, body: dict | None = None) -> dict:
    """Like rpost but does NOT raise on HTTP 5xx.

    Used for endpoints whose controller returns HTTP 500 even when the
    business logic succeeds partially (e.g. post-manual-upload with missing
    files, post-manual-download with unmapped files).  We check resp["success"]
    directly instead.
    """
    import requests as _requests
    resp = _requests.post(
        BASE_URL + path,
        json=body or {},
        timeout=TIMEOUT,
    )
    return resp.json()


# ---------------------------------------------------------------------------
# Storage helper — direct Baidu API calls (bypass Flask, same credentials)
# ---------------------------------------------------------------------------

def _get_storage():
    """Construct a BaiduCloudStorage instance using the same settings as the backend."""
    from file_git.settings_manager import SettingsManager
    from file_git.cloud.baidu import BaiduCloudStorage

    def token_provider():
        return SettingsManager.get_baidu_credentials()["access_token"]

    root_prefix = SettingsManager.get_baidu_root_prefix()
    return BaiduCloudStorage(token_provider, root_prefix=root_prefix)


def auto_cleanup_remote(remote_root: str) -> int:
    """Delete all files under remote_root on Baidu Pan.

    Called at the start of T01 so stale files from previous runs do not
    pollute the cloud listing that later tests assert against.
    Returns the number of files deleted.
    """
    storage = _get_storage()
    count = 0
    for meta in list(storage.list_files(remote_root)):
        storage.delete(meta["remote_path"])
        count += 1
    return count


def auto_upload_buffer(repo_root: str, remote_root: str) -> int:
    """Upload all files in .fgit/buffer/ to Baidu Pan under remote_root/.

    Preserves the sub-directory structure of the buffer (each file's relative
    path under buffer/ becomes its encoded_path under remote_root/).
    Returns the number of files uploaded.
    """
    storage = _get_storage()
    buf = Path(repo_root) / ".fgit" / "buffer"
    count = 0
    for f in sorted(buf.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(buf).as_posix()          # encoded_path
        remote_path = f"{remote_root.rstrip('/')}/{rel}"
        data = f.read_bytes()
        storage.upload(io.BytesIO(data), remote_path, len(data))
        count += 1
    return count


def auto_download_to_buffer(repo_root: str, remote_root: str,
                             encoded_paths: list[str]) -> int:
    """Download specified encoded_paths from Baidu Pan into .fgit/buffer/.

    Preserves sub-directory structure so post-manual-download can map them
    back via cloud_index.  Returns the number of files downloaded.
    """
    storage = _get_storage()
    buf = Path(repo_root) / ".fgit" / "buffer"
    count = 0
    for ep in encoded_paths:
        remote_path = f"{remote_root.rstrip('/')}/{ep}"
        target = buf / Path(ep)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as fh:
            storage.download(remote_path, fh)
        count += 1
    return count


# ---------------------------------------------------------------------------
# Module-level shared state
# ---------------------------------------------------------------------------

class State:
    id_a: str = ""
    _local_a: str = ""
    id_b: str = ""
    _local_b: str = ""
    remote_root: str = ""
    id_prep: str = ""

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
    resp = rpost("/file-git/repos", {"local_path": local_path, "mode": "ENCRYPTED"})
    assert resp["success"], f"create repo failed: {resp}"
    repo_id = resp["repo"]["id"]
    r = rput(f"/file-git/repos/{repo_id}/config", {
        "remote_path": remote_root,
        "password": PASSWORD,
    })
    assert r["success"], f"set config failed: {r}"
    return repo_id


def buffer_files(repo_root: str) -> list[Path]:
    buf = Path(repo_root) / ".fgit" / "buffer"
    if not buf.exists():
        return []
    return [p for p in buf.rglob("*") if p.is_file()]


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


def encoded_paths_for(ci: dict, middle_paths: list[str]) -> list[str]:
    result = []
    for mp in middle_paths:
        for entry in ci.values():
            if entry["middle_path"] == mp:
                result.append(entry["encoded_path"])
                break
    return result


# ---------------------------------------------------------------------------
# T01 — Manual upload (full, 8 files)
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("backend_alive")
def test_t01_manual_upload_full(remote_root_encrypted, tmp_path):
    S.remote_root = remote_root_encrypted
    auto_cleanup_remote(S.remote_root)

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

    # Step 1: backend encrypts into .fgit/buffer/
    resp = rpost(f"/file-git/repos/{S.id_a}/manual-upload")
    assert resp["success"], f"manual-upload failed: {resp}"
    action_folder = resp["action_folder"]

    bufs = buffer_files(local_a)
    assert len(bufs) == 8, f"Expected 8 buffer files, got {len(bufs)}: {bufs}"

    # Step 1b: upload buffer files to Baidu Pan programmatically
    uploaded = auto_upload_buffer(local_a, S.remote_root)
    assert uploaded == 8, f"Expected to upload 8 files, uploaded {uploaded}"

    # Step 2: confirm
    resp = rpost_raw(f"/file-git/repos/{S.id_a}/post-manual-upload")
    assert resp["success"], f"post-manual-upload failed: {resp}"
    assert resp["confirmed"] == 8, f"Expected 8 confirmed: {resp}"
    assert resp["missing"] == [], f"Missing files: {resp['missing']}"

    for rel in FILES_8:
        assert Path(local_a, rel).exists(), f"Local file missing: {rel}"
    assert buffer_files(local_a) == [], "Buffer should be empty after confirm"

    ci = read_cloud_index(local_a)
    li = read_local_index(local_a)
    assert len(li) == 8, f"local_index: expected 8, got {len(li)}"
    assert len(ci) == 8, f"cloud_index: expected 8, got {len(ci)}"
    assert {v["middle_path"] for v in li.values()} == {v["middle_path"] for v in ci.values()}
    for v in li.values():
        assert v["size"] == Path(local_a, v["middle_path"]).stat().st_size

    for v in ci.values():
        assert v["encoded_path"] != v["middle_path"], (
            f"encoded_path should differ from middle_path: {v['middle_path']}"
        )

    assert_success_log_contains(local_a, action_folder, "MANUAL_UPLOAD_CONFIRM")
    assert_no_errors(local_a, action_folder)


# ---------------------------------------------------------------------------
# T02 — Manual upload subpath (incremental)
# ---------------------------------------------------------------------------

def test_t02_manual_upload_subpath():
    local_a = S.local_a

    for rel in ["l12/l22/l22_1.txt", "l12/l22/l22_2.txt"]:
        make_file(os.path.join(local_a, rel))

    resp = rpost(f"/file-git/repos/{S.id_a}/manual-upload", {"subpath": "l12/l22"})
    assert resp["success"], f"manual-upload failed: {resp}"
    action_folder = resp["action_folder"]

    bufs = buffer_files(local_a)
    assert len(bufs) == 2, f"Expected 2 buffer files for subpath, got {len(bufs)}"

    uploaded = auto_upload_buffer(local_a, S.remote_root)
    assert uploaded == 2, f"Expected to upload 2 files, uploaded {uploaded}"

    resp = rpost_raw(f"/file-git/repos/{S.id_a}/post-manual-upload")
    assert resp["success"], f"post-manual-upload failed: {resp}"
    assert resp["confirmed"] == 2
    assert resp["missing"] == []

    ci = read_cloud_index(local_a)
    for rel in ["l12/l22/l22_1.txt", "l12/l22/l22_2.txt"]:
        entry = next((v for v in ci.values() if v["middle_path"] == rel), None)
        assert entry is not None, f"cloud_index missing {rel}"
        assert entry["encoded_path"] != rel

    li = read_local_index(local_a)
    assert len(li) == 10, f"local_index: expected 10, got {len(li)}"
    assert len(ci) == 10
    assert {v["middle_path"] for v in li.values()} == {v["middle_path"] for v in ci.values()}
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

    resp = rpost(f"/file-git/repos/{S.id_b}/pre-manual-download")
    assert resp["success"], f"pre-manual-download failed: {resp}"
    action_folder = resp["action_folder"]

    ci_a = read_cloud_index(S.local_a)
    L12_MIDDLES = [
        "l12/l12_1.txt", "l12/l12_2.txt",
        "l12/l21/l21_1.txt", "l12/l21/l21_2.txt",
        "l12/l22/l22_1.txt", "l12/l22/l22_2.txt",
    ]
    l12_encoded = encoded_paths_for(ci_a, L12_MIDDLES)
    assert len(l12_encoded) == 6, f"Could not find all l12 encoded_paths: {l12_encoded}"

    # Download ciphertext files from Baidu Pan into buffer
    downloaded = auto_download_to_buffer(local_b, S.remote_root, l12_encoded)
    assert downloaded == 6, f"Expected to download 6 files, got {downloaded}"

    resp = rpost_raw(f"/file-git/repos/{S.id_b}/post-manual-download")
    assert resp["success"], f"post-manual-download failed: {resp}"
    assert resp.get("unmapped", []) == [], f"Unmapped files: {resp.get('unmapped')}"

    for rel in L12_MIDDLES:
        assert Path(local_b, rel).exists(), f"Expected {rel} in local_b after decrypt"
    for rel in ["root1.txt", "root2.txt"]:
        assert not Path(local_b, rel).exists(), f"Unexpected {rel} in local_b"
    assert not Path(local_b, "l11").exists()
    assert buffer_files(local_b) == [], "Buffer should be empty after decrypt"

    for rel in L12_MIDDLES:
        actual = Path(local_b, rel).read_text(encoding="utf-8")
        expected = f"content of {Path(rel).name}\n"
        assert actual == expected, f"{rel}: content mismatch: {actual!r} != {expected!r}"

    li = read_local_index(local_b)
    ci_b = read_cloud_index(local_b)
    assert len(li) == 6, f"local_index: expected 6, got {len(li)}"
    assert len(ci_b) == 10, f"cloud_index: expected 10, got {len(ci_b)}"

    assert_success_log_contains(local_b, action_folder, "MANUAL_DOWNLOAD_CONFIRM")
    assert_no_errors(local_b, action_folder)


# ---------------------------------------------------------------------------
# T04 — Manual download remaining files
# ---------------------------------------------------------------------------

def test_t04_manual_download_remaining():
    local_b = S.local_b

    resp = rpost(f"/file-git/repos/{S.id_b}/pre-manual-download")
    assert resp["success"], f"pre-manual-download failed: {resp}"
    action_folder = resp["action_folder"]

    ci_a = read_cloud_index(S.local_a)
    REMAINING_MIDDLES = ["root1.txt", "root2.txt", "l11/l11_1.txt", "l11/l11_2.txt"]
    remaining_encoded = encoded_paths_for(ci_a, REMAINING_MIDDLES)
    assert len(remaining_encoded) == 4

    downloaded = auto_download_to_buffer(local_b, S.remote_root, remaining_encoded)
    assert downloaded == 4, f"Expected to download 4 files, got {downloaded}"

    resp = rpost_raw(f"/file-git/repos/{S.id_b}/post-manual-download")
    assert resp["success"], f"post-manual-download failed: {resp}"
    assert resp.get("unmapped", []) == []

    ALL_10 = [
        "root1.txt", "root2.txt",
        "l11/l11_1.txt", "l11/l11_2.txt",
        "l12/l12_1.txt", "l12/l12_2.txt",
        "l12/l21/l21_1.txt", "l12/l21/l21_2.txt",
        "l12/l22/l22_1.txt", "l12/l22/l22_2.txt",
    ]
    for rel in ALL_10:
        assert Path(local_b, rel).exists(), f"Missing after decrypt: {rel}"
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


# ---------------------------------------------------------------------------
# T05 — Push new files
# ---------------------------------------------------------------------------

def test_t05_push_new_files():
    local_a = S.local_a

    NEW = ["root3.txt", "l12/l23/l23_1.txt", "l12/l23/l23_2.txt"]
    for rel in NEW:
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

    for rel in NEW:
        assert Path(local_a, rel).exists(), f"Local file missing: {rel}"
        entry = next((v for v in ci.values() if v["middle_path"] == rel), None)
        assert entry is not None, f"cloud_index missing entry for {rel}"
        assert entry["encoded_path"] != rel

    assert resp["uploaded"] == 3, f"Expected uploaded=3, got {resp['uploaded']}"
    assert_no_errors(local_a, action_folder)
    assert "REMOTE_TRASH" not in file_log_actions(local_a, action_folder)


# ---------------------------------------------------------------------------
# T06 — Pull new files from remote (simulated "another machine" push)
#
# Uses a scratch prep-repo + upload_only=True push to pre-populate the remote.
# Does NOT use rebuild-cloud-index — in ENCRYPTED mode that would produce
# UNKNOWN_* entries for files not already in old_index.
# ---------------------------------------------------------------------------

def test_t06_pull_new_files(tmp_path):
    local_a = S.local_a

    local_prep = str(tmp_path / "local_prep")
    Path(local_prep).mkdir()
    PREP = ["root4.txt", "l12/l24/l24_1.txt", "l12/l24/l24_2.txt"]
    for rel in PREP:
        make_file(os.path.join(local_prep, rel), content=f"remote content of {rel}\n")

    S.id_prep = create_repo(local_prep, S.remote_root)
    r = rpost(f"/file-git/repos/{S.id_prep}/push", {"upload_only": True})
    assert r["success"], f"prep push failed: {r}"
    assert r["uploaded"] == 3, f"Expected prep uploaded=3: {r}"

    resp = rpost(f"/file-git/repos/{S.id_a}/pull")
    assert resp["success"], f"pull failed: {resp}"
    action_folder = resp["action_folder"]

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

    assert resp["downloaded"] == 3, f"Expected downloaded=3: {resp}"
    assert_no_errors(local_a, action_folder)
    assert "LOCAL_DELETE" not in file_log_actions(local_a, action_folder)


# ---------------------------------------------------------------------------
# T07 — Sync filter: synced → remote-only
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

    ci = read_cloud_index(local_a)
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
# T08 — Sync filter: remote-only → synced
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
        actual = Path(local_a, rel).read_text(encoding="utf-8")
        # l12/l24 files were pulled from prep-repo in T06
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


# ---------------------------------------------------------------------------
# T10 — Sync filter: synced → local-only (remote soft-delete)
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
    # Encrypted files on Baidu Pan under S.remote_root are NOT auto-deleted.
    # Clean up manually via Baidu Pan web UI after the test run.
