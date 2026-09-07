# file_git E2E Test Design

---

## Glossary

- **Manual upload/download**: calling the cloud API directly (bypassing file_git push/pull flow)
- **Verify remote**: list files via cloud API + download cloud_index and assert its content
- **Verify local**: assert file existence on disk, local_index.json content, cloud_index.json content
- **Remote test path**: read from config, never hardcoded — env var `TEST_REMOTE_ROOT`

---

## Test structure

- **Not Cypress** — tests call the backend REST API directly (`http://127.0.0.1:50001`)
- All tests run **serially**; each scenario depends on the previous one's filesystem state
- Two top-level suites: Plain (PLAIN) and Encrypted (ENCRYPTED); each suite is self-contained and cleans up after itself

---

## Configuration

`TEST_REMOTE_ROOT` is read from the environment or `config_local.py`. Never hardcoded in test code.

---

## Backend REST API reference

| Operation | Method | Path |
|---|---|---|
| Create repo | POST | `/file-git/repos` |
| Manual upload prepare | POST | `/file-git/repos/<id>/manual-upload` |
| Manual upload confirm | POST | `/file-git/repos/<id>/post-manual-upload` |
| Manual download acquire lock | POST | `/file-git/repos/<id>/pre-manual-download` |
| Manual download decrypt & reconcile | POST | `/file-git/repos/<id>/post-manual-download` |
| Push | POST | `/file-git/repos/<id>/push` |
| Pull | POST | `/file-git/repos/<id>/pull` |
| Rebuild cloud index | POST | `/file-git/repos/<id>/rebuild-cloud-index` |
| Set sync filter mode | PUT | `/file-git/repos/<id>/sync-filter` |
| Apply sync filter | POST | `/file-git/repos/<id>/sync-filter/apply` |
| Delete repo | DELETE | `/file-git/repos/<id>` |

---

## Remote directory structure

```
TEST_REMOTE_ROOT/
├── .fgit/
│   ├── cloud_index.json
│   └── _trash/
│       └── <YYYYMMDD>/     ← files moved here on REMOTE_TRASH (flat — filename only, no subdirs)
├── root1.txt
├── l11/
│   └── ...
└── l12/
    └── ...
```

**Note**: remote trash preserves only the filename (`encoded_path.split("/")[-1]`), not the original directory hierarchy.
All test filenames must be globally unique within a suite run to avoid false-positive trash matches.

---

## Suite A — Plain mode (PLAIN)

---

### T01 — Initial manual upload (full)

**Purpose**: verify manual upload populates the remote from scratch and establishes cloud_index.

**Initial file structure (8 files)**:
```
<local_a>/
├── root1.txt
├── root2.txt
├── l11/
│   ├── l11_1.txt
│   └── l11_2.txt
└── l12/
    ├── l12_1.txt
    ├── l12_2.txt
    └── l21/
        ├── l21_1.txt
        └── l21_2.txt
```

**Steps**:
1. Create temp dir `<local_a>` with the 8 files above (each with a small known text payload)
2. `POST /file-git/repos` — create repo (local_path=`<local_a>`, remote_path=`TEST_REMOTE_ROOT`, mode=PLAIN)
3. `POST /file-git/repos/<id_a>/manual-upload` (no subpath → full scan)
4. Upload the 8 files to the remote via cloud API directly
5. `POST /file-git/repos/<id_a>/post-manual-upload`

**Assert — file positions**:
- All 8 local files exist at original paths, no extras or missing
- All 8 files exist on the remote under `TEST_REMOTE_ROOT/<middle_path>`
- Remote `.fgit/cloud_index.json` exists

**Assert — indexes**:
- local_index.json: 8 entries; each middle_path + size matches disk
- cloud_index.json: 8 entries; each middle_path + size matches remote
- middle_path sets of local_index and cloud_index are identical

**Assert — action log**:
- `.fgit/action/<folder>/log/success.log` contains a MANUAL_UPLOAD_CONFIRM line
- `.fgit/action/<folder>/log/error.log` is empty or absent

