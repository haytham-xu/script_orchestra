"""
Video Duplicate Finder — Hash Cache & DB Layer.

DECOUPLED: this module must not import from duplicate_finder.

Responsibilities:
  - SQLite schema for video_hashes / video_similarities / duplicate_video_groups /
    video_group_stats / video_whitelist* / video_duplicate_finder_meta
    (mirrors duplicate_finder's PHashCache shape, schema in
     `buffer/04_image_to_video_mapping.md` §2)
  - Top-level worker function `_compute_video_hash` (multiprocessing-pickleable)
  - `VideoHashCache` class for cached read/write of video signatures and
    whitelist groups
  - Maintenance helpers (cleanup of missing files, file-exists verification)

Workflow (Phase 1/2/2.5/3) lives in `video_workflow.py` and uses this layer.
"""
import hashlib
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import imagehash

from .frame_extractor import (
    bgr_to_pil,
    extract_frame_at_ffmpeg_fallback,
    extract_frames_at_cv2_batch,
    extract_thumbnail,
    probe_metadata,
    compute_sample_points,
    thumbnail_filename_for,
)


# ===========================================================================
# Constants (top-level so multiprocessing workers see them after spawn re-import)
# ===========================================================================

# Hash dimensions. See DECISION D-17 / 04 §1.2.
N_FRAMES = 8                        # frames sampled per video
BITS_PER_FRAME = 64                 # imagehash.phash(hash_size=8)
HEX_PER_FRAME = 16                  # 64 bits = 16 hex chars
VIDEO_HASH_BITS = N_FRAMES * BITS_PER_FRAME  # 512

# Phash input width (cv2.resize before crossing into PIL/imagehash)
THUMB_WIDTH = 320


# ===========================================================================
# Worker global state
# ===========================================================================

# scan_delay (seconds) applied inside the worker before each compute call.
# Set per-process via set_compute_delay(); used by the wrapped worker entry.
# Module-level mutable global is necessary because multiprocessing.Pool on
# Windows uses spawn — each worker re-imports this module and reads the
# current value from its own process memory.
_COMPUTE_DELAY: float = 0.0


def set_compute_delay(delay: float) -> None:
    """Set per-process compute delay (seconds) before each worker call."""
    global _COMPUTE_DELAY
    _COMPUTE_DELAY = float(delay or 0.0)


# ===========================================================================
# Distance metric
# ===========================================================================

def video_distance(sig_a: str, sig_b: str) -> int:
    """
    Hamming-aligned distance between two video signatures.

    Value range: 0 (identical) .. VIDEO_HASH_BITS (completely different).

    Signatures whose frame count differs are treated as "completely different"
    — they're not comparable. Same applies to a frame whose hex is malformed.
    """
    a = sig_a.split('|')
    b = sig_b.split('|')
    if len(a) != len(b):
        return VIDEO_HASH_BITS
    total = 0
    for fa, fb in zip(a, b):
        try:
            total += bin(int(fa, 16) ^ int(fb, 16)).count('1')
        except (ValueError, TypeError):
            total += BITS_PER_FRAME
    return total


# ===========================================================================
# Worker: compute one video's signature
# ===========================================================================

