"""
Video Duplicate Finder — Workflow (Phase 1 / 2 / 2.5 / 3).

DECOUPLED: this module must not import from duplicate_finder.

Singleton lifecycle: see `video_duplicate_finder_controller.get_workflow()`.
The instance is created once per Flask process and must NEVER be rebuilt
mid-process (DECISION pattern E1 — preserves the stop event).
"""
import os
import time
from multiprocessing import Manager, Pool
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .settings_manager import settings_manager
from .video_hash_cache import (
    VIDEO_HASH_BITS,
    VideoHashCache,
    _compute_video_hash_with_delay,
    _compute_video_similarities_single,
    _phase2_worker_init,
    set_compute_delay,
)


class VideoDuplicateFinderWorkflow:
    """Owns the SQLite connection + cross-process stop event.

    The actual table creation runs inside `VideoHashCache._init_db()`; this
    class just keeps a reference and exposes Phase 1/2/2.5/3 entry points.
    """

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Ensure schema is up-to-date.
        self._cache = VideoHashCache(str(self.db_path))

        # Cross-process stop signal. Manager().Event() is process-safe and
        # survives Pool worker spawn (a plain threading.Event would not).
        # NEVER recreate this — see DECISION E1.
        self._manager = Manager()
        self._stop_event = self._manager.Event()

        print(f"[Video Workflow] __init__: db_path={self.db_path}")

    # ---- shared accessors ----

    def _get_connection(self):
        """Return the underlying SQLite connection (delegate to VideoHashCache)."""
        return self._cache._get_connection()

    # ---- stop signal ----

    def set_stop(self) -> None:
        """Signal all running phases to stop ASAP.

        Phases are expected to poll `self._stop_event.is_set()` between
        units of work. Once set, callers see `stopped: True` in the result
        dict and HTTP 200 (NOT 499 — that's reserved for the controller
        layer to map InterruptedError to)."""
        print("[Video Workflow] STOP signal SET")
        self._stop_event.set()

    def clear_stop(self) -> None:
        """Clear the stop event. Called at the start of every phase entry."""
        if self._stop_event.is_set():
            print("[Video Workflow] STOP signal CLEARED")
        self._stop_event.clear()

    # ========================================================================
    # Phase 1: Refresh videos
    # ========================================================================
    #
    # Mirrors image-version `phase1_refresh_images`. The apply_async throttling
    # pattern (max_pending = num_workers * 2) is COPIED verbatim from the
    # image version's documented design (see buffer/03_patterns_and_gotchas.md
    # § A.4) — same correctness/responsiveness guarantees apply.
    # ========================================================================

    def phase1_refresh_videos(self,
                              file_paths: List[str],
                              progress_callback: Optional[Callable] = None,
                              scope_dir_paths: Optional[List[str]] = None) -> Dict:
        """Phase 1: scan FS, sync DB, compute N-frame video signatures.

        Workflow:
          1. Delete `video_hashes` rows whose `file_path` is in DB but not in
             the provided list (= "files vanished from disk"). When
             `scope_dir_paths` is set, this delete is RESTRICTED to rows
             whose dir_path is inside that scope — critical for partial
             rescans that mustn't nuke other folders.
          2. Diff the input against DB: split into (skip if status='computed')
             and (compute if new or status='pending').
          3. Launch a Pool with throttled apply_async, processing tasks at
             max `num_workers * 2` in-flight. Each completed task is
             buffered, then flushed to DB in batches of `db_commit_batch_size`.

        Returns:
            {
              'added':   int,   # rows freshly inserted to video_hashes
              'removed': int,   # rows deleted from video_hashes
              'skipped': int,   # files already 'computed', not re-processed
              'errors':  list,  # worker error dicts (per-file)
              'elapsed': float,
              'stopped': bool,  # True if interrupted by self._stop_event
            }
        """
        self.clear_stop()
        start_time = time.time()
        conn = self._get_connection()
        cursor = conn.cursor()

        # ---- Load Phase 1 perf settings ----
        compute_delay = settings_manager.get_phase1_compute_delay()
        scan_delay = settings_manager.get_phase1_scan_delay()
        progress_interval = settings_manager.get_phase1_progress_update_interval()
        db_commit_batch_size = settings_manager.get_phase1_db_commit_batch_size()
        num_workers = settings_manager.get_max_cpu_cores()

        # Worker constants
        thumb_dir = settings_manager.get_thumbnail_cache_dir()
        thumb_pct = settings_manager.get_thumbnail_position_percent()
        n_frames = settings_manager.get_n_frames()
        ffmpeg_path = settings_manager.get_ffmpeg_path()
        ffmpeg_timeout = settings_manager.get_frame_extract_timeout_seconds()

        print(f"[Phase 1] START: {len(file_paths)} input paths, "
              f"workers={num_workers}, batch={db_commit_batch_size}, "
              f"compute_delay={compute_delay}s, scope={'limited' if scope_dir_paths else 'global'}")
        if len(file_paths) > 0:
            print(f"[Phase 1] DEBUG: first 3 input paths:")
            for p in file_paths[:3]:
                print(f"  - {p}")
        if scope_dir_paths:
            print(f"[Phase 1] DEBUG: scope_dir_paths:")
            for s in scope_dir_paths:
                print(f"  - {s}")
        print(f"[Phase 1] DEBUG: thumbnail_cache_dir={thumb_dir}")
        print(f"[Phase 1] DEBUG: thumb_position={thumb_pct}%, n_frames={n_frames}")
        print(f"[Phase 1] DEBUG: ffmpeg_path={ffmpeg_path}")

        # ----------------------------------------------------------------
        # Normalize: all incoming paths go through abspath. This matches
        # the worker's D-19 normalization, so the diff sets in Step 1/2
        # compare apples-to-apples with what the worker will store.
        # ----------------------------------------------------------------
        file_paths_abs = [os.path.abspath(p) for p in file_paths]
        total_files = len(file_paths_abs)
        print(f"[Phase 1] DEBUG: normalized {total_files} paths to abspath")

        # ----------------------------------------------------------------
        # Step 1: Remove DB rows whose file no longer exists on disk
        # ----------------------------------------------------------------
        if progress_callback:
            progress_callback(0, total_files, 'Checking missing files...')

        if scope_dir_paths:
            # Scope-limited: only delete within the targeted folders.
            # SQL LIKE has `_` and `%` wildcards; we CANNOT use LIKE with
            # user-supplied dir names (e.g. `C:\my_movies` matches
            # `C:\myXmovies` because `_` is a single-char wildcard).
            # Solution: pull ALL rows, then Python-filter the candidate
            # set using os.path prefix logic with an os.sep boundary.
            cursor.execute("SELECT id, file_path, dir_path FROM video_hashes")
            all_rows = cursor.fetchall()
            scope_abs = [os.path.abspath(f).rstrip(os.sep) for f in scope_dir_paths]

            def _in_scope(dp):
                if dp is None:
                    return False
                for sa in scope_abs:
                    if dp == sa or dp.startswith(sa + os.sep):
                        return True
                return False

            db_rows = [(rid, fp) for rid, fp, dp in all_rows if _in_scope(dp)]
            print(f"[Phase 1] Step 1 SCOPED: limited to {len(scope_dir_paths)} dir_path roots "
                  f"— {len(db_rows)} of {len(all_rows)} rows in scope")
        else:
            cursor.execute("SELECT id, file_path FROM video_hashes")
            db_rows = cursor.fetchall()
        db_path_set = {fp for _, fp in db_rows}
        fs_path_set = set(file_paths_abs)
        missing_paths = db_path_set - fs_path_set
        print(f"[Phase 1] DEBUG: db has {len(db_path_set)} paths, fs has {len(fs_path_set)}, "
              f"missing_from_fs = {len(missing_paths)}")

        removed_count = 0
        DELETE_COMMIT_THRESHOLD = 100
        for db_id, file_path in db_rows:
            if file_path in missing_paths:
                cursor.execute('DELETE FROM video_hashes WHERE id = ?', (db_id,))
                removed_count += 1
                if removed_count % DELETE_COMMIT_THRESHOLD == 0:
                    conn.commit()
                    print(f"[Phase 1] DEBUG: interim commit at {removed_count} deletes")
        conn.commit()
        print(f"[Phase 1] Step 1 DONE: removed {removed_count} missing files from DB")

        # ----------------------------------------------------------------
        # Step 2: Diff DB to find files needing compute
        # ----------------------------------------------------------------
        cursor.execute("SELECT file_path, status FROM video_hashes")
        db_status = {fp: status for fp, status in cursor.fetchall()}

        files_to_compute: List[str] = []
        skipped_count = 0
        checked_count = 0
        scan_stopped = False

        for fp in file_paths_abs:
            if self._stop_event.is_set():
                scan_stopped = True
                print(f"[Phase 1] Step 2: stop signal detected at {checked_count}/{total_files}")
                break

            if scan_delay > 0:
                time.sleep(scan_delay)

            status = db_status.get(fp)
            if status == 'computed':
                skipped_count += 1
            else:
                # status is None (new) or 'pending' (left over from prior partial run)
                files_to_compute.append(fp)

            checked_count += 1
            if progress_callback and (checked_count % progress_interval == 0
                                       or checked_count == total_files):
                progress_callback(
                    checked_count, total_files,
                    f"Checking files... ({checked_count}/{total_files})"
                )

        print(f"[Phase 1] Step 2 DONE: {skipped_count} already-computed, "
              f"{len(files_to_compute)} need compute (scan_stopped={scan_stopped})")
        if files_to_compute:
            print(f"[Phase 1] DEBUG: first 5 files to compute:")
            for fp in files_to_compute[:5]:
                print(f"  - {fp}")

        # ----------------------------------------------------------------
        # Step 3: Pool with apply_async throttling
        # ----------------------------------------------------------------
        added_count = 0
        error_files: List[Dict] = []
        compute_stopped = False

        if files_to_compute and not scan_stopped:
            # Each task tuple matches _compute_video_hash_with_delay's args:
            #   (file_path, thumbnail_cache_dir, thumbnail_position_percent,
            #    n_frames, ffmpeg_path, ffmpeg_timeout)
            def task_for(fp: str):
                return (fp, thumb_dir, thumb_pct, n_frames, ffmpeg_path, ffmpeg_timeout)

            n_tasks = len(files_to_compute)
            max_pending = max(2, num_workers * 2)

            print(f"[Phase 1] Step 3: Pool({num_workers}) processing {n_tasks} tasks, "
                  f"max_pending={max_pending}")

            with Pool(
                processes=num_workers,
                initializer=set_compute_delay,
                initargs=(compute_delay,),
            ) as pool:
                pending: List = []         # list of (AsyncResult, file_path)
                submitted_count = 0
                completed_count = 0
                batch_buffer: List[Dict] = []

                # Prime the pump
                for idx in range(min(max_pending, n_tasks)):
                    if self._stop_event.is_set():
                        compute_stopped = True
                        break
                    fp = files_to_compute[idx]
                    ar = pool.apply_async(_compute_video_hash_with_delay, (task_for(fp),))
                    pending.append((ar, fp))
                    submitted_count += 1

                while pending:
                    # Honor stop: stop SUBMITTING new tasks but drain pending.
                    if self._stop_event.is_set() and not compute_stopped:
                        print(f"[Phase 1] Step 3: STOP detected — "
                              f"submitted={submitted_count}, completed={completed_count}, "
                              f"in-flight={len(pending)}. Draining pending only.")
                        compute_stopped = True

                    progressed = False
                    for ar, fp in pending[:]:
                        if not ar.ready():
                            continue
                        try:
                            result = ar.get(timeout=0.1)
                            if not isinstance(result, dict):
                                result = {
                                    'error': True, 'file_path': fp,
                                    'error_type': 'unknown_error',
                                    'error_msg': f'non-dict result: {type(result).__name__}',
                                }
                            if result.get('error'):
                                error_files.append(result)
                            else:
                                batch_buffer.append(result)
                                if len(batch_buffer) >= db_commit_batch_size:
                                    added_count += self._insert_videos_batch(batch_buffer)
                                    batch_buffer = []
                            completed_count += 1
                            if progress_callback and (completed_count % progress_interval == 0
                                                       or completed_count == n_tasks):
                                progress_callback(
                                    completed_count, n_tasks,
                                    f"Hashing videos... ({completed_count}/{n_tasks})"
                                )
                        except Exception as e:
                            print(f"[Phase 1] Step 3: result fetch failed for {fp}: {e}")
                            error_files.append({
                                'error': True, 'file_path': fp,
                                'error_type': 'unknown_error',
                                'error_msg': f'AsyncResult.get raised: {e}',
                            })
                            completed_count += 1
                        finally:
                            pending.remove((ar, fp))
                            progressed = True

                            # Submit next task if not stopped and queue has more
                            if not compute_stopped and submitted_count < n_tasks:
                                next_fp = files_to_compute[submitted_count]
                                next_ar = pool.apply_async(
                                    _compute_video_hash_with_delay,
                                    (task_for(next_fp),),
                                )
                                pending.append((next_ar, next_fp))
                                submitted_count += 1
                            break  # restart pending scan

                    if not progressed and pending:
                        time.sleep(0.01)

                # Final flush
                if batch_buffer:
                    added_count += self._insert_videos_batch(batch_buffer)

            if compute_stopped:
                print(f"[Phase 1] Step 3 STOPPED: submitted={submitted_count}, "
                      f"completed={completed_count}, n_tasks={n_tasks}")
            else:
                print(f"[Phase 1] Step 3 DONE: completed {completed_count}/{n_tasks}, "
                      f"added {added_count}, errors {len(error_files)}")
        elif not files_to_compute:
            print("[Phase 1] Step 3: nothing to compute")

        # ----------------------------------------------------------------
        # Summary
        # ----------------------------------------------------------------
        any_stopped = scan_stopped or compute_stopped
        elapsed = time.time() - start_time

        if progress_callback:
            if any_stopped:
                progress_callback(
                    total_files, total_files,
                    f"Stopped: +{added_count}, -{removed_count}, skipped {skipped_count}"
                )
            else:
                progress_callback(
                    total_files, total_files,
                    f"Complete: +{added_count}, -{removed_count}, skipped {skipped_count}"
                )

        print(f"[Phase 1] {'STOPPED' if any_stopped else 'COMPLETE'} in {elapsed:.1f}s: "
              f"+{added_count}, -{removed_count}, skipped {skipped_count}, "
              f"errors {len(error_files)}")

        return {
            'added':   added_count,
            'removed': removed_count,
            'skipped': skipped_count,
            'errors':  error_files,
            'elapsed': elapsed,
            'stopped': any_stopped,
        }

    # ------------------------------------------------------------------
    # Phase 1 helper — INSERT OR IGNORE (NOT REPLACE!)
    # ------------------------------------------------------------------
    # Distinct from VideoHashCache.set_hash_batch (which uses OR REPLACE).
    # REPLACE on UNIQUE conflict drops + re-inserts, triggering CASCADE on
    # video_similarities — wiping any edges we computed previously. For
    # Phase 1 (which may re-run on the same folder), we want OR IGNORE so
    # existing rows are preserved untouched.
    # ------------------------------------------------------------------

    def _insert_videos_batch(self, batch: List[Dict]) -> int:
        """INSERT OR IGNORE batch into video_hashes. Returns the NUMBER OF
        ROWS ACTUALLY INSERTED (UNIQUE conflicts are skipped → not counted).

        Implementation note: `cursor.rowcount` after `executemany` is
        unreliable in Python's sqlite3 (historically reported -1 or
        cumulative-vs-last-statement depending on version). We use a
        COUNT(*) diff instead — rock-solid across all SQLite versions.

        Why this matters: re-running Phase 1 on the same folder will queue
        all 'pending' rows for re-hash (per design — they may have changed),
        but the INSERT OR IGNORE skips writing them back. Reporting the
        skipped batch as "added" would be misleading.
        """
        if not batch:
            return 0
        rows = []
        for r in batch:
            if r.get('error'):
                continue
            fp = r['file_path']  # already abspath per D-19
            rows.append((
                os.path.basename(fp),
                int(r.get('filesize', 0) or 0),
                fp,
                os.path.dirname(fp),
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
                int(r.get('n_frames', 8)),
                r.get('thumbnail_path'),
                'pending',
            ))
        if not rows:
            return 0
        conn = self._get_connection()
        cur = conn.cursor()

        # Count diff: snapshot BEFORE
        cur.execute('SELECT COUNT(*) FROM video_hashes')
        before_count = int(cur.fetchone()[0])

        cur.executemany(
            '''INSERT OR IGNORE INTO video_hashes
                 (filename, filesize, file_path, dir_path, mtime,
                  duration, width, height, fps, bitrate, vcodec, acodec, container,
                  video_hash, n_frames, thumbnail_path, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            rows,
        )
        conn.commit()

        cur.execute('SELECT COUNT(*) FROM video_hashes')
        after_count = int(cur.fetchone()[0])
        inserted = after_count - before_count
        skipped = len(rows) - inserted

        print(f"[Phase 1] _insert_videos_batch: tried {len(rows)}, "
              f"inserted {inserted}, IGNORE-skipped {skipped}")
        return inserted

    # ========================================================================
    # Phase 2 / 2.5 / 3 / Compare / Stats — placeholders (S3-S7)
    # ========================================================================

    # ========================================================================
    # Phase 2: build video_similarities
    # ========================================================================
    #
    # Mirrors image-version `phase2_build_similarities`. Apply_async throttling
    # is identical to Phase 1. The crucial difference is the WRITE-BEFORE-MARK
    # ordering (pattern A.6 in buffer/03_patterns_and_gotchas.md): we MUST
    # commit each task's similarity rows BEFORE updating its source video's
    # status to 'computed'. If we crashed after the UPDATE but before the
    # INSERT, the source row would appear "done" forever while its edges
    # were missing — Phase 2.5 would silently miss those duplicates.
    #
    # threshold semantics (mirrors image side, see 04_image_to_video_mapping.md §F.3):
    #   - This method's `threshold_distance` parameter sets the WIDTH of edges
    #     stored. Default is VIDEO_HASH_BITS * 0.2 = 102, which covers at
    #     least the "80% similarity" UI threshold.
    #   - The `threshold` column in video_similarities is the SCHEMA-fixed
    #     value 80 (constant per-row). Phase 2.5 filters at query time by
    #     `distance <= max_distance_for_ui_threshold`.
    #   - So Phase 2 stores broad-net coverage; UI threshold is applied
    #     downstream.
    # ========================================================================

    def phase2_build_similarities(self,
                                  threshold_distance: int = 102,
                                  progress_callback: Optional[Callable] = None) -> Dict:
        """Compute pairwise distances among videos, write `video_similarities`.

        Workflow:
          1. Snapshot all `status='pending'` rows (the work queue).
          2. Snapshot all rows (the comparison set — `_PHASE2_ALL_VIDEOS`).
          3. Spawn a Pool that gets the comparison set via initializer
             (one transmission per worker process).
          4. For each pending row, dispatch a task. Each task computes the
             frame-aligned hamming distance against every other video; rows
             with distance ≤ threshold_distance are kept.
          5. Per completed task: commit edges THEN update source row's
             status='computed' (in that order, see § A.6).

        Returns:
            {
              'processed':            int,   # rows transitioned to 'computed'
              'similarities_found':   int,   # edges actually inserted
              'elapsed':              float,
              'stopped':              bool,
            }
        """
        self.clear_stop()
        start_time = time.time()
        conn = self._get_connection()
        cursor = conn.cursor()

        # Load perf settings
        compare_delay = settings_manager.get_phase2_compare_delay()
        db_commit_batch_size = settings_manager.get_phase2_db_commit_batch_size()
        progress_interval = settings_manager.get_phase2_progress_update_interval()
        num_workers = settings_manager.get_max_cpu_cores()

        print(f"[Phase 2] START: threshold_distance ≤ {threshold_distance} "
              f"(of {VIDEO_HASH_BITS}), workers={num_workers}, "
              f"commit_batch={db_commit_batch_size}, compare_delay={compare_delay}s")
        print(f"[Phase 2] DEBUG: progress_interval={progress_interval}, max_pending={max(2, num_workers * 2)}")

        # ----------------------------------------------------------------
        # Step 1: snapshot pending work
        # ----------------------------------------------------------------
        cursor.execute("SELECT id, video_hash FROM video_hashes WHERE status = 'pending'")
        pending = cursor.fetchall()
        if not pending:
            elapsed = time.time() - start_time
            print(f"[Phase 2] No pending videos; nothing to do (elapsed {elapsed:.2f}s)")
            if progress_callback:
                progress_callback(0, 0, 'No pending videos')
            return {
                'processed': 0,
                'similarities_found': 0,
                'elapsed': elapsed,
                'stopped': False,
            }

        # ----------------------------------------------------------------
        # Step 2: snapshot full comparison set
        # ----------------------------------------------------------------
        cursor.execute("SELECT id, video_hash FROM video_hashes")
        all_videos = cursor.fetchall()
        n_pending = len(pending)
        n_total = len(all_videos)
        print(f"[Phase 2] Snapshot: pending={n_pending}, total={n_total}")
        # Warn if pending == 0 but total > 0 — this is the "nothing to do" case
        # but the user may be confused why Phase 2 completed instantly.
        if n_pending == 0 and n_total > 0:
            print(f"[Phase 2] DEBUG: all {n_total} videos already have status='computed' — nothing to recompute")

        # ----------------------------------------------------------------
        # Step 3: Pool with throttled apply_async
        # ----------------------------------------------------------------
        similarities_count = 0
        processed_count = 0
        stop_requested = False

        # SCHEMA threshold constant (see method docstring)
        SCHEMA_THRESHOLD = 80

        max_pending = max(2, num_workers * 2)

        with Pool(
            processes=num_workers,
            initializer=_phase2_worker_init,
            initargs=(all_videos, compare_delay),
        ) as pool:
            in_flight = []  # list of (AsyncResult, source_video_id)
            submitted = 0

            def submit(idx):
                vid, vhash = pending[idx]
                ar = pool.apply_async(
                    _compute_video_similarities_single,
                    ((vid, vhash, threshold_distance),),
                )
                in_flight.append((ar, vid))

            # Prime — no main-process sleep here (Tier-2 review): sleeping
            # in the driver only staggers submission, it does not throttle
            # worker CPU. compare_delay is applied inside the worker via
            # _phase2_worker_init.
            for i in range(min(max_pending, n_pending)):
                if self._stop_event.is_set():
                    stop_requested = True
                    break
                submit(i)
                submitted += 1

            while in_flight:
                if self._stop_event.is_set() and not stop_requested:
                    print(f"[Phase 2] STOP detected — submitted={submitted}, "
                          f"processed={processed_count}, in-flight={len(in_flight)}; "
                          f"draining remaining tasks")
                    stop_requested = True

                progressed = False
                for ar, src_id in in_flight[:]:
                    if not ar.ready():
                        continue
                    try:
                        result_src_id, sims_list = ar.get(timeout=0.1)
                    except Exception as e:
                        print(f"[Phase 2] result fetch failed for video_id={src_id}: {e}")
                        # Don't mark this source as computed — let next run retry.
                        in_flight.remove((ar, src_id))
                        progressed = True
                        if not stop_requested and submitted < n_pending:
                            submit(submitted); submitted += 1
                        break

                    # ⚠️ ORDER (gotcha A.6): commit edges FIRST, then mark status
                    # Wrap in try/except so a per-task DB failure doesn't
                    # tear down the whole Pool. On failure: rollback the
                    # pending write, record an error, and let the source
                    # stay 'pending' for a subsequent Phase 2 run.
                    try:
                        if sims_list:
                            rows = [(a, b, SCHEMA_THRESHOLD, d) for (a, b, d) in sims_list]
                            cursor.executemany(
                                '''INSERT OR REPLACE INTO video_similarities
                                     (video_id_a, video_id_b, threshold, distance)
                                   VALUES (?, ?, ?, ?)''',
                                rows,
                            )
                            conn.commit()
                            # Count uniquely-canonicalized edges only once.
                            # Both endpoints A and B canonicalize to the same
                            # (min,max) tuple, so we deduplicate here to
                            # keep `similarities_found` accurate (Tier-3
                            # review — fix for double-counting).
                            unique_edges = len({(a, b) for (a, b, _d) in sims_list
                                                if a > result_src_id or b > result_src_id})
                            similarities_count += unique_edges
                            print(f"[Phase 2] DEBUG: source_id={result_src_id} committed {len(rows)} rows "
                                  f"({unique_edges} unique-new edges, total_count={similarities_count})")

                        cursor.execute(
                            "UPDATE video_hashes SET status = 'computed' WHERE id = ?",
                            (result_src_id,),
                        )
                        conn.commit()
                        # Verbose per-task completion — helpful when the user
                        # runs the full pipeline manually and wants to see
                        # progress in the console.
                        if processed_count % 10 == 0 or processed_count < 20:
                            print(f"[Phase 2] DEBUG: task done source_id={result_src_id} "
                                  f"(processed={processed_count + 1}/{n_pending}, "
                                  f"in_flight={len(in_flight) - 1})")
                    except Exception as db_err:
                        # Roll back the pending transaction so partial state
                        # doesn't leak into subsequent commits on this
                        # shared connection.
                        try:
                            conn.rollback()
                        except Exception:
                            pass
                        print(f"[Phase 2] DB write failed for video_id={result_src_id}: {db_err}")
                        import traceback; traceback.print_exc()
                        # Do NOT mark this source computed — let next Phase 2 run retry.

                    processed_count += 1
                    if progress_callback and (processed_count % progress_interval == 0
                                               or processed_count == n_pending):
                        progress_callback(
                            processed_count, n_pending,
                            f"Pairwise compare... ({processed_count}/{n_pending}, "
                            f"{similarities_count} edges)"
                        )

                    in_flight.remove((ar, src_id))
                    progressed = True
                    if not stop_requested and submitted < n_pending:
                        submit(submitted); submitted += 1
                    break  # restart scan with fresh in_flight order

                if not progressed and in_flight:
                    time.sleep(0.01)

        elapsed = time.time() - start_time

        if progress_callback:
            if stop_requested:
                progress_callback(
                    processed_count, n_pending,
                    f"Stopped: processed {processed_count}/{n_pending}, "
                    f"{similarities_count} edges"
                )
            else:
                progress_callback(
                    n_pending, n_pending,
                    f"Complete: processed {processed_count}, {similarities_count} edges"
                )

        print(f"[Phase 2] {'STOPPED' if stop_requested else 'COMPLETE'} in {elapsed:.1f}s: "
              f"processed={processed_count}/{n_pending}, edges={similarities_count}")

        return {
            'processed': processed_count,
            'similarities_found': similarities_count,
            'elapsed': elapsed,
            'stopped': stop_requested,
        }

    # ========================================================================
    # Phase 2.5: materialize duplicate_video_groups + video_group_stats
    # ========================================================================
    #
    # Mirrors image-version `phase2_5_materialize_groups`. Five-step flow:
    #   1. SQL filter edges (UI threshold + per-video whitelist + optional same-folder)
    #   2. BFS over the edge list to find connected components → groups
    #   3. Drop groups that exactly match a `video_whitelist_groups` entry
    #   4. Rewrite duplicate_video_groups membership rows
    #   5. Compute video_group_stats (5a: SQL aggregates; 5b: per-group anchor)
    #
    # The anchor (Step 5b) is a SINGLE member per group whose folder has the
    # MOST duplicate files in the DB. Tie-break: smaller folder (curated), then
    # dir_path. The anchor's:
    #   - file_path → representative_file_path (which member shows as img1)
    #   - dir_path  → primary_folder
    #   - folder_dup[dir_path] → folder_dup_count (drives "hot folder" sort)
    # ========================================================================

    def phase2_5_materialize_groups(self,
                                    threshold_percent: int = 80,
                                    same_folder_filter: bool = True,
                                    progress_callback: Optional[Callable] = None) -> Dict:
        """Build duplicate_video_groups + video_group_stats from current edges."""
        import sqlite3 as _sqlite3   # only for OperationalError type

        self.clear_stop()
        start_time = time.time()
        conn = self._get_connection()
        cur = conn.cursor()

        max_distance = int(VIDEO_HASH_BITS * (100 - threshold_percent) / 100)

        def cb(pct: int, msg: str):
            if progress_callback:
                progress_callback(pct, 100, msg)

        def stopped() -> bool:
            if self._stop_event.is_set():
                print("[Phase 2.5] stop event detected; aborting")
                return True
            return False

        print("=" * 80)
        print(f"[Phase 2.5] START threshold={threshold_percent}% "
              f"(max_distance ≤ {max_distance} of {VIDEO_HASH_BITS}), "
              f"same_folder_filter={same_folder_filter}")
        print("=" * 80)

        # Pre-flight DB stats (mostly for debugging large datasets)
        try:
            n_videos = cur.execute("SELECT COUNT(*) FROM video_hashes").fetchone()[0]
            n_pending = cur.execute("SELECT COUNT(*) FROM video_hashes WHERE status='pending'").fetchone()[0]
            n_computed = cur.execute("SELECT COUNT(*) FROM video_hashes WHERE status='computed'").fetchone()[0]
            n_edges = cur.execute("SELECT COUNT(*) FROM video_similarities WHERE threshold=80").fetchone()[0]
            n_wl_individual = cur.execute("SELECT COUNT(*) FROM video_whitelist").fetchone()[0]
            n_wl_groups = cur.execute("SELECT COUNT(*) FROM video_whitelist_groups").fetchone()[0]
            print(f"[Phase 2.5] pre-flight: videos={n_videos} (pending={n_pending}, "
                  f"computed={n_computed}), edges={n_edges} (threshold=80), "
                  f"whitelist={n_wl_individual} videos / {n_wl_groups} groups")
            if n_pending > 0:
                print(f"[Phase 2.5] WARNING: {n_pending} videos still pending — "
                      f"Phase 2 may not have finished. Their edges are not in the table yet.")
        except Exception as e:
            print(f"[Phase 2.5] pre-flight stats failed (non-fatal): {e}")
            n_wl_groups = 0

        try:
            # ----------------------------------------------------------------
            # Step 1: SQL-filter edges
            # ----------------------------------------------------------------
            cb(0, "Step 1/5: filtering edges")
            same_folder_sql = "AND a.dir_path <> b.dir_path" if same_folder_filter else ""
            sql = f"""
                SELECT s.video_id_a, s.video_id_b, s.distance
                FROM video_similarities s
                JOIN video_hashes a ON s.video_id_a = a.id
                JOIN video_hashes b ON s.video_id_b = b.id
                LEFT JOIN video_whitelist wa ON wa.video_id = s.video_id_a
                LEFT JOIN video_whitelist wb ON wb.video_id = s.video_id_b
                WHERE s.threshold = 80
                  AND s.distance <= ?
                  AND wa.video_id IS NULL
                  AND wb.video_id IS NULL
                  {same_folder_sql}
            """
            t = time.time()
            cur.execute(sql, (max_distance,))
            edges = cur.fetchall()
            print(f"[Phase 2.5] Step 1 DONE: {len(edges)} edges in {time.time() - t:.2f}s")
            if stopped():
                return {'stopped': True, 'elapsed': time.time() - start_time}

            # ----------------------------------------------------------------
            # Step 2: BFS connected components
            # ----------------------------------------------------------------
            cb(20, "Step 2/5: building connected components")
            t = time.time()
            groups = self._build_groups(edges)
            if groups:
                sizes = [len(g) for g in groups]
                print(f"[Phase 2.5] Step 2 DONE: {len(groups)} groups "
                      f"(min={min(sizes)} max={max(sizes)} "
                      f"mean={sum(sizes)/len(sizes):.1f}) "
                      f"in {time.time() - t:.2f}s")
            else:
                print(f"[Phase 2.5] Step 2 DONE: 0 groups (no edges survived filter)")
            if stopped():
                return {'stopped': True, 'elapsed': time.time() - start_time}

            # ----------------------------------------------------------------
            # Step 3: drop fully-whitelisted groups
            # ----------------------------------------------------------------
            cb(40, "Step 3/5: filtering whitelisted groups")
            t = time.time()
            whitelisted_dropped = 0
            if n_wl_groups == 0:
                filtered_groups = groups
                print(f"[Phase 2.5] Step 3 SKIP: no whitelist groups to check")
            else:
                # Reuse the workflow-owned cache (Tier-2 review D-24):
                # opening a second VideoHashCache here would leak a
                # connection and trigger DDL churn on every materialize.
                filtered_groups = [g for g in groups if not self._cache.is_group_whitelisted(g)]
                whitelisted_dropped = len(groups) - len(filtered_groups)
                print(f"[Phase 2.5] Step 3 DONE: {len(filtered_groups)} groups remain, "
                      f"dropped {whitelisted_dropped} whitelisted "
                      f"in {time.time() - t:.2f}s")
            if stopped():
                return {'stopped': True, 'elapsed': time.time() - start_time}

            # ----------------------------------------------------------------
            # Step 4: rewrite duplicate_video_groups
            # ----------------------------------------------------------------
            cb(60, "Step 4/5: writing duplicate_video_groups")
            t = time.time()
            cur.execute("DELETE FROM video_group_stats")
            cur.execute("DELETE FROM duplicate_video_groups")

            dg_rows = []
            for group_id, member_ids in enumerate(filtered_groups, start=1):
                for video_id in member_ids:
                    dg_rows.append((group_id, video_id))
            if dg_rows:
                cur.executemany(
                    "INSERT INTO duplicate_video_groups (group_id, video_id) VALUES (?, ?)",
                    dg_rows,
                )
            print(f"[Phase 2.5] Step 4 DONE: wrote {len(dg_rows)} rows "
                  f"in {time.time() - t:.2f}s")
            if stopped():
                conn.rollback()
                print(f"[Phase 2.5] Stop detected after Step 4 — rolled back")
                return {'stopped': True, 'elapsed': time.time() - start_time}

            # ----------------------------------------------------------------
            # Step 5a: base aggregates (count, max/min filesize/duration/bitrate/mtime)
            # ----------------------------------------------------------------
            if stopped():
                conn.rollback()
                print("[Phase 2.5] Stop before Step 5a — rolled back")
                return {'stopped': True, 'elapsed': time.time() - start_time}
            cb(75, "Step 5/5: computing group_stats (5a base aggregates)")
            t = time.time()
            cur.execute('''
                INSERT INTO video_group_stats (
                    group_id, member_count,
                    max_filesize, min_filesize,
                    max_duration, min_duration,
                    max_bitrate, min_bitrate,
                    max_mtime, min_mtime
                )
                SELECT
                    dg.group_id,
                    COUNT(*),
                    MAX(v.filesize), MIN(v.filesize),
                    MAX(v.duration), MIN(v.duration),
                    MAX(v.bitrate), MIN(v.bitrate),
                    MAX(v.mtime), MIN(v.mtime)
                FROM duplicate_video_groups dg
                JOIN video_hashes v ON dg.video_id = v.id
                GROUP BY dg.group_id
            ''')
            n_gs = cur.execute("SELECT COUNT(*) FROM video_group_stats").fetchone()[0]
            print(f"[Phase 2.5] Step 5a DONE: {n_gs} group_stats rows "
                  f"in {time.time() - t:.2f}s")

            # ----------------------------------------------------------------
            # Step 5b: per-group anchor → representative_file_path + primary_folder + folder_dup_count
            # ----------------------------------------------------------------
            if stopped():
                conn.rollback()
                print("[Phase 2.5] Stop before Step 5b — rolled back")
                return {'stopped': True, 'elapsed': time.time() - start_time}
            cb(85, "Step 5/5: computing group_stats (5b anchor)")
            t = time.time()

            # 5b-i: total files per dir_path (used for display tie-break)
            cur.execute("SELECT dir_path, COUNT(*) FROM video_hashes "
                        "WHERE dir_path IS NOT NULL GROUP BY dir_path")
            folder_total: Dict[str, int] = {dp: cnt for dp, cnt in cur.fetchall()}

            # 5b-ii: duplicate files per dir_path (drives "hot folder" sort)
            cur.execute('''
                SELECT v.dir_path, COUNT(*)
                FROM duplicate_video_groups dg
                JOIN video_hashes v ON dg.video_id = v.id
                WHERE v.dir_path IS NOT NULL
                GROUP BY v.dir_path
            ''')
            folder_dup: Dict[str, int] = {dp: cnt for dp, cnt in cur.fetchall()}

            # 5b-iii: stream all members on TWO cursors (read while we'd write)
            # The image-version comment in phash_new_workflow.py explains why:
            # SQLite's sqlite3 driver doesn't let you execute on the same cursor
            # while iterating its results; a second cursor avoids the conflict.
            read_cur = conn.cursor()
            read_cur.execute('''
                SELECT dg.group_id, v.file_path, v.dir_path, v.filename
                FROM duplicate_video_groups dg
                JOIN video_hashes v ON dg.video_id = v.id
            ''')
            members_by_group: Dict[int, List[tuple]] = {}
            for gid, fp, dp, fn in read_cur:
                # tuple: (folder_total, folder_dup, filename, file_path, dir_path)
                members_by_group.setdefault(gid, []).append((
                    folder_total.get(dp, 0),
                    folder_dup.get(dp, 0),
                    fn or '',
                    fp,
                    dp,
                ))

            # 5b-iv: pick anchor per group — most-duplicates folder wins,
            # tie → smaller folder, then dir_path ASC, then filename ASC,
            # then file_path ASC. Filename + file_path tiebreakers make
            # the anchor DETERMINISTIC across reruns (Tier-2 review D-27).
            # tuple layout: (folder_total, folder_dup, filename, file_path, dir_path)
            updates = []
            for gid, members in members_by_group.items():
                anchor = min(members, key=lambda x: (-x[1], x[0], x[4], x[2], x[3]))
                fdc = folder_dup.get(anchor[4], 0)
                updates.append((anchor[3], anchor[4], fdc, gid))

            BATCH = 5000
            write_cur = conn.cursor()
            for i in range(0, len(updates), BATCH):
                write_cur.executemany(
                    '''UPDATE video_group_stats
                       SET representative_file_path = ?,
                           primary_folder = ?,
                           folder_dup_count = ?
                       WHERE group_id = ?''',
                    updates[i:i + BATCH],
                )
            print(f"[Phase 2.5] Step 5b DONE: anchored {len(updates)} groups "
                  f"in {time.time() - t:.2f}s")

            # ----------------------------------------------------------------
            # Step 6: write meta
            # ----------------------------------------------------------------
            now = time.time()
            cur.executemany(
                "INSERT OR REPLACE INTO video_duplicate_finder_meta (key, value) VALUES (?, ?)",
                [
                    ("materialized_threshold", str(threshold_percent)),
                    ("materialized_at", str(now)),
                    ("materialized_same_folder_filter", "1" if same_folder_filter else "0"),
                    ("materialized_group_count", str(len(filtered_groups))),
                ],
            )
            conn.commit()

            elapsed = time.time() - start_time
            cb(100, f"Complete: {len(filtered_groups)} groups")
            print("=" * 80)
            print(f"[Phase 2.5] COMPLETE in {elapsed:.2f}s: "
                  f"groups={len(filtered_groups)}, members={len(dg_rows)}, "
                  f"whitelisted_dropped={whitelisted_dropped}")
            print("=" * 80)

            return {
                'groups_count':         len(filtered_groups),
                'members_count':        len(dg_rows),
                'whitelisted_dropped':  whitelisted_dropped,
                'threshold_percent':    threshold_percent,
                'same_folder_filter':   same_folder_filter,
                'elapsed':              elapsed,
                'stopped':              False,
            }

        except Exception as e:
            conn.rollback()
            elapsed = time.time() - start_time
            print("=" * 80)
            print(f"[Phase 2.5] EXCEPTION after {elapsed:.2f}s: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            print("=" * 80)
            raise

    def get_materialization_meta(self) -> dict:
        """Read video_duplicate_finder_meta as a flat dict (key → value).

        Returns {} if the table doesn't exist (e.g. fresh DB before Phase 2.5).
        """
        import sqlite3 as _sqlite3
        cur = self._get_connection().cursor()
        try:
            cur.execute("SELECT key, value FROM video_duplicate_finder_meta")
            rows = cur.fetchall()
        except _sqlite3.OperationalError:
            return {}
        return {k: v for k, v in rows}

    def _build_groups(self, edges: List[tuple]) -> List[List[int]]:
        """BFS connected components from (id_a, id_b, distance) edge list.

        Returns list of member-id lists, each of length ≥ 2. Singletons
        (which shouldn't happen anyway, since edges are always pairs) are
        dropped.
        """
        graph: Dict[int, List[int]] = {}
        for a, b, _ in edges:
            graph.setdefault(a, []).append(b)
            graph.setdefault(b, []).append(a)

        visited: set = set()
        groups: List[List[int]] = []
        for node in graph:
            if node in visited:
                continue
            group: List[int] = []
            queue: List[int] = [node]
            visited.add(node)
            while queue:
                current = queue.pop(0)
                group.append(current)
                for nb in graph.get(current, ()):
                    if nb not in visited:
                        visited.add(nb)
                        queue.append(nb)
            if len(group) >= 2:
                groups.append(group)
        return groups

    # ========================================================================
    # Phase 3: paginated read of materialized groups
    # ========================================================================
    #
    # Mirrors image-version `phase3_get_duplicates`. Strict mode: if Phase 2.5
    # hasn't run, OR was run at a different threshold, returns a structured
    # error marker. Controller maps these to HTTP 409 so the UI can prompt
    # the user to re-run materialization.
    #
    # Video-specific additions:
    #   - sort whitelist extended with max/min_duration + max/min_bitrate
    #   - each member carries `auto_delete_suggestion: bool` from server-side
    #     rules (D-08 / D-14) — image-version frontend does this client-side,
    #     video version moves it server-side
    #   - member fields include duration/width/height/fps/bitrate/vcodec/acodec/
    #     container/thumbnail_path (not just file_path/phash like image)
    # ========================================================================

    # SQL-injection guard — only these columns can be ORDER BY'd
    PHASE3_ALLOWED_SORTS = {
        'representative_file_path',
        'folder_dup_count',
        'max_filesize', 'min_filesize',
        'max_duration', 'min_duration',   # video-specific
        'max_bitrate', 'min_bitrate',     # video-specific
        'max_mtime', 'min_mtime',
        'member_count',
    }

    # Codec ranking (newer/better first). Used by auto_mark_older_codec rule.
    _CODEC_RANK = {
        'av1':   4,
        'hevc':  3, 'h265': 3,
        'h264':  2, 'avc':  2,
        'mpeg4': 1, 'xvid': 1, 'divx': 1,
        'wmv':   0, 'rv40': 0, 'mp42': 0,
    }

    def phase3_get_duplicates(self,
                              threshold_percent: int = 80,
                              page: int = 1,
                              page_size: int = 100,
                              sort_by: str = 'folder_dup_count',
                              sort_order: str = 'desc',
                              folder_paths: Optional[List[str]] = None,
                              progress_callback: Optional[Callable] = None) -> Dict:
        """Paginated read of materialized duplicate_video_groups + video_group_stats.

        Strict mode: returns structured error marker if no materialization
        exists or threshold doesn't match. Controller maps to HTTP 409.

        Returns:
            {
              'groups':              [[member_dict, ...], ...],
              'total_groups':        int,
              'total_duplicates':    int,
              'total_files_in_db':   int,
              'current_page':        int,   # 1-indexed; 0 → return-all → 1
              'page_size':           int,
              'total_pages':         int,
              'elapsed':             float,
              'stopped':             False,
              'materialization_meta': {...},
              'sort_by':             str,
              'sort_order':          'asc'|'desc',
              'error':               'no_materialization' | 'threshold_mismatch'  (only on error)
            }
        """
        import math
        import os
        import sqlite3 as _sqlite3

        start_time = time.time()
        conn = self._get_connection()
        cur = conn.cursor()
        print(f"[Phase 3] START: threshold={threshold_percent}%, page={page}, "
              f"page_size={page_size}, sort_by={sort_by}, sort_order={sort_order}")

        # ----------------------------------------------------------------
        # 1. Strict materialization check
        # ----------------------------------------------------------------
        meta = self.get_materialization_meta()
        # Pre-compute total files (carried even on error paths so the UI
        # summary panel doesn't show 0 just because of a mismatch)
        try:
            _pre_total = int(cur.execute("SELECT COUNT(*) FROM video_hashes").fetchone()[0])
        except Exception:
            _pre_total = 0

        empty_page = {
            'groups':              [],
            'total_groups':        0,
            'total_duplicates':    0,
            'total_files_in_db':   _pre_total,
            'current_page':        page if page > 0 else 1,
            'page_size':           page_size,
            'total_pages':         0,
            'stopped':             False,
            'materialization_meta': meta,
        }

        if not meta or 'materialized_threshold' not in meta:
            return {
                **empty_page,
                'error':   'no_materialization',
                'message': 'No materialized groups. Please run Phase 2.5 first.',
                'elapsed': time.time() - start_time,
            }

        try:
            materialized_threshold = int(meta['materialized_threshold'])
        except (TypeError, ValueError):
            materialized_threshold = -1

        if materialized_threshold != threshold_percent:
            return {
                **empty_page,
                'error':   'threshold_mismatch',
                'message': (
                    f'Groups materialized at {materialized_threshold}%, '
                    f'but UI requests {threshold_percent}%. '
                    f'Re-run Phase 2.5 to refresh.'
                ),
                'materialized_threshold': materialized_threshold,
                'current_threshold':      threshold_percent,
                'elapsed': time.time() - start_time,
            }

        # ----------------------------------------------------------------
        # 2. Validate sort column (whitelist + on-disk schema check)
        # ----------------------------------------------------------------
        if sort_by not in self.PHASE3_ALLOWED_SORTS:
            sort_by = 'folder_dup_count'
        cur.execute("PRAGMA table_info(video_group_stats)")
        existing_cols = {row[1] for row in cur.fetchall()}
        if sort_by not in existing_cols:
            print(f"[Phase 3] WARNING: sort column {sort_by!r} missing from "
                  f"video_group_stats (have {sorted(existing_cols)}). "
                  f"Falling back to group_id.")
            sort_by = 'group_id'
        sort_order_sql = 'DESC' if str(sort_order).lower() == 'desc' else 'ASC'

        # Tiebreakers: stable within-bucket ordering
        tiebreakers = []
        if (sort_by != 'representative_file_path'
                and 'representative_file_path' in existing_cols):
            tiebreakers.append('representative_file_path ASC')
        if sort_by != 'group_id':
            tiebreakers.append('group_id ASC')
        tb_sql = (', ' + ', '.join(tiebreakers)) if tiebreakers else ''

        # ----------------------------------------------------------------
        # 3. Totals (counts before paging)
        # ----------------------------------------------------------------
        cur.execute("SELECT COUNT(*), COALESCE(SUM(member_count), 0) FROM video_group_stats")
        total_groups_all, total_duplicates = cur.fetchone()
        total_duplicates = int(total_duplicates)
        total_files_in_db = int(cur.execute("SELECT COUNT(*) FROM video_hashes").fetchone()[0])
        print(f"[Phase 3] DEBUG: total_groups={total_groups_all}, total_duplicates={total_duplicates}, "
              f"total_files_in_db={total_files_in_db}")

        if total_groups_all == 0:
            return {
                **empty_page,
                'total_groups':       0,
                'total_duplicates':   0,
                'total_files_in_db':  total_files_in_db,
                'total_pages':        0,
                'elapsed':            time.time() - start_time,
                'sort_by':            sort_by,
                'sort_order':         sort_order_sql.lower(),
            }

        # ----------------------------------------------------------------
        # 4. Page group_ids — all pagination in SQL
        # ----------------------------------------------------------------
        if page > 0:
            total_pages = max(1, math.ceil(total_groups_all / page_size)) if page_size > 0 else 1
            offset = max(0, (page - 1) * page_size)
            cur.execute(
                f"SELECT group_id FROM video_group_stats "
                f"ORDER BY {sort_by} {sort_order_sql}{tb_sql} "
                f"LIMIT ? OFFSET ?",
                (page_size, offset),
            )
        else:
            total_pages = 1
            cur.execute(
                f"SELECT group_id FROM video_group_stats "
                f"ORDER BY {sort_by} {sort_order_sql}{tb_sql}"
            )

        page_group_ids = [r[0] for r in cur.fetchall()]
        print(f"[Phase 3] DEBUG: paged {len(page_group_ids)} group_ids "
              f"(page {page}/{total_pages}, offset={(page - 1) * page_size if page > 0 else 0})")
        if not page_group_ids:
            return {
                **empty_page,
                'total_groups':       total_groups_all,
                'total_duplicates':   total_duplicates,
                'total_files_in_db':  total_files_in_db,
                'total_pages':        total_pages,
                'elapsed':            time.time() - start_time,
                'sort_by':            sort_by,
                'sort_order':         sort_order_sql.lower(),
            }

        # ----------------------------------------------------------------
        # 5. Bulk fetch members for THIS page only (one JOIN, batched)
        # ----------------------------------------------------------------
        videos_by_group: Dict[int, List[Dict]] = {gid: [] for gid in page_group_ids}
        batch_size = 900   # under SQLite's 999 variable cap
        for i in range(0, len(page_group_ids), batch_size):
            chunk = page_group_ids[i:i + batch_size]
            ph = ','.join('?' * len(chunk))
            cur.execute(
                f"SELECT dg.group_id, v.id, v.filename, v.filesize, v.file_path, "
                f"       v.video_hash, v.duration, v.width, v.height, v.fps, "
                f"       v.bitrate, v.vcodec, v.acodec, v.container, "
                f"       v.thumbnail_path, v.dir_path, v.mtime "
                f"FROM duplicate_video_groups dg "
                f"JOIN video_hashes v ON dg.video_id = v.id "
                f"WHERE dg.group_id IN ({ph})",
                chunk,
            )
            for row in cur.fetchall():
                (gid, vid, filename, filesize, fp, vh, dur, w, h, fps,
                 br, vc, ac, ct, thumb, dp, mt) = row
                videos_by_group[gid].append({
                    'id':              vid,
                    'filename':        filename,
                    'filesize':        filesize,
                    'file_path':       fp,
                    'video_hash':      vh,
                    'duration':        dur,
                    'width':           w,
                    'height':          h,
                    'fps':             fps,
                    'bitrate':         br,
                    'vcodec':          vc,
                    'acodec':          ac,
                    'container':       ct,
                    'thumbnail_path':  thumb,
                    'mtime':           mt,
                    '_dir_path':       dp,   # stripped before returning
                })

        # ----------------------------------------------------------------
        # 5b. Folder counts (folder_total + folder_dup_count) per dir_path
        # ----------------------------------------------------------------
        distinct_dirs: List[str] = []
        seen: set = set()
        for members in videos_by_group.values():
            for m in members:
                dp = m['_dir_path']
                if dp and dp not in seen:
                    seen.add(dp)
                    distinct_dirs.append(dp)

        folder_counts: Dict[str, int] = {}
        folder_dup_counts: Dict[str, int] = {}
        if distinct_dirs:
            for i in range(0, len(distinct_dirs), batch_size):
                chunk = distinct_dirs[i:i + batch_size]
                ph = ','.join('?' * len(chunk))
                cur.execute(
                    f"SELECT dir_path, COUNT(*) FROM video_hashes "
                    f"WHERE dir_path IN ({ph}) GROUP BY dir_path",
                    chunk,
                )
                for dp, cnt in cur.fetchall():
                    folder_counts[dp] = cnt
                cur.execute(
                    f"SELECT v.dir_path, COUNT(*) "
                    f"FROM duplicate_video_groups dg "
                    f"JOIN video_hashes v ON dg.video_id = v.id "
                    f"WHERE v.dir_path IN ({ph}) GROUP BY v.dir_path",
                    chunk,
                )
                for dp, cnt in cur.fetchall():
                    folder_dup_counts[dp] = cnt

        # ----------------------------------------------------------------
        # 5c. Sort members within each group + annotate folder_dup/total
        # ----------------------------------------------------------------
        for gid, members in videos_by_group.items():
            members.sort(key=lambda m: (
                -folder_dup_counts.get(m['_dir_path'], 0),    # biggest dup folder wins
                folder_counts.get(m['_dir_path'], 0),         # tie: smaller folder
                m.get('filename') or '',                       # tie: filename ASC
            ))
            for m in members:
                dp = m['_dir_path']
                m['folder_dup']   = int(folder_dup_counts.get(dp, 0))
                m['folder_total'] = int(folder_counts.get(dp, 0))
                m.pop('_dir_path', None)

        # ----------------------------------------------------------------
        # 6. display_path (project-root-relative)
        # ----------------------------------------------------------------
        folder_abs_list = []
        for folder in (folder_paths or []):
            if not folder:
                continue
            try:
                folder_abs_list.append(os.path.abspath(folder))
            except Exception:
                continue

        def compute_display_path(file_path: Optional[str]) -> str:
            if not file_path:
                return '/'
            try:
                fp_abs = os.path.abspath(file_path)
                for fa in folder_abs_list:
                    if fp_abs == fa or fp_abs.startswith(fa + os.sep):
                        rel = os.path.relpath(file_path, fa)
                        d = os.path.dirname(rel)
                        return d if d and d != '.' else '/'
            except Exception:
                pass
            return os.path.dirname(file_path)

        for members in videos_by_group.values():
            for m in members:
                m['display_path'] = compute_display_path(m['file_path'])

        # ----------------------------------------------------------------
        # 7. auto_delete_suggestion per member (D-14)
        # ----------------------------------------------------------------
        rules = settings_manager.get_auto_selection_rules()
        for gid, members in videos_by_group.items():
            suggested = self._compute_auto_delete_suggestions(members, rules)
            for m in members:
                m['auto_delete_suggestion'] = m['file_path'] in suggested

        # ----------------------------------------------------------------
        # 8. Assemble result preserving SQL-ordered group sequence
        # ----------------------------------------------------------------
        result_groups = [videos_by_group[gid] for gid in page_group_ids if videos_by_group[gid]]

        elapsed = time.time() - start_time
        print(f"[Phase 3] Page {page}/{total_pages}: {len(result_groups)} groups "
              f"in {elapsed * 1000:.0f}ms (sort_by={sort_by} {sort_order_sql})")
        print(f"[Phase 3] DEBUG: response members total = {sum(len(g) for g in result_groups)}, "
              f"auto_delete_marks = {sum(1 for g in result_groups for m in g if m.get('auto_delete_suggestion'))}")

        return {
            'groups':              result_groups,
            'total_groups':        total_groups_all,
            'total_duplicates':    total_duplicates,
            'total_files_in_db':   total_files_in_db,
            'current_page':        page if page > 0 else 1,
            'page_size':           page_size,
            'total_pages':         total_pages if page > 0 else 1,
            'elapsed':             elapsed,
            'stopped':             False,
            'materialization_meta': meta,
            'sort_by':             sort_by,
            'sort_order':          sort_order_sql.lower(),
        }

    # ------------------------------------------------------------------
    # Auto-delete-suggestion helper (D-08 / D-14)
    # ------------------------------------------------------------------

    def _compute_auto_delete_suggestions(self, group: List[Dict],
                                          rules: Dict) -> set:
        """Return a set of file_paths in `group` that auto-selection rules
        mark for deletion. Server-side; never client.

        Conservative semantics:
          - Each rule independently OR's into the set
          - Rules NEVER mark ALL members of a group (would leave nothing
            to keep). If a rule would empty the group, it's a no-op
            for that group.
        """
        import os
        import re

        to_delete: set = set()
        if not group or not rules:
            return to_delete

        all_paths = {m['file_path'] for m in group}

        def _apply(candidates: set):
            """Add to to_delete unless that would mark every group member."""
            if not candidates:
                return
            survivors = all_paths - to_delete - candidates
            if not survivors:
                return  # would empty the group → skip
            to_delete.update(candidates)

        # Rule 1: lower resolution
        if rules.get('auto_mark_lower_resolution'):
            pixels = [(m.get('width') or 0) * (m.get('height') or 0) for m in group]
            if pixels:
                max_p = max(pixels)
                cand = {m['file_path'] for m, p in zip(group, pixels) if p < max_p}
                _apply(cand)

        # Rule 2: lower bitrate within same resolution bucket
        if rules.get('auto_mark_lower_bitrate'):
            by_res: Dict = {}
            for m in group:
                by_res.setdefault((m.get('width'), m.get('height')), []).append(m)
            cand: set = set()
            for bucket in by_res.values():
                brs = [(m.get('bitrate') or 0) for m in bucket]
                max_br = max(brs) if brs else 0
                if max_br <= 0:
                    continue
                for m, br in zip(bucket, brs):
                    if br < max_br:
                        cand.add(m['file_path'])
            _apply(cand)

        # Rule 3: smaller filesize (intentionally OFF by default — see
        # default settings; a small file isn't necessarily worse)
        if rules.get('auto_mark_smaller_filesize'):
            sizes = [(m.get('filesize') or 0) for m in group]
            if sizes:
                max_s = max(sizes)
                cand = {m['file_path'] for m, s in zip(group, sizes) if s < max_s}
                _apply(cand)

        # Rule 4: older codec
        if rules.get('auto_mark_older_codec'):
            ranks = [self._CODEC_RANK.get((m.get('vcodec') or '').lower(), 0)
                     for m in group]
            if ranks:
                max_r = max(ranks)
                cand = {m['file_path'] for m, r in zip(group, ranks) if r < max_r}
                _apply(cand)

        # Rule 5: numbered copies / _copy / (1) / copy suffix
        if rules.get('auto_mark_numbered_copies'):
            copy_re = re.compile(
                r'(\(\d+\)$|\s\(\d+\)$|_copy$|-copy$|\s+copy$|\scopy$)',
                re.IGNORECASE,
            )
            cand = set()
            for m in group:
                stem = os.path.splitext(m.get('filename') or '')[0]
                if copy_re.search(stem):
                    cand.add(m['file_path'])
            _apply(cand)

        # Rule 6: prefer_folders — use path-prefix semantics (with os.sep
        # boundary + realpath normalization) so `C:\Media\Keep` doesn't
        # accidentally match `C:\Media\Keeper\...` (Tier-2 review D-26).
        prefer_folders = rules.get('prefer_folders') or []
        if prefer_folders:
            pref_abs: list = []
            for pref in prefer_folders:
                if not pref:
                    continue
                try:
                    pref_abs.append(os.path.realpath(pref).rstrip(os.sep))
                except Exception:
                    continue
            preferred: set = set()
            for m in group:
                fp = m['file_path']
                try:
                    fp_real = os.path.realpath(fp)
                except Exception:
                    fp_real = fp
                for pref in pref_abs:
                    if fp_real == pref or fp_real.startswith(pref + os.sep):
                        preferred.add(fp)
                        break
            if preferred:
                cand = {m['file_path'] for m in group
                        if m['file_path'] not in preferred}
                _apply(cand)

        return to_delete

    def compare_folders_focused(self,
                                 folders: List[str],
                                 threshold_distance: int = 102,
                                 progress_callback: Optional[Callable] = None) -> Dict:
        """Scoped pairwise comparison limited to the given folders.

        Contract (no global side-effects):
          - reads video_hashes rows whose dir_path is inside the scope
            (exact match OR any subdirectory)
          - walks the filesystem under each scope folder, respecting
            exclude_folder_paths
          - for files on disk that aren't yet in the DB: compute
            video_hash and INSERT a new row (status='computed')
          - for files in DB whose video_hash column happens to be
            NULL/empty: also compute and UPDATE (defensive)
          - pairwise compares EVERY video in scope (old + newly-inserted)
            and INSERT OR IGNORE the matching pairs into video_similarities
          - NEVER deletes any video_hashes row
          - NEVER touches scope-outside rows or scope-outside similarities

        Caller is expected to run phase2_5_materialize_groups afterwards
        to surface the new edges in Phase 3.

        Returns:
            {
              'folders':                   [abs paths],
              'fs_files':                  int,
              'scope_total':               int,
              'new_phashes_computed':      int,
              'errors':                    int,
              'pairs_found':               int,
              'new_similarities_inserted': int,
              'elapsed':                   float,
            }
        """
        import subprocess as _subprocess  # noqa
        from .video_hash_cache import _compute_video_hash, video_distance

        self.clear_stop()
        start = time.time()
        conn = self._get_connection()
        cur = conn.cursor()

        def cb(pct: int, msg: str):
            if progress_callback:
                progress_callback(pct, 100, msg)

        folders_abs = [os.path.abspath(f) for f in folders if f]
        if not folders_abs:
            print("[Compare Focused] No folders given")
            return {
                'folders': [],
                'fs_files': 0,
                'scope_total': 0,
                'new_phashes_computed': 0,
                'errors': 0,
                'pairs_found': 0,
                'new_similarities_inserted': 0,
                'elapsed': 0.0,
            }

        print("=" * 80)
        print(f"[Compare Focused] START — {len(folders_abs)} folder(s), distance ≤ {threshold_distance}")
        for f in folders_abs:
            print(f"   {f}")
        print("=" * 80)

        # ---- Step 1: read scoped DB rows (Python-side filter, NOT LIKE) ----
        # (Same Tier-1 fix as Phase 1: LIKE `_` wildcard would over-match
        # underscores in folder names like `C:\my_movies`.)
        cb(5, "Step 1/4: Reading scoped DB rows")
        cur.execute("SELECT id, file_path, video_hash, dir_path FROM video_hashes")
        all_db = cur.fetchall()

        scope_abs_rstrip = [f.rstrip(os.sep) for f in folders_abs]

        def _in_scope(dp):
            if not dp:
                return False
            for sa in scope_abs_rstrip:
                if dp == sa or dp.startswith(sa + os.sep):
                    return True
            return False

        db_by_path: Dict[str, Tuple[int, Optional[str]]] = {
            row[1]: (row[0], row[2]) for row in all_db if _in_scope(row[3])
        }
        print(f"[Compare Focused] Step 1: {len(db_by_path)} existing DB rows in scope "
              f"(of {len(all_db)} total)")

        # ---- Step 2: walk FS under each scope folder ----
        cb(10, "Step 2/4: Walking filesystem")
        exclude_paths = settings_manager.get_exclude_folder_paths() or []
        exclude_abs = [os.path.abspath(p) for p in exclude_paths if p]

        def is_excluded(p: str) -> bool:
            pa = os.path.abspath(p)
            for ex in exclude_abs:
                if pa == ex or pa.startswith(ex + os.sep):
                    return True
            return False

        # Project-wide video extensions — match controller VIDEO_EXTS.
        VIDEO_EXTS = ('.mp4', '.mkv', '.avi', '.mov', '.webm',
                      '.flv', '.wmv', '.m4v', '.ts', '.m2ts')
        fs_files: List[str] = []
        for folder in folders_abs:
            if not os.path.isdir(folder):
                print(f"[Compare Focused] WARNING: not a directory: {folder}")
                continue
            for root, dirs, files in os.walk(folder):
                if is_excluded(root):
                    dirs[:] = []
                    continue
                dirs[:] = [d for d in dirs if not is_excluded(os.path.join(root, d))]
                for fname in files:
                    if fname.lower().endswith(VIDEO_EXTS):
                        fs_files.append(os.path.abspath(os.path.join(root, fname)))
        print(f"[Compare Focused] Step 2: {len(fs_files)} files on disk in scope")

        # ---- Step 3: build scope_videos = (id, video_hash, file_path) ----
        cb(20, "Step 3/4: Resolving hashes for in-scope files")
        thumb_dir = settings_manager.get_thumbnail_cache_dir()
        thumb_pct = settings_manager.get_thumbnail_position_percent()
        n_frames = settings_manager.get_n_frames()
        ffmpeg_path = settings_manager.get_ffmpeg_path()
        ffmpeg_timeout = settings_manager.get_frame_extract_timeout_seconds()

        scope_videos: List[Tuple[int, str, str]] = []
        new_computed = 0
        errors = 0
        need_compute: List[str] = []
        need_hash_update: List[Tuple[int, str]] = []

        for fs_file in fs_files:
            existing = db_by_path.get(fs_file)
            if existing is not None:
                row_id, row_hash = existing
                if row_hash:
                    scope_videos.append((row_id, row_hash, fs_file))
                else:
                    need_hash_update.append((row_id, fs_file))
            else:
                need_compute.append(fs_file)

        print(f"[Compare Focused] Step 3: {len(scope_videos)} reused from DB, "
              f"{len(need_compute)} need compute (not in DB), "
              f"{len(need_hash_update)} need compute (DB hash missing)")

        # 3a: compute + INSERT for files not in DB (single-process — scope is
        # typically small; if performance matters, spawn a Pool here)
        for i, fs_file in enumerate(need_compute):
            if self._stop_event.is_set():
                print("[Compare Focused] STOP during Step 3a")
                break
            result = _compute_video_hash(
                fs_file,
                thumbnail_cache_dir=thumb_dir,
                thumbnail_position_percent=thumb_pct,
                n_frames=n_frames,
                ffmpeg_path=ffmpeg_path,
                ffmpeg_timeout=ffmpeg_timeout,
            )
            if result.get('error'):
                errors += 1
                print(f"[Compare Focused] hash error: {fs_file}: {result.get('error_msg')}")
                continue
            filename = os.path.basename(fs_file)
            dir_path = os.path.dirname(fs_file)
            cur.execute('''
                INSERT OR IGNORE INTO video_hashes
                (filename, filesize, file_path, dir_path, mtime,
                 duration, width, height, fps, bitrate, vcodec, acodec, container,
                 video_hash, n_frames, thumbnail_path, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'computed')
            ''', (
                filename, result.get('filesize', 0), fs_file, dir_path,
                result.get('mtime'), result.get('duration'), result.get('width'),
                result.get('height'), result.get('fps'), result.get('bitrate'),
                result.get('vcodec'), result.get('acodec'), result.get('container'),
                result['video_hash'], int(result.get('n_frames', 8)),
                result.get('thumbnail_path'),
            ))
            # Round-2 review: INSERT OR IGNORE can no-op if another writer
            # inserted a row for this path between the Step-1 snapshot and
            # here. In that case rowcount is 0, and we must use the DB's
            # stored hash (which might differ from our just-computed one)
            # for Step-4 comparisons — and NOT increment `new_computed`.
            inserted_now = (cur.rowcount == 1)
            cur.execute("SELECT id, video_hash FROM video_hashes WHERE file_path = ?", (fs_file,))
            row = cur.fetchone()
            if row:
                db_id, db_hash = row[0], row[1]
                # Use the DB's stored hash on IGNORE (may differ if the other
                # writer used different hash_size/n_frames/thumbnail_position);
                # use our fresh hash only when we actually inserted.
                hash_to_use = result['video_hash'] if inserted_now else (db_hash or result['video_hash'])
                scope_videos.append((db_id, hash_to_use, fs_file))
                if inserted_now:
                    new_computed += 1
            if (i + 1) % 25 == 0:
                cb(20 + int(30 * (i + 1) / max(1, len(need_compute))),
                   f"Step 3a: computing hash {i + 1}/{len(need_compute)}")

        # 3b: compute + UPDATE for in-DB rows with missing hash
        for i, (row_id, fs_file) in enumerate(need_hash_update):
            if self._stop_event.is_set():
                print("[Compare Focused] STOP during Step 3b")
                break
            result = _compute_video_hash(
                fs_file,
                thumbnail_cache_dir=thumb_dir,
                thumbnail_position_percent=thumb_pct,
                n_frames=n_frames,
                ffmpeg_path=ffmpeg_path,
                ffmpeg_timeout=ffmpeg_timeout,
            )
            if result.get('error'):
                errors += 1
                continue
            cur.execute('''
                UPDATE video_hashes
                SET video_hash = ?, duration = ?, width = ?, height = ?, fps = ?,
                    bitrate = ?, vcodec = ?, acodec = ?, container = ?,
                    filesize = ?, mtime = ?, thumbnail_path = ?,
                    status = 'computed'
                WHERE id = ?
            ''', (
                result['video_hash'], result.get('duration'), result.get('width'),
                result.get('height'), result.get('fps'), result.get('bitrate'),
                result.get('vcodec'), result.get('acodec'), result.get('container'),
                result.get('filesize', 0), result.get('mtime'),
                result.get('thumbnail_path'), row_id,
            ))
            scope_videos.append((row_id, result['video_hash'], fs_file))
            new_computed += 1

        if new_computed or errors:
            conn.commit()

        n = len(scope_videos)
        print(f"[Compare Focused] Step 3 DONE: scope = {n} videos "
              f"({new_computed} freshly computed, {errors} errors)")

        if n < 2:
            print("[Compare Focused] Less than 2 videos in scope — nothing to compare")
            return {
                'folders': folders_abs,
                'fs_files': len(fs_files),
                'scope_total': n,
                'new_phashes_computed': new_computed,
                'errors': errors,
                'pairs_found': 0,
                'new_similarities_inserted': 0,
                'elapsed': time.time() - start,
            }

        # ---- Step 4: pairwise compare WITHIN scope, INSERT OR IGNORE ----
        total_comparisons = n * (n - 1) // 2
        cb(60, f"Step 4/4: Pairwise compare ({total_comparisons} pairs)")
        print(f"[Compare Focused] Step 4: pairwise compare among {n} videos "
              f"({total_comparisons} distance computations)")

        pairs: List[Tuple[int, int, int, int]] = []
        SCHEMA_THRESHOLD = 80  # See Phase 2 note about the schema-fixed value

        for i in range(n):
            if self._stop_event.is_set():
                print("[Compare Focused] STOP during Step 4")
                break
            id_a, hash_a, _ = scope_videos[i]
            for j in range(i + 1, n):
                id_b, hash_b, _ = scope_videos[j]
                if id_a == id_b:
                    continue
                dist = video_distance(hash_a, hash_b)
                if dist <= threshold_distance:
                    if id_a < id_b:
                        pairs.append((id_a, id_b, SCHEMA_THRESHOLD, dist))
                    else:
                        pairs.append((id_b, id_a, SCHEMA_THRESHOLD, dist))

        print(f"[Compare Focused] Step 4: {len(pairs)} similar pair(s) within scope "
              f"(distance ≤ {threshold_distance})")

        # ---- Step 5: bulk INSERT OR IGNORE ----
        cb(90, "Inserting similarity edges")

        # COUNT-diff for the "new_similarities_inserted" metric
        cur.execute('SELECT COUNT(*) FROM video_similarities')
        before_count = int(cur.fetchone()[0])

        new_inserted = 0
        if pairs:
            BATCH = 5000
            for i in range(0, len(pairs), BATCH):
                chunk = pairs[i:i + BATCH]
                cur.executemany('''
                    INSERT OR IGNORE INTO video_similarities
                    (video_id_a, video_id_b, threshold, distance)
                    VALUES (?, ?, ?, ?)
                ''', chunk)
            conn.commit()
            cur.execute('SELECT COUNT(*) FROM video_similarities')
            after_count = int(cur.fetchone()[0])
            new_inserted = after_count - before_count
        print(f"[Compare Focused] Step 5: {new_inserted} new edges inserted "
              f"({len(pairs) - new_inserted} were already present)")

        elapsed = time.time() - start
        cb(100, f"Compare done — {new_inserted} new edges")
        print("=" * 80)
        print(f"[Compare Focused] COMPLETE in {elapsed:.2f}s")
        print("=" * 80)

        return {
            'folders': folders_abs,
            'fs_files': len(fs_files),
            'scope_total': n,
            'new_phashes_computed': new_computed,
            'errors': errors,
            'pairs_found': len(pairs),
            'new_similarities_inserted': new_inserted,
            'elapsed': elapsed,
        }

    # ========================================================================
    # Incremental stats repair (S7.4)
    # ========================================================================
    #
    # Mirrors image-version `stats_collect_affected_before_mutation` +
    # `stats_repair_after_mutation`. Two-call protocol:
    #
    #   1. BEFORE the mutation (delete / whitelist-add / replace), snapshot
    #      the groups + folders that will be affected.
    #   2. Do the actual mutation (DELETE FROM video_hashes, or whitelist
    #      INSERT, etc.). CASCADE handles dependent rows.
    #   3. AFTER the mutation, repair video_group_stats incrementally — only
    #      touching the groups/folders captured in step 1.
    #
    # Why incremental: re-running Phase 2.5 in full after every delete would
    # be wasteful on large libraries (re-aggregating ALL groups when only a
    # handful changed). The repair re-aggregates only the affected groups
    # and refreshes folder_dup_count only for the affected folders.
    # ========================================================================

    def stats_collect_affected_before_mutation(self,
                                                video_ids: List[int]) -> Dict:
        """Snapshot which groups + folders + old primary_folders will be
        affected by removing the given video_ids from the materialized view.

        Call BEFORE the actual delete/whitelist-add. Pass the result to
        `stats_repair_after_mutation` afterwards.

        Returns:
            {
              'video_ids':           [...],   # the ids being mutated
              'affected_groups':     [...],   # group_ids containing those videos
              'old_primary_folders': [...],   # primary_folder values for those groups BEFORE
              'affected_folders':    [...],   # dir_paths of the videos being mutated
            }
        """
        if not video_ids:
            return {
                'video_ids': [],
                'affected_groups': [],
                'old_primary_folders': [],
                'affected_folders': [],
            }

        cur = self._get_connection().cursor()
        affected_groups: set = set()
        affected_folders: set = set()

        BATCH = 900
        ids_list = list(video_ids)
        for i in range(0, len(ids_list), BATCH):
            chunk = ids_list[i:i + BATCH]
            ph = ','.join('?' * len(chunk))
            cur.execute(
                f"SELECT DISTINCT group_id FROM duplicate_video_groups "
                f"WHERE video_id IN ({ph})",
                chunk,
            )
            affected_groups.update(r[0] for r in cur.fetchall())

            cur.execute(
                f"SELECT DISTINCT dir_path FROM video_hashes "
                f"WHERE id IN ({ph}) AND dir_path IS NOT NULL",
                chunk,
            )
            affected_folders.update(r[0] for r in cur.fetchall())

        old_primary_folders: set = set()
        ag_list = list(affected_groups)
        for i in range(0, len(ag_list), BATCH):
            chunk = ag_list[i:i + BATCH]
            ph = ','.join('?' * len(chunk))
            cur.execute(
                f"SELECT DISTINCT primary_folder FROM video_group_stats "
                f"WHERE group_id IN ({ph}) AND primary_folder IS NOT NULL",
                chunk,
            )
            old_primary_folders.update(r[0] for r in cur.fetchall())

        print(f"[Stats Repair] CAPTURE: video_ids={len(ids_list)}, "
              f"affected_groups={len(affected_groups)}, "
              f"affected_folders={len(affected_folders)}, "
              f"old_primary_folders={len(old_primary_folders)}")

        return {
            'video_ids':           ids_list,
            'affected_groups':     list(affected_groups),
            'old_primary_folders': list(old_primary_folders),
            'affected_folders':    list(affected_folders),
        }

    def stats_repair_after_mutation(self,
                                     affected: Dict,
                                     remove_from_groups: bool = False) -> Dict:
        """Repair video_group_stats + duplicate_video_groups for the
        previously-captured `affected` state.

        Wrapped in try/except with rollback: multi-statement failure
        (constraint violation / DB locked / disk full) does NOT leave the
        shared connection with a half-executed transaction that would
        contaminate the next endpoint call. Tier-2 review.

        Args:
            affected: result of `stats_collect_affected_before_mutation`
            remove_from_groups: True for the whitelist case (video_hashes
                row STAYS — we must manually DELETE FROM duplicate_video_groups).
                False for the delete-file case (image_hashes row is gone,
                CASCADE already removed from duplicate_video_groups).

        Returns counts for caller logging.
        """
        start = time.time()
        conn = self._get_connection()
        try:
            return self._stats_repair_after_mutation_body(affected, remove_from_groups, start)
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            import traceback; traceback.print_exc()
            raise

    def _stats_repair_after_mutation_body(self,
                                           affected: Dict,
                                           remove_from_groups: bool,
                                           start: float) -> Dict:
        """Actual repair logic. Only called from `stats_repair_after_mutation`
        which handles rollback. Do not call directly."""
        cur = self._get_connection().cursor()

        video_ids           = affected.get('video_ids', [])
        affected_groups     = affected.get('affected_groups', [])
        old_primary_folders = affected.get('old_primary_folders', [])
        affected_folders    = affected.get('affected_folders', [])

        if not affected_groups:
            elapsed = time.time() - start
            print(f"[Stats Repair] No affected groups; nothing to do ({elapsed:.3f}s)")
            return {
                'video_ids_processed':     len(video_ids),
                'affected_groups':         0,
                'orphan_groups_deleted':   0,
                'survivor_groups_updated': 0,
                'folders_refreshed':       0,
                'elapsed':                 elapsed,
            }

        BATCH = 900

        # ------------------------------------------------------------------
        # Step A: whitelist mode → manually DELETE from duplicate_video_groups
        # ------------------------------------------------------------------
        # CASCADE doesn't fire here because the video_hashes row still exists
        # (we just whitelisted it). We must explicitly remove its memberships.
        if remove_from_groups and video_ids:
            removed_dvg = 0
            for i in range(0, len(video_ids), BATCH):
                chunk = video_ids[i:i + BATCH]
                ph = ','.join('?' * len(chunk))
                cur.execute(
                    f"DELETE FROM duplicate_video_groups WHERE video_id IN ({ph})",
                    chunk,
                )
                removed_dvg += cur.rowcount
            print(f"[Stats Repair] (whitelist) removed {removed_dvg} rows from duplicate_video_groups")

        # ------------------------------------------------------------------
        # Step B: classify affected groups into orphan (<2) vs survivor (≥2)
        # ------------------------------------------------------------------
        orphan_groups: set = set()
        survivor_groups: set = set()

        for i in range(0, len(affected_groups), BATCH):
            chunk = affected_groups[i:i + BATCH]
            ph = ','.join('?' * len(chunk))
            cur.execute(
                f"SELECT gs.group_id, COALESCE(dg.cnt, 0) "
                f"FROM video_group_stats gs "
                f"LEFT JOIN ("
                f"  SELECT group_id, COUNT(*) AS cnt FROM duplicate_video_groups "
                f"  WHERE group_id IN ({ph}) GROUP BY group_id"
                f") dg ON gs.group_id = dg.group_id "
                f"WHERE gs.group_id IN ({ph})",
                chunk + chunk,
            )
            for gid, cnt in cur.fetchall():
                if cnt < 2:
                    orphan_groups.add(gid)
                else:
                    survivor_groups.add(gid)

        # ------------------------------------------------------------------
        # Step C: delete orphan groups
        # ------------------------------------------------------------------
        if orphan_groups:
            ol = list(orphan_groups)
            for i in range(0, len(ol), BATCH):
                chunk = ol[i:i + BATCH]
                ph = ','.join('?' * len(chunk))
                cur.execute(f"DELETE FROM duplicate_video_groups WHERE group_id IN ({ph})", chunk)
                cur.execute(f"DELETE FROM video_group_stats WHERE group_id IN ({ph})", chunk)
            print(f"[Stats Repair] dropped {len(orphan_groups)} orphan groups (< 2 members)")

        # ------------------------------------------------------------------
        # Step D: re-aggregate survivor stats (member_count + max/min)
        # ------------------------------------------------------------------
        # Video-specific: also re-aggregate duration + bitrate min/max.
        if survivor_groups:
            sl = list(survivor_groups)
            for i in range(0, len(sl), BATCH):
                chunk = sl[i:i + BATCH]
                ph = ','.join('?' * len(chunk))
                cur.execute(f'''
                    UPDATE video_group_stats
                    SET member_count = (
                            SELECT COUNT(*) FROM duplicate_video_groups dg
                            WHERE dg.group_id = video_group_stats.group_id
                        ),
                        max_filesize = (
                            SELECT MAX(v.filesize) FROM duplicate_video_groups dg
                            JOIN video_hashes v ON dg.video_id = v.id
                            WHERE dg.group_id = video_group_stats.group_id
                        ),
                        min_filesize = (
                            SELECT MIN(v.filesize) FROM duplicate_video_groups dg
                            JOIN video_hashes v ON dg.video_id = v.id
                            WHERE dg.group_id = video_group_stats.group_id
                        ),
                        max_duration = (
                            SELECT MAX(v.duration) FROM duplicate_video_groups dg
                            JOIN video_hashes v ON dg.video_id = v.id
                            WHERE dg.group_id = video_group_stats.group_id
                        ),
                        min_duration = (
                            SELECT MIN(v.duration) FROM duplicate_video_groups dg
                            JOIN video_hashes v ON dg.video_id = v.id
                            WHERE dg.group_id = video_group_stats.group_id
                        ),
                        max_bitrate = (
                            SELECT MAX(v.bitrate) FROM duplicate_video_groups dg
                            JOIN video_hashes v ON dg.video_id = v.id
                            WHERE dg.group_id = video_group_stats.group_id
                        ),
                        min_bitrate = (
                            SELECT MIN(v.bitrate) FROM duplicate_video_groups dg
                            JOIN video_hashes v ON dg.video_id = v.id
                            WHERE dg.group_id = video_group_stats.group_id
                        ),
                        max_mtime = (
                            SELECT MAX(v.mtime) FROM duplicate_video_groups dg
                            JOIN video_hashes v ON dg.video_id = v.id
                            WHERE dg.group_id = video_group_stats.group_id
                        ),
                        min_mtime = (
                            SELECT MIN(v.mtime) FROM duplicate_video_groups dg
                            JOIN video_hashes v ON dg.video_id = v.id
                            WHERE dg.group_id = video_group_stats.group_id
                        )
                        -- primary_folder/representative_file_path/folder_dup_count
                        -- are refreshed in Step E below (anchor reselection).
                    WHERE group_id IN ({ph})
                ''', chunk)
            print(f"[Stats Repair] re-aggregated {len(survivor_groups)} survivor groups")

        # ------------------------------------------------------------------
        # Step E: refresh anchor for survivors (representative_file_path +
        #         primary_folder + folder_dup_count)
        # ------------------------------------------------------------------
        if survivor_groups:
            sl = list(survivor_groups)

            # E1: collect dir_paths of survivor members
            member_dirs: set = set()
            for i in range(0, len(sl), BATCH):
                chunk = sl[i:i + BATCH]
                ph = ','.join('?' * len(chunk))
                cur.execute(
                    f"SELECT DISTINCT v.dir_path FROM duplicate_video_groups dg "
                    f"JOIN video_hashes v ON dg.video_id = v.id "
                    f"WHERE dg.group_id IN ({ph}) AND v.dir_path IS NOT NULL",
                    chunk,
                )
                for (dp,) in cur.fetchall():
                    member_dirs.add(dp)

            # E2: counts per dir_path
            folder_total_repair: Dict[str, int] = {}
            folder_dup_repair:   Dict[str, int] = {}
            mdl = list(member_dirs)
            for i in range(0, len(mdl), BATCH):
                chunk = mdl[i:i + BATCH]
                ph = ','.join('?' * len(chunk))
                cur.execute(
                    f"SELECT dir_path, COUNT(*) FROM video_hashes "
                    f"WHERE dir_path IN ({ph}) GROUP BY dir_path",
                    chunk,
                )
                for dp, cnt in cur.fetchall():
                    folder_total_repair[dp] = cnt
                cur.execute(
                    f"SELECT v.dir_path, COUNT(*) "
                    f"FROM duplicate_video_groups dg JOIN video_hashes v ON dg.video_id = v.id "
                    f"WHERE v.dir_path IN ({ph}) GROUP BY v.dir_path",
                    chunk,
                )
                for dp, cnt in cur.fetchall():
                    folder_dup_repair[dp] = cnt

            # E3: per survivor group, pick anchor (same key as Phase 2.5)
            anchor_updates = []
            for i in range(0, len(sl), BATCH):
                chunk = sl[i:i + BATCH]
                ph = ','.join('?' * len(chunk))
                cur.execute(
                    f"SELECT dg.group_id, v.file_path, v.dir_path, v.filename "
                    f"FROM duplicate_video_groups dg "
                    f"JOIN video_hashes v ON dg.video_id = v.id "
                    f"WHERE dg.group_id IN ({ph})",
                    chunk,
                )
                members_by_group: Dict[int, list] = {}
                for gid, fp, dp, fn in cur.fetchall():
                    members_by_group.setdefault(gid, []).append((
                        folder_total_repair.get(dp, 0),
                        folder_dup_repair.get(dp, 0),
                        fn or '',
                        fp,
                        dp,
                    ))
                for gid, members in members_by_group.items():
                    # Single anchor: biggest dup folder wins, ties → smaller
                    # folder, dir_path, filename, file_path — deterministic
                    # across reruns (Tier-2 review D-27). Same key as
                    # Phase 2.5 Step 5b.
                    anchor = min(members, key=lambda x: (-x[1], x[0], x[4], x[2], x[3]))
                    fdc = folder_dup_repair.get(anchor[4], 0)
                    anchor_updates.append((anchor[3], anchor[4], fdc, gid))

            if anchor_updates:
                for i in range(0, len(anchor_updates), BATCH):
                    cur.executemany(
                        "UPDATE video_group_stats "
                        "SET representative_file_path = ?, primary_folder = ?, folder_dup_count = ? "
                        "WHERE group_id = ?",
                        anchor_updates[i:i + BATCH],
                    )
                print(f"[Stats Repair] refreshed anchor (rep_path/primary_folder/folder_dup_count) "
                      f"for {len(anchor_updates)} groups")

        # ------------------------------------------------------------------
        # Step F: refresh folder_dup_count for OTHER groups whose
        #          primary_folder is one of the affected folders
        # ------------------------------------------------------------------
        # When a group's anchor doesn't move but the folder's overall dup-count
        # changed (because some other group's member in that folder vanished),
        # those groups' folder_dup_count needs to be refreshed too.
        new_primary_folders: set = set()
        if survivor_groups:
            for i in range(0, len(survivor_groups), BATCH):
                chunk = list(survivor_groups)[i:i + BATCH]
                ph = ','.join('?' * len(chunk))
                cur.execute(
                    f"SELECT DISTINCT primary_folder FROM video_group_stats "
                    f"WHERE group_id IN ({ph}) AND primary_folder IS NOT NULL",
                    chunk,
                )
                new_primary_folders.update(r[0] for r in cur.fetchall())

        folders_to_refresh = set(affected_folders) | set(old_primary_folders) | new_primary_folders
        if folders_to_refresh:
            ftr = list(folders_to_refresh)
            for i in range(0, len(ftr), BATCH):
                chunk = ftr[i:i + BATCH]
                ph = ','.join('?' * len(chunk))
                cur.execute(f'''
                    UPDATE video_group_stats
                    SET folder_dup_count = (
                        SELECT COUNT(*)
                        FROM duplicate_video_groups dg2
                        JOIN video_hashes v2 ON dg2.video_id = v2.id
                        WHERE v2.dir_path = video_group_stats.primary_folder
                    )
                    WHERE primary_folder IN ({ph})
                ''', chunk)
            print(f"[Stats Repair] refreshed folder_dup_count for {len(folders_to_refresh)} folders")

        # Meta: bump last_incremental_update timestamp
        cur.execute(
            "INSERT OR REPLACE INTO video_duplicate_finder_meta (key, value) VALUES (?, ?)",
            ("last_incremental_update", str(time.time())),
        )
        self._get_connection().commit()

        elapsed = time.time() - start
        result = {
            'video_ids_processed':     len(video_ids),
            'affected_groups':         len(affected_groups),
            'orphan_groups_deleted':   len(orphan_groups),
            'survivor_groups_updated': len(survivor_groups),
            'folders_refreshed':       len(folders_to_refresh),
            'elapsed':                 elapsed,
        }
        print(f"[Stats Repair] DONE in {elapsed:.3f}s: {result}")
        return result