---

### T02 — Manual upload subpath (incremental)

**Purpose**: verify subpath upload adds only the specified subtree to the remote.

**Changes**: add `l12/l22/` with 2 new files → total 10 files

**Steps**:
1. Create `<local_a>/l12/l22/l22_1.txt` and `l22_2.txt`
2. `POST /file-git/repos/<id_a>/manual-upload` body `{"subpath": "l12/l22"}`
3. Upload `l22_1.txt`, `l22_2.txt` to remote via cloud API
4. `POST /file-git/repos/<id_a>/post-manual-upload`

**Assert — file positions**:
- `l12/l22/l22_1.txt` and `l22_2.txt` exist both locally and on remote

**Assert — indexes**:
- local_index.json: 10 entries
- cloud_index.json: 10 entries; 2 new middle_paths + sizes correct
- queue.json has no lock (post released it)

**Assert — action log**:
- success.log contains MANUAL_UPLOAD_CONFIRM
- error.log is empty or absent

---

### T03 — Manual download subpath (partial)

**Purpose**: verify manual download of a subtree; local_index reflects only downloaded files,
cloud_index reflects the full remote.

**Steps**:
1. Create temp dir `<local_b>`, create repo id_b (local_path=`<local_b>`, remote_path=`TEST_REMOTE_ROOT`, mode=PLAIN)
2. `POST /file-git/repos/<id_b>/pre-manual-download`
3. Download the 6 files under remote `l12/` into `<local_b>/l12/` via cloud API directly
4. `POST /file-git/repos/<id_b>/post-manual-download`

**Assert — file positions (id_b)**:
- `l12/l12_1.txt`, `l12_2.txt`, `l21/l21_1.txt`, `l21_2.txt`, `l22/l22_1.txt`, `l22_2.txt` exist under `<local_b>`
- `<local_b>/root1.txt`, `root2.txt`, `l11/` do not exist
- `.fgit/buffer/` is empty (post cleaned it up)

**Assert — indexes (id_b)**:
- local_index.json: 6 entries, l12 subtree only, middle_path + size correct
- cloud_index.json: 10 entries (full remote), matches T02 remote state

**Assert — action log (id_b)**:
- success.log contains MANUAL_DOWNLOAD_CONFIRM
- error.log is empty or absent; no unmapped entries in the response

---

### T04 — Manual download remaining files

**Purpose**: verify second manual download appends to local; local_index ends equal to cloud_index.

**Steps**:
1. `POST /file-git/repos/<id_b>/pre-manual-download`
2. Download `root1.txt`, `root2.txt`, `l11/l11_1.txt`, `l11/l11_2.txt` via cloud API into `<local_b>/`
3. `POST /file-git/repos/<id_b>/post-manual-download`

**Assert — file positions (id_b)**:
- 10 files total, structure identical to `<local_a>` at end of T02
- `.fgit/buffer/` is empty

**Assert — indexes (id_b)**:
- local_index.json: 10 entries, every middle_path + size correct
- cloud_index.json: 10 entries; middle_path sets of local_index and cloud_index identical

**Assert — action log (id_b)**:
- success.log contains MANUAL_DOWNLOAD_CONFIRM; error.log empty or absent

---

### T05 — Push (new files)

**Purpose**: verify push detects locally added files and uploads them.

**Precondition**: id_a, T02 state, 10 local files

**Changes**: add 3 files → total 13

**Steps**:
1. Create `<local_a>/root3.txt`
2. Create `<local_a>/l12/l23/l23_1.txt` and `l23_2.txt`
3. `POST /file-git/repos/<id_a>/push`

**Assert — file positions**:
- Remote `root3.txt`, `l12/l23/l23_1.txt`, `l12/l23/l23_2.txt` exist
- All 3 new files remain at local original paths (not moved)

**Assert — indexes**:
- local_index.json: 13 entries; 3 new middle_paths + sizes correct
- cloud_index.json: 13 entries; middle_path set identical to local_index
- queue.json has no pending items