def _compute_video_hash(file_path: str,
                       thumbnail_cache_dir: Optional[str] = None,
                       thumbnail_position_percent: int = 30,
                       n_frames: int = N_FRAMES,
                       ffmpeg_path: Optional[str] = None,
                       ffmpeg_timeout: int = 30) -> Dict:
    """
    Top-level worker: returns a dict on success or an error-tagged dict on
    failure. NEVER raises (per DECISION pattern A2 — image side gotchas).

    Success dict keys:
        error=False, file_path, video_hash, n_frames, duration, width, height,
        fps, frame_count, vcodec, container, filesize, mtime, thumbnail_path

    Error dict keys:
        error=True, file_path, error_type, error_msg

    error_type values come from FRAME_EXTRACT_ERROR_TYPES in frame_extractor.py.

    Path normalization: `file_path` is internally normalized to abspath. The
    returned dict's `file_path` is the abspath form. This keeps consumers from
    storing mixed relative/absolute paths (which break cleanup_missing_files).

    Threadsafe / multiprocess-safe: opens its own cv2 capture, no shared state.
    """
    import multiprocessing
    pid = os.getpid()
    worker_name = multiprocessing.current_process().name

    # Normalize to abspath up front (defense-in-depth — controller should already
    # do this, but workers may be called by tests/scripts that don't).
    file_path = os.path.abspath(file_path)
    fname = os.path.basename(file_path)

    print(f"[VHash Worker {worker_name} PID={pid}] START {fname}")

    try:
        if not os.path.isfile(file_path):
            return _err(file_path, 'cv2_open_failed', 'file not found')

        st = os.stat(file_path)
        filesize = st.st_size
        mtime = st.st_mtime

        # Probe metadata
        meta = probe_metadata(file_path)
        if meta is None:
            return _err(file_path, 'cv2_open_failed',
                        'cv2 could not open / read metadata')

        if meta['duration'] <= 0 or meta['frame_count'] <= 0:
            return _err(file_path, 'no_duration',
                        f"duration={meta['duration']} frame_count={meta['frame_count']}")

        # Compute sample points
        sample_points = compute_sample_points(meta['duration'], n_frames)
        if not sample_points:
            return _err(file_path, 'no_duration', 'compute_sample_points returned empty')

        # Extract frames (cv2 batch — opens once)
        frames = extract_frames_at_cv2_batch(file_path, sample_points)

        # Hash each frame; for failed frames try ffmpeg fallback once
        hashes: List[str] = []
        failed_frames = 0
        for t, frame in zip(sample_points, frames):
            if frame is None and ffmpeg_path:
                pil = extract_frame_at_ffmpeg_fallback(
                    file_path, t,
                    ffmpeg_path=ffmpeg_path,
                    timeout=ffmpeg_timeout,
                )
                if pil is not None:
                    hashes.append(str(imagehash.phash(pil, hash_size=8)))
                    continue
            if frame is None:
                hashes.append('0' * HEX_PER_FRAME)
                failed_frames += 1
                continue
            pil = bgr_to_pil(frame, target_width=THUMB_WIDTH)
            hashes.append(str(imagehash.phash(pil, hash_size=8)))

        if failed_frames == len(sample_points):
            return _err(file_path, 'all_frames_failed',
                        'every sample point failed to decode')

        video_hash = '|'.join(hashes)

        # Optional: thumbnail (generated synchronously per DECISION D-15 / Q-02 a)
        thumbnail_path: Optional[str] = None
        if thumbnail_cache_dir:
            try:
                os.makedirs(thumbnail_cache_dir, exist_ok=True)
                thumb_filename = thumbnail_filename_for(file_path)
                thumb_full = os.path.join(thumbnail_cache_dir, thumb_filename)
                if not os.path.isfile(thumb_full):
                    ok = extract_thumbnail(
                        file_path, thumb_full,
                        thumbnail_position_percent=thumbnail_position_percent,
                        width=THUMB_WIDTH,
                        ffmpeg_path=ffmpeg_path,
                        ffmpeg_timeout=ffmpeg_timeout,
                    )
                    if ok:
                        thumbnail_path = thumb_full
                else:
                    # Reuse existing thumbnail (file_path is keyed by md5)
                    thumbnail_path = thumb_full
            except Exception as e:
                # Thumbnail failure must not fail the whole compute
                print(f"[VHash Worker {worker_name}] thumbnail failed for {fname}: {e}")

        print(f"[VHash Worker {worker_name} PID={pid}] OK {fname} "
              f"hash={video_hash[:16]}... failed_frames={failed_frames}/{len(sample_points)}")

        return {
            'error': False,
            'file_path': file_path,
            'video_hash': video_hash,
            'n_frames': len(sample_points),
            'failed_frames': failed_frames,
            'duration': meta['duration'],
            'width': meta['width'],
            'height': meta['height'],
            'fps': meta['fps'],
            'frame_count': meta['frame_count'],
            'vcodec': meta['vcodec'],
            'container': meta['container'],
            'bitrate': meta.get('bitrate'),   # Q-06: filesize*8/duration estimate
            'filesize': filesize,
            'mtime': mtime,
            'thumbnail_path': thumbnail_path,
        }

    except Exception as e:
        # Catch-all per DECISION pattern A2
        print(f"[VHash Worker {worker_name} PID={pid}] EXCEPTION {fname}: {e}")
        return _err(file_path, 'unknown_error', str(e))