**Assert — action log**:
- success.log contains PUSH line; response `uploaded == 3`
- error.log empty or absent; no REMOTE_TRASH action in file_log.jsonl

---

### T06 — Pull (new files from remote)

**Purpose**: verify pull downloads cloud-only files and updates local_index.

**Precondition**: id_a, T05 state, 13 local files

**Simulate another machine uploading 3 files**:

**Steps**:
1. Upload `root4.txt`, `l12/l24/l24_1.txt`, `l12/l24/l24_2.txt` to remote via cloud API
2. `POST /file-git/repos/<id_a>/rebuild-cloud-index` (let backend re-scan remote to update cloud_index)
3. `POST /file-git/repos/<id_a>/pull`

**Assert — file positions**:
- `root4.txt`, `l12/l24/l24_1.txt`, `l12/l24/l24_2.txt` exist locally with content matching remote
- Existing 13 files are untouched (not moved or deleted)

**Assert — indexes**:
- local_index.json: 16 entries; 3 new middle_paths + sizes correct
- cloud_index.json: 16 entries; middle_path set identical to local_index
- queue.json has no pending items

**Assert — action log**:
- success.log contains PULL line; response `downloaded == 3`
- error.log empty or absent; no LOCAL_TRASH action in file_log.jsonl

---

### T07 — Sync filter: synced → remote-only (move local files to trash)

**Purpose**: verify that setting a synced path to remote-only soft-deletes local copies to local trash
without touching the remote.

**Precondition**: id_a, T06 state, 16 local files

**Steps**:
1. `PUT /file-git/repos/<id_a>/sync-filter` body `{"path": "l12/l23", "mode": "remote-only"}`
2. `PUT /file-git/repos/<id_a>/sync-filter` body `{"path": "l12/l24", "mode": "remote-only"}`
3. `POST /file-git/repos/<id_a>/sync-filter/apply`

**Assert — file positions**:
- `l12/l23/l23_1.txt`, `l23_2.txt`, `l24/l24_1.txt`, `l24_2.txt` are gone from local original paths
- `.fgit/trash/<action_folder>/l12/l23/l23_1.txt` (and siblings) exist — path hierarchy preserved
- Remote `l12/l23/` and `l12/l24/` files are still present (remote-only does not touch cloud)
- Remote `.fgit/_trash/` has no new entries

**Assert — indexes**:
- local_index.json: 12 entries; no l23 or l24 entries
- cloud_index.json: 16 entries; unchanged from T06

**Assert — action log**:
- success.log contains SYNC_FILTER_APPLY; response `local_deleted == 4`, `remote_deleted == 0`
- file_log.jsonl: 4 LOCAL_TRASH actions, 0 REMOTE_TRASH actions
- error.log empty or absent

---

### T08 — Sync filter: remote-only → synced (download from cloud)

**Purpose**: verify that switching a remote-only path back to synced downloads the cloud files to local.

**Precondition**: T07 state, 12 local files; l23 and l24 are remote-only and exist only on cloud

**Steps**:
1. `PUT /file-git/repos/<id_a>/sync-filter` body `{"path": "l12/l23", "mode": "synced"}`
2. `PUT /file-git/repos/<id_a>/sync-filter` body `{"path": "l12/l24", "mode": "synced"}`
3. `POST /file-git/repos/<id_a>/sync-filter/apply`

**Assert — file positions**:
- `l12/l23/l23_1.txt`, `l23_2.txt`, `l24/l24_1.txt`, `l24_2.txt` are back at local original paths
- File content matches the remote versions (downloaded correctly)
- `.fgit/trash/` still contains T07's files (apply never clears trash)

**Assert — indexes**:
- local_index.json: 16 entries; 4 restored entries with correct middle_path + size
- cloud_index.json: 16 entries; unchanged

**Assert — action log**:
- success.log contains SYNC_FILTER_APPLY; response `downloaded == 4`, `local_deleted == 0`, `remote_deleted == 0`
- file_log.jsonl: 4 DOWNLOAD actions, 0 LOCAL_TRASH/REMOTE_TRASH actions
- error.log empty or absent

---

### T09 — Sync filter: local-only (no remote copy; pull leaves it alone)

**Purpose**: verify that a local-only path with no remote counterpart is untouched by apply and pull.

**Precondition**: T08 state, 16 local files

**Steps**:
1. Create `<local_a>/l12/l25/l25_1.txt` and `l25_2.txt`
2. `PUT /file-git/repos/<id_a>/sync-filter` body `{"path": "l12/l25", "mode": "local-only"}`
3. `POST /file-git/repos/<id_a>/sync-filter/apply`
   — expected: remote has no l25, local-only + not on remote → no action
4. `POST /file-git/repos/<id_a>/pull`

**Assert — file positions**:
- `l12/l25/l25_1.txt`, `l25_2.txt` remain at local paths after both apply and pull
- `.fgit/trash/` has no new entries after T09 (neither apply nor pull trashes local-only files)
- Remote `l12/l25/` does not exist

**Assert — indexes**:
- local_index.json: 18 entries; l25 subtree included
- cloud_index.json: 16 entries; no l25 entries

**Assert — action log (apply)**:
- response `uploaded == 0`, `downloaded == 0`, `local_deleted == 0`, `remote_deleted == 0`

**Assert — action log (pull)**:
- response `downloaded == 0`; no l25-related actions in file_log.jsonl

---

### T10 — Sync filter: synced (both sides) → local-only (remote soft-delete)

**Purpose**: verify that switching a fully synced path to local-only moves remote files to remote trash
while leaving local files intact.

**Precondition**: T09 state, 18 local files; l11 exists on both local and remote

**Steps**:
1. `PUT /file-git/repos/<id_a>/sync-filter` body `{"path": "l11", "mode": "local-only"}`
2. `POST /file-git/repos/<id_a>/sync-filter/apply`

**Assert — file positions**:
- `l11/l11_1.txt`, `l11_2.txt` remain at local original paths (local-only does not delete local files)
- `.fgit/trash/` has no new entries (local files untouched)
- Remote `l11/l11_1.txt`, `l11_2.txt` no longer exist at original remote paths
- Remote `.fgit/_trash/<YYYYMMDD>/l11_1.txt` and `l11_2.txt` exist (flat, filename only)

**Assert — indexes**:
- local_index.json: 18 entries; l11 entries still present (local unchanged)
- cloud_index.json: 14 entries (16 − 2 l11 files; l25 was never in cloud_index)

**Assert — action log**:
- success.log contains SYNC_FILTER_APPLY; response `remote_deleted == 2`, `local_deleted == 0`
- file_log.jsonl: 2 REMOTE_TRASH actions for l11_1.txt and l11_2.txt; 0 LOCAL_TRASH/UPLOAD/DOWNLOAD actions
- error.log empty or absent

---

## Suite B — Encrypted mode (ENCRYPTED)

Runs the same T01–T10 sequence with the following differences:

- Repo is created with `mode=ENCRYPTED` and a password
- **T01/T02 manual upload**: files are AES-256-GCM encrypted; the test reads ciphertext from
  `.fgit/buffer/` (produced by the pre step) and uploads that to the remote
- **T03/T04 manual download**: test downloads ciphertext from remote into `.fgit/buffer/`;
  the post step decrypts to final local paths automatically
- **Verify remote cloud_index**: the blob is encrypted; test derives the key from
  `(password, remote_path)` using the same KDF as the backend, then decrypts and parses JSON
- **Verify local file content**: after decryption, plaintext must match the original write payload
- Uses a separate `TEST_REMOTE_ROOT_ENCRYPTED` (e.g. `.../test_encrypted`) to avoid collision with Suite A
- All counter/index/trash assertions are identical to Suite A

---

## Implementation plan

1. This document (`DESIGN.md`) — checked into `backend/tests/e2e/`
2. Pytest test code — checked into `backend/tests/e2e/`
3. Chinese design draft (`.temp.md`) — gitignored, local reference only