def _compute_video_hash_with_delay(args: Tuple) -> Dict:
    """
    Pool.imap_unordered-friendly wrapper: accepts a tuple so pickle is happy,
    applies `_COMPUTE_DELAY` before calling the real worker.

    args layout:
        (file_path, thumbnail_cache_dir, thumbnail_position_percent,
         n_frames, ffmpeg_path, ffmpeg_timeout)
    """
    if _COMPUTE_DELAY > 0:
        time.sleep(_COMPUTE_DELAY)
    file_path, thumb_dir, thumb_pct, n_frames, ffmpeg_path, ffmpeg_timeout = args
    return _compute_video_hash(
        file_path=file_path,
        thumbnail_cache_dir=thumb_dir,
        thumbnail_position_percent=thumb_pct,
        n_frames=n_frames,
        ffmpeg_path=ffmpeg_path,
        ffmpeg_timeout=ffmpeg_timeout,
    )


def _err(file_path: str, error_type: str, error_msg: str) -> Dict:
    """Build a standardized error result dict (never None, never raises)."""
    return {
        'error': True,
        'file_path': file_path,
        'error_type': error_type,
        'error_msg': error_msg,
    }


# ===========================================================================
# Phase 2 worker (top-level for multiprocessing pickling)
# ===========================================================================
#
# Pattern (mirrors image-version, see buffer/03_patterns_and_gotchas.md § A.7):
# the entire "all videos" snapshot is passed via Pool's `initializer` ONCE per
# worker process — not as a per-task arg. That avoids re-sending megabytes of
# (id, hash) tuples for every task. For 10k videos × 8×16-char hash each,
# the all-set is ~5 MB; passed once per worker (= num_workers transmissions
# total, vs N transmissions if it lived in args).
# ===========================================================================

# Per-process global: populated by _phase2_worker_init.
# Each Pool worker sees its OWN copy after spawn re-import. Reading from a
# global is faster than receiving via args every task.
_PHASE2_ALL_VIDEOS = None  # type: Optional[List[Tuple[int, str]]]
# Per-worker compare_delay (seconds, sleep BEFORE each per-video comparison).
# Set by _phase2_worker_init; sleeps inside the worker where it can actually
# throttle CPU. Setting compare_delay in the main-process prime loop only
# staggers submission — it does not throttle the workers themselves. (Tier-2
# review — Backend concurrency dimension.)
_PHASE2_COMPARE_DELAY = 0.0


def _phase2_worker_init(all_videos: List[Tuple[int, str]],
                        compare_delay: float = 0.0) -> None:
    """Pool initializer: stash the global snapshot in this worker process."""
    global _PHASE2_ALL_VIDEOS
    global _PHASE2_COMPARE_DELAY
    _PHASE2_ALL_VIDEOS = all_videos
    _PHASE2_COMPARE_DELAY = float(compare_delay or 0.0)
    import os
    import multiprocessing
    print(f"[Phase 2 Worker {multiprocessing.current_process().name} "
          f"PID={os.getpid()}] init: {len(all_videos)} videos in memory, "
          f"compare_delay={_PHASE2_COMPARE_DELAY}s")


def _compute_video_similarities_single(args) -> Tuple[int, List[Tuple[int, int, int]]]:
    """
    Compute similarities for ONE pending video against the worker-local
    snapshot `_PHASE2_ALL_VIDEOS`.

    args = (video_id, video_hash, threshold_distance)

    Returns: (video_id, similarities_list)
        where similarities_list is [(id_a, id_b, distance), ...] with
        id_a < id_b (canonical ordering matches video_similarities CHECK).

    Returns an empty list if no neighbors are within threshold. Self-pair
    (video_id == other_id) is always skipped.

    Never raises — distance failures are silently encoded as MAX_DISTANCE,
    which gets filtered out by the threshold_distance comparison.
    """
    video_id, video_hash, threshold_distance = args
    sims: List[Tuple[int, int, int]] = []

    if _PHASE2_ALL_VIDEOS is None:
        return (video_id, sims)  # defensive: initializer didn't run

    # Apply per-worker compare_delay before the pairwise loop so the setting
    # actually throttles worker CPU (Tier-2 review).
    if _PHASE2_COMPARE_DELAY > 0:
        time.sleep(_PHASE2_COMPARE_DELAY)

    # Inline a fast version of video_distance to avoid the function call
    # overhead inside the inner loop. Same semantics — see video_distance().
    my_frames = video_hash.split('|')
    n_my = len(my_frames)

    for other_id, other_hash in _PHASE2_ALL_VIDEOS:
        if other_id == video_id:
            continue

        other_frames = other_hash.split('|')
        if len(other_frames) != n_my:
            continue  # incomparable: different frame counts

        total = 0
        ok = True
        for fa, fb in zip(my_frames, other_frames):
            try:
                total += bin(int(fa, 16) ^ int(fb, 16)).count('1')
            except (ValueError, TypeError):
                ok = False
                break
        if not ok:
            continue

        if total <= threshold_distance:
            id_a, id_b = (video_id, other_id) if video_id < other_id else (other_id, video_id)
            sims.append((id_a, id_b, total))

    return (video_id, sims)


# ===========================================================================
# VideoHashCache
# ===========================================================================

class VideoHashCache:
    """
    DB-backed cache for video signatures + whitelist.

    Owns the SQLite schema. Workflow code (`video_workflow.py`) instantiates
    one per request and reuses the persistent connection.

    Critical patterns (mirroring image-version gotchas in
    `buffer/03_patterns_and_gotchas.md`):
      - `PRAGMA foreign_keys = ON` set on every connection
      - `check_same_thread=False` (Flask + SocketIO touches from multiple threads)
      - Persistent `_conn` reused; close() releases it
      - All batched `IN (?, ?, ...)` queries cap at 900 placeholders
    """

    BATCH_CAP = 900

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        # Ensure parent dir exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        # WAL mode + a per-instance lock let Flask/SocketIO threads share the
        # connection safely under check_same_thread=False (Tier-2 review).
        # The lock serializes multi-statement transactions; WAL avoids
        # reader/writer blocking; busy_timeout auto-retries on SQLITE_BUSY.
        self._conn_lock = threading.RLock()
        self._init_db()

    # ---- connection management ----

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            # CASCADE FK enforcement — see Decoupling Pattern B2 in gotchas doc
            self._conn.execute('PRAGMA foreign_keys = ON')
            # WAL + busy_timeout — see Tier-2 review D-23
            try:
                self._conn.execute('PRAGMA journal_mode = WAL')
                self._conn.execute('PRAGMA busy_timeout = 5000')
            except sqlite3.OperationalError as e:
                # WAL setup failing (e.g. read-only mount) is not fatal;
                # log and continue on default rollback journal.
                print(f"[VideoHashCache] WAL setup skipped: {e}")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ---- schema ----

    def _init_db(self) -> None:
        conn = self._get_connection()
        cur = conn.cursor()

        # video_hashes — main table. Mirrors image_hashes layout with video-
        # specific metadata columns.
        cur.execute('''
            CREATE TABLE IF NOT EXISTS video_hashes (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                filename        TEXT NOT NULL,
                filesize        INTEGER NOT NULL,
                file_path       TEXT NOT NULL,
                dir_path        TEXT,
                mtime           REAL,

                duration        REAL,
                width           INTEGER,
                height          INTEGER,
                fps             REAL,
                bitrate         INTEGER,
                vcodec          TEXT,
                acodec          TEXT,
                container       TEXT,

                video_hash      TEXT NOT NULL,
                n_frames        INTEGER NOT NULL DEFAULT 8,
                thumbnail_path  TEXT,

                status          TEXT NOT NULL DEFAULT 'pending',

                UNIQUE (filename, filesize, file_path)
            )
        ''')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_v_video_hash    ON video_hashes(video_hash)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_v_filename_size ON video_hashes(filename, filesize)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_v_status        ON video_hashes(status)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_v_dir_path      ON video_hashes(dir_path)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_v_mtime         ON video_hashes(mtime)')

        # video_similarities — edge list, CHECK a<b enforces canonical ordering
        cur.execute('''
            CREATE TABLE IF NOT EXISTS video_similarities (
                video_id_a  INTEGER NOT NULL,
                video_id_b  INTEGER NOT NULL,
                threshold   INTEGER NOT NULL,
                distance    INTEGER NOT NULL,
                PRIMARY KEY (video_id_a, video_id_b, threshold),
                CHECK (video_id_a < video_id_b),
                FOREIGN KEY (video_id_a) REFERENCES video_hashes(id) ON DELETE CASCADE,
                FOREIGN KEY (video_id_b) REFERENCES video_hashes(id) ON DELETE CASCADE
            )
        ''')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_vs_a_thr ON video_similarities(video_id_a, threshold)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_vs_b_thr ON video_similarities(video_id_b, threshold)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_vs_thr   ON video_similarities(threshold)')

        # Symmetric view — both directions in one query
        cur.execute('''
            CREATE VIEW IF NOT EXISTS video_similarities_view AS
            SELECT video_id_a AS video_id, video_id_b AS neighbor_id, threshold, distance
            FROM video_similarities
            UNION ALL
            SELECT video_id_b AS video_id, video_id_a AS neighbor_id, threshold, distance
            FROM video_similarities
        ''')

        # Phase 2.5 materialized output
        cur.execute('''
            CREATE TABLE IF NOT EXISTS duplicate_video_groups (
                group_id INTEGER NOT NULL,
                video_id INTEGER NOT NULL,
                PRIMARY KEY (group_id, video_id),
                FOREIGN KEY (video_id) REFERENCES video_hashes(id) ON DELETE CASCADE
            )
        ''')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_dvg_video_id ON duplicate_video_groups(video_id)')

        cur.execute('''
            CREATE TABLE IF NOT EXISTS video_group_stats (
                group_id                  INTEGER PRIMARY KEY,
                member_count              INTEGER NOT NULL,
                max_filesize              INTEGER,
                min_filesize              INTEGER,
                max_duration              REAL,
                min_duration              REAL,
                max_bitrate               INTEGER,
                min_bitrate               INTEGER,
                max_mtime                 REAL,
                min_mtime                 REAL,
                primary_folder            TEXT,
                folder_dup_count          INTEGER NOT NULL DEFAULT 0,
                representative_file_path  TEXT
            )
        ''')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_vgs_folder_dup_count ON video_group_stats(folder_dup_count)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_vgs_max_filesize     ON video_group_stats(max_filesize)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_vgs_max_duration     ON video_group_stats(max_duration)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_vgs_max_mtime        ON video_group_stats(max_mtime)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_vgs_member_count     ON video_group_stats(member_count)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_vgs_primary_folder   ON video_group_stats(primary_folder)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_vgs_rep_path         ON video_group_stats(representative_file_path)')

        # Whitelist tables
        cur.execute('''
            CREATE TABLE IF NOT EXISTS video_whitelist (
                video_id   INTEGER PRIMARY KEY,
                added_time REAL NOT NULL,
                note       TEXT,
                FOREIGN KEY (video_id) REFERENCES video_hashes(id) ON DELETE CASCADE
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS video_whitelist_groups (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                added_time REAL NOT NULL
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS video_whitelist_group_members (
                group_id INTEGER NOT NULL,
                video_id INTEGER NOT NULL,
                PRIMARY KEY (group_id, video_id),
                FOREIGN KEY (group_id) REFERENCES video_whitelist_groups(id) ON DELETE CASCADE,
                FOREIGN KEY (video_id) REFERENCES video_hashes(id) ON DELETE CASCADE
            )
        ''')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_vwgm_group ON video_whitelist_group_members(group_id)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_vwgm_video ON video_whitelist_group_members(video_id)')

        # Materialization meta (Phase 2.5 records threshold etc.)
        cur.execute('''
            CREATE TABLE IF NOT EXISTS video_duplicate_finder_meta (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        conn.commit()

    # ---- read API ----

    def get_hash(self, file_path: str) -> Optional[Dict]:
        """Return cached signature for a file IF the on-disk mtime+size match.

        Returns None if not cached, or if the file was modified since cache.
        Input is normalized to abspath (matches worker's storage normalization).
        """
        file_path = os.path.abspath(file_path)
        if not os.path.isfile(file_path):
            return None
        try:
            st = os.stat(file_path)
        except OSError:
            return None

        filename = os.path.basename(file_path)
        cur = self._get_connection().cursor()

        cur.execute(
            '''SELECT id, video_hash, mtime, duration, width, height, fps, vcodec, container,
                      n_frames, thumbnail_path, status
               FROM video_hashes
               WHERE filename = ? AND filesize = ? AND file_path = ?''',
            (filename, st.st_size, file_path),
        )
        row = cur.fetchone()
        if not row:
            return None

        (id_, video_hash, cached_mtime, duration, width, height, fps,
         vcodec, container, n_frames, thumb_path, status) = row

        if cached_mtime is None or abs(cached_mtime - st.st_mtime) > 0.001:
            return None

        return {
            'id': id_,
            'video_hash': video_hash,
            'duration': duration,
            'width': width,
            'height': height,
            'fps': fps,
            'vcodec': vcodec,
            'container': container,
            'n_frames': n_frames,
            'thumbnail_path': thumb_path,
            'status': status,
            'filesize': st.st_size,
            'mtime': st.st_mtime,
        }

    def get_all_cached_videos(self, file_exists_check: bool = True) -> List[Dict]:
        """Stream all cached video rows. Optionally drops rows whose file is
        missing or modified since cache."""
        cur = self._get_connection().cursor()
        cur.execute(
            '''SELECT id, file_path, video_hash, duration, width, height, fps,
                      vcodec, container, n_frames, thumbnail_path, filesize, mtime, status
               FROM video_hashes
               ORDER BY file_path'''
        )
        out: List[Dict] = []
        skipped_missing = 0
        for row in cur.fetchall():
            (id_, file_path, video_hash, duration, width, height, fps,
             vcodec, container, n_frames, thumb_path, filesize, mtime, status) = row
            if file_exists_check:
                if not os.path.isfile(file_path):
                    skipped_missing += 1
                    continue
                try:
                    st = os.stat(file_path)
                    if st.st_size != filesize or (mtime is not None and abs(st.st_mtime - mtime) > 0.001):
                        skipped_missing += 1
                        continue
                except OSError:
                    skipped_missing += 1
                    continue
            out.append({
                'id': id_,
                'file_path': file_path,
                'video_hash': video_hash,
                'duration': duration,
                'width': width,
                'height': height,
                'fps': fps,
                'vcodec': vcodec,
                'container': container,
                'n_frames': n_frames,
                'thumbnail_path': thumb_path,
                'filesize': filesize,
                'mtime': mtime,
                'status': status,
            })
        if skipped_missing:
            print(f"[VideoHashCache] get_all_cached_videos skipped {skipped_missing} missing/changed files")
        return out

    # ---- write API ----

    def set_hash(self, payload: Dict) -> int:
        """Insert or replace one row from a worker result dict. Returns row id."""
        self.set_hash_batch([payload])
        cur = self._get_connection().cursor()
        cur.execute(
            'SELECT id FROM video_hashes WHERE file_path = ?',
            (payload['file_path'],),
        )
        row = cur.fetchone()
        return int(row[0]) if row else -1

    def set_hash_batch(self, results: List[Dict]) -> None:
        """Bulk insert/replace. Skips entries flagged as errors."""
        if not results:
            return

        rows = []
        for r in results:
            if r.get('error'):
                continue
            file_path = r['file_path']
            filename = os.path.basename(file_path)
            dir_path = os.path.dirname(file_path)
            rows.append((
                filename,
                int(r.get('filesize', 0) or 0),
                file_path,
                dir_path,
                r.get('mtime'),
                r.get('duration'),
                r.get('width'),
                r.get('height'),
                r.get('fps'),
                r.get('bitrate'),
                r.get('vcodec'),
                r.get('acodec'),
                r.get('container'),
                r['video_hash'],
                int(r.get('n_frames', N_FRAMES)),
                r.get('thumbnail_path'),
                'pending',  # Phase 1 always writes 'pending'; Phase 2 marks computed
            ))

        if not rows:
            return

        conn = self._get_connection()
        cur = conn.cursor()
        cur.executemany(
            '''INSERT OR REPLACE INTO video_hashes
                 (filename, filesize, file_path, dir_path, mtime,
                  duration, width, height, fps, bitrate, vcodec, acodec, container,
                  video_hash, n_frames, thumbnail_path, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            rows,
        )
        conn.commit()

    # ---- whitelist ----

    def add_to_whitelist(self, video_id: int, note: Optional[str] = None) -> None:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            'INSERT OR REPLACE INTO video_whitelist (video_id, added_time, note) VALUES (?, ?, ?)',
            (video_id, time.time(), note),
        )
        conn.commit()

    def remove_from_whitelist(self, video_id: int) -> None:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute('DELETE FROM video_whitelist WHERE video_id = ?', (video_id,))
        conn.commit()

    def is_whitelisted(self, video_id: int) -> bool:
        cur = self._get_connection().cursor()
        cur.execute('SELECT 1 FROM video_whitelist WHERE video_id = ?', (video_id,))
        return cur.fetchone() is not None

    def get_whitelist(self) -> List[Dict]:
        cur = self._get_connection().cursor()
        cur.execute('''
            SELECT w.video_id, w.added_time, w.note, v.filename, v.filesize,
                   v.file_path, v.duration, v.width, v.height
            FROM video_whitelist w
            JOIN video_hashes v ON w.video_id = v.id
        ''')
        return [
            {
                'video_id': r[0], 'added_time': r[1], 'note': r[2],
                'filename': r[3], 'filesize': r[4], 'file_path': r[5],
                'duration': r[6], 'width': r[7], 'height': r[8],
            }
            for r in cur.fetchall()
        ]

    def add_group_to_whitelist(self, video_ids: List[int]) -> int:
        if not video_ids or len(video_ids) < 2:
            raise ValueError("Group must have at least 2 videos")
        conn = self._get_connection()
        cur = conn.cursor()
        # Atomic parent + members insert (Tier-2 review): if any member
        # insert fails, roll back so the orphaned parent row doesn't
        # linger for later commits.
        try:
            cur.execute('INSERT INTO video_whitelist_groups (added_time) VALUES (?)', (time.time(),))
            gid = cur.lastrowid
            for vid in video_ids:
                cur.execute(
                    'INSERT INTO video_whitelist_group_members (group_id, video_id) VALUES (?, ?)',
                    (gid, vid),
                )
            conn.commit()
            return gid
        except Exception:
            conn.rollback()
            raise

    def remove_whitelist_group(self, group_id: int) -> None:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute('DELETE FROM video_whitelist_groups WHERE id = ?', (group_id,))
        conn.commit()

    def is_group_whitelisted(self, video_ids: List[int]) -> bool:
        """True iff the given set of video_ids matches a whitelist group exactly."""
        if not video_ids or len(video_ids) < 2:
            return False
        cur = self._get_connection().cursor()
        cur.execute('''
            SELECT group_id, GROUP_CONCAT(video_id) AS members
            FROM video_whitelist_group_members
            GROUP BY group_id
        ''')
        target = set(video_ids)
        for _gid, members in cur.fetchall():
            try:
                ids = set(int(x) for x in members.split(','))
            except (ValueError, AttributeError):
                continue
            if ids == target:
                return True
        return False

    def get_whitelist_groups(self) -> List[Dict]:
        cur = self._get_connection().cursor()
        cur.execute('SELECT id, added_time FROM video_whitelist_groups ORDER BY added_time DESC')
        groups = cur.fetchall()
        out: List[Dict] = []
        for gid, added in groups:
            cur.execute('''
                SELECT m.video_id, v.filename, v.filesize, v.file_path,
                       v.duration, v.width, v.height
                FROM video_whitelist_group_members m
                JOIN video_hashes v ON m.video_id = v.id
                WHERE m.group_id = ?
            ''', (gid,))
            members = [
                {
                    'video_id': r[0], 'filename': r[1], 'filesize': r[2],
                    'file_path': r[3], 'duration': r[4],
                    'width': r[5], 'height': r[6],
                }
                for r in cur.fetchall()
            ]
            # Drop groups that decayed below 2 members (FK CASCADE removed some)
            if len(members) < 2:
                cur.execute('DELETE FROM video_whitelist_groups WHERE id = ?', (gid,))
                self._get_connection().commit()
                continue
            out.append({'group_id': gid, 'added_time': added, 'members': members})
        return out

    def cleanup_whitelist_groups(self) -> int:
        """Drop whitelist groups whose membership fell below 2. Returns count removed."""
        cur = self._get_connection().cursor()
        cur.execute('''
            SELECT group_id FROM video_whitelist_group_members
            GROUP BY group_id
            HAVING COUNT(*) < 2
        ''')
        bad = [r[0] for r in cur.fetchall()]
        if not bad:
            return 0
        # Batch the DELETE — SQLite's 999-variable cap. Tier-2 review B3.
        for i in range(0, len(bad), self.BATCH_CAP):
            chunk = bad[i:i + self.BATCH_CAP]
            ph = ','.join('?' * len(chunk))
            cur.execute(f'DELETE FROM video_whitelist_groups WHERE id IN ({ph})', chunk)
        self._get_connection().commit()
        return len(bad)

    # ---- maintenance ----

    def cleanup_missing_files(self,
                              existing_files: set,
                              scope_dir_paths: Optional[List[str]] = None) -> Tuple[int, int]:
        """
        Delete video_hashes rows for files no longer on disk.
        CASCADE drops associated similarities, group memberships, whitelist entries.

        SAFETY (Tier-1 fix):
            The caller MUST pass a snapshot of ALL video files under the
            scope they consider "authoritative". Any DB row NOT in the
            snapshot AND inside the scope is deleted.

            If `scope_dir_paths` is provided, the delete candidate set is
            RESTRICTED to rows whose dir_path lies inside one of those
            roots (with os.sep boundary check — never SQL LIKE, to avoid
            wildcard injection via '_' / '%' in user directory names).

            If `scope_dir_paths` is None, the caller is asserting they
            enumerated the ENTIRE filesystem. Any partial enumeration
            with `scope_dir_paths=None` will DELETE UNRELATED FOLDERS'
            ROWS. Prefer passing a scope.

        Returns:
            Tuple (removed_hashes_count, removed_whitelist_count).
            The whitelist count is always 0 because CASCADE handles it.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        if scope_dir_paths:
            cursor.execute('SELECT id, file_path, dir_path FROM video_hashes')
            all_rows = cursor.fetchall()
            scope_abs = [os.path.abspath(p).rstrip(os.sep) for p in scope_dir_paths if p]

            def _in_scope(dp):
                if not dp:
                    return False
                for sa in scope_abs:
                    if dp == sa or dp.startswith(sa + os.sep):
                        return True
                return False

            candidate_rows = [(rid, fp) for rid, fp, dp in all_rows if _in_scope(dp)]
            missing = [(rid, fp) for rid, fp in candidate_rows if fp not in existing_files]
            print(f"[VideoHashCache] cleanup_missing_files: SCOPED to "
                  f"{len(scope_dir_paths)} dirs — {len(candidate_rows)} candidates, "
                  f"{len(missing)} missing")
        else:
            cursor.execute('SELECT id, file_path FROM video_hashes')
            all_files = cursor.fetchall()
            missing = [(rid, fp) for rid, fp in all_files if fp not in existing_files]
            print(f"[VideoHashCache] cleanup_missing_files: GLOBAL — "
                  f"{len(all_files)} rows in DB, {len(missing)} missing")

        removed = 0
        for rid, _fp in missing:
            cursor.execute('DELETE FROM video_hashes WHERE id = ?', (rid,))
            removed += cursor.rowcount
        conn.commit()
        return (removed, 0)

    def verify_files_exist(self, file_paths: List[str]) -> Dict[str, List[str]]:
        """Split a path list into existing / missing."""
        existing: List[str] = []
        missing: List[str] = []
        for p in file_paths:
            (existing if os.path.isfile(p) else missing).append(p)
        return {'existing': existing, 'missing': missing}
