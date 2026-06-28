"""
New 3-phase workflow for duplicate finder (DATABASE_SCHEMA.md)

Phase 1: Refresh images - Scan filesystem, sync DB, compute phash
Phase 2: Build similarities - Compute distances, populate phash_similarities
Phase 3: Get duplicates - Generate duplicate groups from similarities
"""
import sqlite3
import os
import time
from pathlib import Path
from typing import List, Dict, Optional, Callable, Tuple
from multiprocessing import Pool, cpu_count, Manager

try:
    from .phash_cache import _compute_single_hash_with_delay, get_default_cache_path, set_compute_delay, PHashCache
except ImportError:
    from phash_cache import _compute_single_hash_with_delay, get_default_cache_path, set_compute_delay, PHashCache

# Global variables for performance settings (accessible by multiprocessing workers)
_SCAN_DELAY = 0.0
_COMPARE_DELAY = 0.0


def set_performance_delays(scan_delay: float = 0.0, compare_delay: float = 0.0):
    """Set global performance delays for multiprocessing workers"""
    global _SCAN_DELAY, _COMPARE_DELAY
    _SCAN_DELAY = scan_delay
    _COMPARE_DELAY = compare_delay


def _compute_similarities_batch(args):
    """
    Compute similarities for a batch of pending images.
    This function is used by multiprocessing.

    Args:
        args: tuple of (pending_batch, all_images, threshold_distance, compare_delay)

    Returns:
        List of similarity tuples: (id_a, id_b, distance)
    """
    import os
    import time
    import multiprocessing

    pending_batch, all_images, threshold_distance, compare_delay = args
    similarities = []

    pid = os.getpid()
    worker_name = multiprocessing.current_process().name

    print(f"[Worker {worker_name} PID={pid}] START batch: {len(pending_batch)} pending vs {len(all_images)} total images")

    def hamming_distance(hash1: str, hash2: str) -> int:
        return bin(int(hash1, 16) ^ int(hash2, 16)).count('1')

    processed = 0
    for pending_id, pending_phash in pending_batch:
        # Apply compare delay once per pending image (not per comparison)
        if compare_delay > 0:
            time.sleep(compare_delay)

        matches = 0
        for other_id, other_phash in all_images:
            if pending_id == other_id:
                continue

            distance = hamming_distance(pending_phash, other_phash)
            if distance <= threshold_distance:
                # Ensure id_a < id_b
                id_a, id_b = (pending_id, other_id) if pending_id < other_id else (other_id, pending_id)
                similarities.append((id_a, id_b, distance))
                matches += 1

        processed += 1
        if processed % 10 == 0 or processed == len(pending_batch):
            print(f"[Worker {worker_name} PID={pid}] Progress: {processed}/{len(pending_batch)} images, found {len(similarities)} similarities so far")

    print(f"[Worker {worker_name} PID={pid}] DONE batch: processed {len(pending_batch)} images, found {len(similarities)} total similarities")

    return similarities


# ========== Phase 2 Single Image Worker (New Architecture) ==========

# Global variable to store all_images in each worker process
_PHASE2_ALL_IMAGES = None


def _phase2_worker_init(all_images):
    """
    Worker process initializer for Phase 2.
    Called once per worker process at startup.
    Stores all_images in global variable to avoid repeated transmission.

    Args:
        all_images: List of (id, phash) tuples for all images in database
    """
    global _PHASE2_ALL_IMAGES
    _PHASE2_ALL_IMAGES = all_images

    import os
    import multiprocessing
    pid = os.getpid()
    worker_name = multiprocessing.current_process().name
    print(f"[Worker {worker_name} PID={pid}] Phase 2 initialized with {len(all_images)} images in memory")


def _compute_similarities_single(args):
    """
    Compute similarities for a SINGLE pending image vs all images.
    Uses global _PHASE2_ALL_IMAGES initialized once per worker.

    Args:
        args: tuple of (img_id, img_phash, threshold_distance, compare_delay)

    Returns:
        Tuple of (img_id, similarities_list) where similarities_list contains (id_a, id_b, distance) tuples
    """
    global _PHASE2_ALL_IMAGES
    img_id, img_phash, threshold_distance, compare_delay = args

    def hamming_distance(hash1: str, hash2: str) -> int:
        return bin(int(hash1, 16) ^ int(hash2, 16)).count('1')

    similarities = []

    # Apply compare delay once per image (before processing)
    if compare_delay > 0:
        import time
        time.sleep(compare_delay)

    # Compare with all images
    for other_id, other_phash in _PHASE2_ALL_IMAGES:
        if img_id == other_id:
            continue

        distance = hamming_distance(img_phash, other_phash)
        if distance <= threshold_distance:
            # Ensure id_a < id_b
            id_a, id_b = (img_id, other_id) if img_id < other_id else (other_id, img_id)
            similarities.append((id_a, id_b, distance))

    return (img_id, similarities)


class DuplicateFinderWorkflow:
    """
    New workflow manager for duplicate finder.
    Implements 3-phase process with stop control.
    """

    def __init__(self, db_path: str = None):
        if db_path:
            self.db_path = Path(db_path)
        else:
            self.db_path = get_default_cache_path()

        print(f"[Workflow] Using database: {self.db_path}")
        self._conn = None
        # Use multiprocessing Manager for cross-process Event
        self._manager = Manager()
        self._stop_event = self._manager.Event()
        self._init_db()

    def _init_db(self):
        """Initialize database tables if needed"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Create tables
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS image_hashes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                filesize INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                phash TEXT NOT NULL,
                resolution TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                dir_path TEXT,
                mtime REAL,
                UNIQUE (filename, filesize, file_path)
            )
        ''')

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_phash ON image_hashes(phash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_filename_filesize ON image_hashes(filename, filesize)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_status ON image_hashes(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_dir_path ON image_hashes(dir_path)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_mtime ON image_hashes(mtime)')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS whitelist (
                image_id INTEGER PRIMARY KEY,
                added_time REAL NOT NULL,
                note TEXT,
                FOREIGN KEY (image_id) REFERENCES image_hashes(id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS phash_similarities (
                image_id_a INTEGER NOT NULL,
                image_id_b INTEGER NOT NULL,
                threshold INTEGER NOT NULL,
                distance INTEGER NOT NULL,
                PRIMARY KEY (image_id_a, image_id_b, threshold),
                CHECK (image_id_a < image_id_b),
                FOREIGN KEY (image_id_a) REFERENCES image_hashes(id) ON DELETE CASCADE,
                FOREIGN KEY (image_id_b) REFERENCES image_hashes(id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_image_id_a_threshold ON phash_similarities(image_id_a, threshold)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_image_id_b_threshold ON phash_similarities(image_id_b, threshold)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_threshold ON phash_similarities(threshold)')

        # Materialized groups (Phase 2.5 output)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS duplicate_groups (
                group_id INTEGER NOT NULL,
                image_id INTEGER NOT NULL,
                PRIMARY KEY (group_id, image_id),
                FOREIGN KEY (image_id) REFERENCES image_hashes(id) ON DELETE CASCADE
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_dg_image_id ON duplicate_groups(image_id)')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS group_stats (
                group_id INTEGER PRIMARY KEY,
                member_count INTEGER NOT NULL,
                max_filesize INTEGER,
                min_filesize INTEGER,
                max_mtime REAL,
                min_mtime REAL,
                primary_folder TEXT,
                folder_dup_count INTEGER NOT NULL DEFAULT 0
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_gs_folder_dup_count ON group_stats(folder_dup_count)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_gs_max_filesize ON group_stats(max_filesize)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_gs_max_mtime ON group_stats(max_mtime)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_gs_member_count ON group_stats(member_count)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_gs_primary_folder ON group_stats(primary_folder)')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS duplicate_finder_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        cursor.execute('''
            CREATE VIEW IF NOT EXISTS phash_similarities_view AS
            SELECT image_id_a as image_id, image_id_b as neighbor_id, threshold, distance
            FROM phash_similarities
            UNION ALL
            SELECT image_id_b as image_id, image_id_a as neighbor_id, threshold, distance
            FROM phash_similarities
        ''')

        conn.commit()

    def _get_connection(self):
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            # Enable foreign key constraints (required for CASCADE DELETE)
            self._conn.execute('PRAGMA foreign_keys = ON')
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def set_stop(self):
        """Signal all phases to stop"""
        print("[Workflow] STOP signal set!")
        self._stop_event.set()
        print(f"[Workflow] Stop event is_set: {self._stop_event.is_set()}")

    def clear_stop(self):
        """Clear stop signal"""
        print("[Workflow] STOP signal cleared")
        self._stop_event.clear()

    # ========== Phase 1: Refresh Images ==========

    def phase1_refresh_images(
        self,
        file_paths: List[str],
        progress_callback: Optional[Callable] = None,
        scope_dir_paths: Optional[List[str]] = None,
    ) -> Dict:
        """
        Phase 1: Refresh image table
        - Scan all files vs DB
        - Remove missing files from DB
        - Add new files, compute phash, set status='pending'
        - Skip files with status='computed'

        Args:
            file_paths: List of image paths to scan
            progress_callback: Optional callback(current, total, message)
            scope_dir_paths: if set, the "missing files" deletion is RESTRICTED
                to DB rows whose dir_path is within this scope (exact match OR
                a subdirectory). Used by /compare-folders so a partial Phase 1
                doesn't nuke rows outside the targeted folders.

        Returns:
            {
                'added': int,
                'removed': int,
                'skipped': int,
                'errors': List[Dict]
            }
        """
        self.clear_stop()
        start_time = time.time()
        conn = self._get_connection()
        cursor = conn.cursor()

        print(f"[Phase 1] START: Refreshing image table for {len(file_paths)} files...")

        # Load performance settings
        try:
            from .settings_manager import settings_manager
            scan_delay = settings_manager.get_phase1_scan_delay()
            compute_delay = settings_manager.get_phase1_compute_delay()
            progress_interval = settings_manager.get_phase1_progress_update_interval()
            ipc_chunk_size = settings_manager.get_phase1_ipc_chunk_size()
            db_commit_batch_size = settings_manager.get_phase1_db_commit_batch_size()

            set_performance_delays(scan_delay=scan_delay, compare_delay=0.0)
            set_compute_delay(compute_delay)

            if scan_delay > 0:
                print(f"[Phase 1] Scan delay enabled: {scan_delay}s per file")
            if compute_delay > 0:
                print(f"[Phase 1] Compute delay enabled: {compute_delay}s per file")
            print(f"[Phase 1] Progress update interval: every {progress_interval} files")
            print(f"[Phase 1] IPC chunk size: {ipc_chunk_size}")
            print(f"[Phase 1] DB commit batch size: {db_commit_batch_size}")
        except Exception as e:
            print(f"[Warning] Could not load performance settings: {e}")
            set_performance_delays(0.0, 0.0)
            set_compute_delay(0.0)
            progress_interval = 100
            ipc_chunk_size = 10
            db_commit_batch_size = 100

        # Step 1: Remove missing files from DB
        # If scope_dir_paths is provided, the candidate set is RESTRICTED to DB
        # rows whose dir_path matches that scope (exact or subdir). Critical for
        # /compare-folders partial runs — otherwise rows outside scope get
        # treated as "missing" and deleted.
        print(f"[Phase 1] Step 1: Checking for missing files in DB...")
        if progress_callback:
            progress_callback(0, len(file_paths), "Checking missing files...")

        if scope_dir_paths:
            clauses = []
            params: list = []
            for f in scope_dir_paths:
                fa = os.path.abspath(f)
                clauses.append("(dir_path = ? OR dir_path LIKE ?)")
                params.append(fa)
                params.append(fa.rstrip(os.sep) + os.sep + '%')
            where = ' OR '.join(clauses)
            cursor.execute(f"SELECT id, file_path FROM image_hashes WHERE {where}", params)
            print(f"[Phase 1] Step 1 SCOPED: limiting to {len(scope_dir_paths)} dir_path roots")
        else:
            cursor.execute("SELECT id, file_path FROM image_hashes")
        db_files = cursor.fetchall()
        print(f"[Phase 1] Found {len(db_files)} files in DB (scope={'limited' if scope_dir_paths else 'global'})")

        db_file_set = {file_path for _, file_path in db_files}
        fs_file_set = set(file_paths)

        missing_files = db_file_set - fs_file_set
        removed_count = 0
        DELETE_COMMIT_THRESHOLD = 100

        for db_id, file_path in db_files:
            if file_path in missing_files:
                cursor.execute("DELETE FROM image_hashes WHERE id = ?", (db_id,))
                removed_count += 1

                # Commit every 100 deletes
                if removed_count % DELETE_COMMIT_THRESHOLD == 0:
                    conn.commit()
                    print(f"[Phase 1] Step 1: Committed {DELETE_COMMIT_THRESHOLD} deletes (total removed: {removed_count})")

        conn.commit()  # Final commit for remaining deletes
        print(f"[Phase 1] Step 1 DONE: Removed {removed_count} missing files from DB")

        # Step 2: Check existing files
        print(f"[Phase 1] Step 2: Checking which files need computation...")
        cursor.execute("SELECT file_path, status FROM image_hashes")
        db_status = {row[0]: row[1] for row in cursor.fetchall()}

        files_to_compute = []
        skipped_count = 0
        checked_count = 0
        total_files = len(file_paths)
        scan_stopped = False

        for file_path in file_paths:
            if self._stop_event.is_set():
                print("[Phase 1] ⏸️ Stop signal received during scan")
                scan_stopped = True
                break  # Exit scan loop, return partial results

            # Apply scan delay from settings (for CPU load reduction or testing)
            if _SCAN_DELAY > 0:
                time.sleep(_SCAN_DELAY)

            status = db_status.get(file_path)
            if status == 'computed':
                skipped_count += 1
            elif status is None:
                # New file, needs phash computation
                files_to_compute.append(file_path)
            # status='pending' will also be computed

            checked_count += 1
            # Send progress updates during file checking
            if progress_callback and (checked_count % progress_interval == 0 or checked_count == total_files):
                progress_callback(
                    checked_count,
                    total_files,
                    f"Checking files... ({checked_count}/{total_files})"
                )

        if scan_stopped:
            print(f"[Phase 1] ⏸️ Scan stopped: checked {checked_count}/{total_files} files, found {len(files_to_compute)} to compute")
        else:
            print(f"[Phase 1] Step 2 DONE: Skipped {skipped_count} computed files, need to compute {len(files_to_compute)} files")

        # Step 3: Compute phash for new/pending files
        added_count = 0
        error_files = []

        if files_to_compute:
            from .settings_manager import settings_manager
            num_workers = settings_manager.get_max_cpu_cores()
            # Use the already loaded values from Phase 1 settings
            # compute_delay, db_commit_batch_size, ipc_chunk_size are already loaded above

            print(f"[Phase 1] Step 3: Settings check - max_cpu_cores from settings: {settings_manager.get_settings().get('max_cpu_cores', 'NOT_SET')}")
            print(f"[Phase 1] Step 3: Computing phash using {num_workers} workers, db_commit_batch_size={db_commit_batch_size}, ipc_chunk_size={ipc_chunk_size}...")

            # Use apply_async for true control over task submission
            with Pool(processes=num_workers) as pool:
                batch_buffer = []
                completed = 0
                stop_requested = False
                pending_results = []  # Store AsyncResult objects
                submitted_count = 0
                max_pending = num_workers * 2  # Allow 2x workers pending tasks

                print(f"[Phase 1] Submitting tasks with max_pending={max_pending}")

                # Submit initial batch of tasks
                for idx in range(min(max_pending, len(files_to_compute))):
                    if self._stop_event.is_set():
                        print(f"[Phase 1 Submit] 🛑 STOP detected before submitting task {idx+1}")
                        stop_requested = True
                        break
                    file_path = files_to_compute[idx]
                    async_result = pool.apply_async(_compute_single_hash_with_delay, ((file_path, compute_delay),))
                    pending_results.append((async_result, file_path))
                    submitted_count += 1
                    if submitted_count <= 20:
                        print(f"[Phase 1 Submit] Submitted task {submitted_count}/{len(files_to_compute)}: {os.path.basename(file_path)}")

                # Process results and submit new tasks as slots become available
                while pending_results:
                    # Check stop event
                    if self._stop_event.is_set() and not stop_requested:
                        print("=" * 80)
                        print(f"[Phase 1 Main] 🛑 STOP EVENT DETECTED!")
                        print(f"[Phase 1 Main] Submitted: {submitted_count}/{len(files_to_compute)}, Completed: {completed}/{len(files_to_compute)}")
                        print(f"[Phase 1 Main] Pending results: {len(pending_results)} tasks still in flight")
                        print("[Phase 1 Main] ⏸️ Will not submit new tasks, waiting for in-flight tasks...")
                        print("=" * 80)
                        stop_requested = True

                    # Poll for completed results (non-blocking)
                    for async_result, file_path in pending_results[:]:
                        if async_result.ready():
                            # Get result
                            try:
                                result = async_result.get(timeout=0.1)
                                filename = os.path.basename(result.get('file_path', 'unknown'))

                                if result.get('error'):
                                    error_files.append(result)
                                    print(f"[Phase 1 Main] Received ERROR for: {filename}")
                                else:
                                    batch_buffer.append(result)
                                    if stop_requested:
                                        print(f"[Phase 1 Main] (STOP mode) Received SUCCESS for: {filename}")
                                    else:
                                        print(f"[Phase 1 Main] Received SUCCESS for: {filename} (batch: {len(batch_buffer)}/{db_commit_batch_size})")

                                    if len(batch_buffer) >= db_commit_batch_size:
                                        self._insert_images_batch(batch_buffer)
                                        added_count += len(batch_buffer)
                                        batch_buffer = []

                                completed += 1
                                if completed % progress_interval == 0:
                                    print(f"[Phase 1 Main] Progress: {completed}/{len(files_to_compute)}, stop_event={self._stop_event.is_set()}")
                                if progress_callback and (completed % progress_interval == 0 or completed == len(files_to_compute)):
                                    progress_callback(completed, len(files_to_compute), f"Computing phash... ({completed}/{len(files_to_compute)})")

                            except Exception as e:
                                print(f"[Phase 1 Main] Error getting result for {os.path.basename(file_path)}: {e}")

                            # Remove from pending
                            pending_results.remove((async_result, file_path))

                            # Submit next task if not stopped and more tasks available
                            if not stop_requested and submitted_count < len(files_to_compute):
                                next_idx = submitted_count
                                next_file = files_to_compute[next_idx]
                                async_result = pool.apply_async(_compute_single_hash_with_delay, ((next_file, compute_delay),))
                                pending_results.append((async_result, next_file))
                                submitted_count += 1
                                if submitted_count <= 20 or submitted_count % 100 == 0:
                                    print(f"[Phase 1 Submit] Submitted task {submitted_count}/{len(files_to_compute)}: {os.path.basename(next_file)}")

                            break  # Check next result

                    # Small sleep to avoid busy loop
                    if pending_results:
                        time.sleep(0.01)

                # Final batch
                if batch_buffer:
                    self._insert_images_batch(batch_buffer)
                    added_count += len(batch_buffer)

                if stop_requested:
                    print(f"[Phase 1 Main] ⏸️ Stopped: Submitted {submitted_count}/{len(files_to_compute)}, Completed {completed}/{len(files_to_compute)}")
        else:
            # No files to compute, send completion progress
            print(f"[Phase 1] No files to compute: skipped={skipped_count}, total={len(file_paths)}")
            if progress_callback:
                progress_callback(len(file_paths), len(file_paths), f"All files already computed (skipped {skipped_count})")
            stop_requested = False  # No multiprocessing, so no stop

        # Combine scan_stopped and compute stop_requested
        any_stopped = scan_stopped or stop_requested

        elapsed = time.time() - start_time

        if any_stopped:
            print(f"[Phase 1] ⏸️ Stopped by user in {elapsed:.1f}s: +{added_count}, -{removed_count}, skipped {skipped_count}")
        else:
            print(f"[Phase 1] ✅ Completed in {elapsed:.1f}s: +{added_count}, -{removed_count}, skipped {skipped_count}")

        # Send final progress
        if progress_callback:
            total = len(file_paths)
            if any_stopped:
                progress_callback(completed if 'completed' in locals() else checked_count, len(files_to_compute) if files_to_compute else total, f"Stopped: +{added_count}, -{removed_count}, skipped {skipped_count}")
            else:
                progress_callback(total, total, f"Complete: +{added_count}, -{removed_count}, skipped {skipped_count}")

        return {
            'added': added_count,
            'removed': removed_count,
            'skipped': skipped_count,
            'errors': error_files,
            'elapsed': elapsed,
            'stopped': any_stopped  # 合并两个停止标志
        }

    def _insert_images_batch(self, batch: List[Dict]):
        """Insert batch of images with status='pending' (max 100 at a time)"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Prepare data for executemany
        batch_data = []
        for item in batch:
            file_path = item['file_path']
            filename = Path(file_path).name
            dir_path = os.path.dirname(file_path)
            batch_data.append((
                filename,
                item['filesize'],
                file_path,
                item['phash'],
                item['resolution'],
                dir_path,
                item.get('mtime'),
            ))

        # Use executemany for better performance
        cursor.executemany('''
            INSERT OR IGNORE INTO image_hashes
            (filename, filesize, file_path, phash, resolution, dir_path, mtime, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
        ''', batch_data)

        conn.commit()
        print(f"[Phase 1] _insert_images_batch: Committed {len(batch)} images")

    # ========== Phase 2: Build Similarities ==========

    def phase2_build_similarities(
        self,
        threshold_distance: int = 12,  # distance ≤ 12 for 80% similarity
        progress_callback: Optional[Callable] = None
    ) -> Dict:
        """
        Phase 2: Build phash_similarities table
        - Get all status='pending' images
        - Compute distance with ALL images (brute force + multiprocessing)
        - If distance ≤ threshold_distance, save to phash_similarities
        - Mark images as status='computed'

        Args:
            threshold_distance: Max hamming distance (default 12 for 80%)
            progress_callback: Optional callback(current, total, message)

        Returns:
            {
                'processed': int,
                'similarities_found': int,
                'elapsed': float
            }
        """
        self.clear_stop()
        start_time = time.time()
        conn = self._get_connection()
        cursor = conn.cursor()

        print(f"[Phase 2] START: Building similarities (threshold distance ≤ {threshold_distance})...")

        # Load performance settings
        try:
            from .settings_manager import settings_manager
            compare_delay = settings_manager.get_phase2_compare_delay()
            db_commit_batch_size = settings_manager.get_phase2_db_commit_batch_size()
            progress_interval = settings_manager.get_phase2_progress_update_interval()
            ipc_chunk_size = settings_manager.get_phase2_ipc_chunk_size()
            num_workers = settings_manager.get_max_cpu_cores()

            set_performance_delays(scan_delay=0.0, compare_delay=compare_delay)

            if compare_delay > 0:
                print(f"[Phase 2] Compare delay enabled: {compare_delay}s per comparison")
            print(f"[Phase 2] DB commit batch size: {db_commit_batch_size}")
            print(f"[Phase 2] Progress update interval: every {progress_interval} images")
            print(f"[Phase 2] IPC chunk size: {ipc_chunk_size}")
        except Exception as e:
            print(f"[Warning] Could not load performance settings: {e}")
            set_performance_delays(0.0, 0.0)
            compare_delay = 0.0
            db_commit_batch_size = 100
            progress_interval = 100
            ipc_chunk_size = 10
            num_workers = 1

        # Get pending images
        print(f"[Phase 2] Step 1: Getting pending images...")
        cursor.execute("SELECT id, phash FROM image_hashes WHERE status = 'pending'")
        pending_images = cursor.fetchall()

        if not pending_images:
            print("[Phase 2] No pending images, nothing to do")
            return {'processed': 0, 'similarities_found': 0, 'elapsed': 0}

        # Get all images (for distance comparison)
        print(f"[Phase 2] Step 2: Getting all images for comparison...")
        cursor.execute("SELECT id, phash FROM image_hashes")
        all_images = cursor.fetchall()

        print(f"[Phase 2] Step 2 DONE: Processing {len(pending_images)} pending images against {len(all_images)} total images")

        print(f"[Phase 2] Step 3: Starting multiprocessing with {num_workers} workers, db_commit_batch_size={db_commit_batch_size}, ipc_chunk_size={ipc_chunk_size}")
        print(f"[Phase 2] Using NEW architecture: Pool(initializer) - all_images transmitted only {num_workers} times (once per worker)")

        similarities_count = 0
        processed_count = 0

        # Use apply_async for true control over task submission
        with Pool(processes=num_workers, initializer=_phase2_worker_init, initargs=(all_images,)) as pool:
            stop_requested = False
            pending_results = []  # Store (AsyncResult, img_id) tuples
            submitted_count = 0
            max_pending = num_workers * 2  # Allow 2x workers pending tasks

            print(f"[Phase 2] Submitting tasks with max_pending={max_pending}")

            # Submit initial batch of tasks
            for idx in range(min(max_pending, len(pending_images))):
                if self._stop_event.is_set():
                    print(f"[Phase 2 Submit] 🛑 STOP detected before submitting task {idx+1}")
                    stop_requested = True
                    break
                img = pending_images[idx]
                task_args = (img[0], img[1], threshold_distance, compare_delay)
                async_result = pool.apply_async(_compute_similarities_single, (task_args,))
                pending_results.append((async_result, img[0]))
                submitted_count += 1
                if submitted_count <= 20:
                    print(f"[Phase 2 Submit] Submitted task {submitted_count}/{len(pending_images)}: image_id={img[0]}")

            # Process results and submit new tasks as slots become available
            while pending_results:
                # Check stop event
                if self._stop_event.is_set() and not stop_requested:
                    print("=" * 80)
                    print(f"[Phase 2 Main] 🛑 STOP EVENT DETECTED!")
                    print(f"[Phase 2 Main] Submitted: {submitted_count}/{len(pending_images)}, Processed: {processed_count}/{len(pending_images)}")
                    print(f"[Phase 2 Main] Pending results: {len(pending_results)} tasks still in flight")
                    print("[Phase 2 Main] ⏸️ Will not submit new tasks, waiting for in-flight tasks...")
                    print("=" * 80)
                    stop_requested = True

                # Poll for completed results (non-blocking)
                for async_result, img_id in pending_results[:]:
                    if async_result.ready():
                        # Get result
                        try:
                            result = async_result.get(timeout=0.1)
                            # result is tuple: (img_id, similarities_list)
                            result_img_id, similarities_list = result
                            processed_count += 1

                            # ⚠️ CRITICAL: Commit similarities BEFORE updating status
                            if similarities_list:
                                cursor.executemany('''
                                    INSERT OR REPLACE INTO phash_similarities
                                    (image_id_a, image_id_b, threshold, distance)
                                    VALUES (?, ?, 80, ?)
                                ''', similarities_list)
                                conn.commit()
                                similarities_count += len(similarities_list)
                                if stop_requested:
                                    print(f"[Phase 2 Main] (STOP mode) Committed {len(similarities_list)} similarities for image {result_img_id}")
                                else:
                                    print(f"[Phase 2 Main] ✓ Committed {len(similarities_list)} similarities for image {result_img_id}")

                            # 2. NOW it's safe to update status to 'computed'
                            cursor.execute("UPDATE image_hashes SET status = 'computed' WHERE id = ?", (result_img_id,))
                            conn.commit()

                            # Progress update
                            if progress_callback and (processed_count % progress_interval == 0 or processed_count == len(pending_images)):
                                progress_callback(processed_count, len(pending_images), f"Building similarities... ({processed_count}/{len(pending_images)})")

                            if processed_count % progress_interval == 0 or processed_count == len(pending_images):
                                print(f"[Phase 2 Main] Progress: {processed_count}/{len(pending_images)}, stop_event={self._stop_event.is_set()}")

                        except Exception as e:
                            print(f"[Phase 2 Main] Error getting result for image {img_id}: {e}")

                        # Remove from pending
                        pending_results.remove((async_result, img_id))

                        # Submit next task if not stopped and more tasks available
                        if not stop_requested and submitted_count < len(pending_images):
                            next_idx = submitted_count
                            next_img = pending_images[next_idx]
                            task_args = (next_img[0], next_img[1], threshold_distance, compare_delay)
                            async_result = pool.apply_async(_compute_similarities_single, (task_args,))
                            pending_results.append((async_result, next_img[0]))
                            submitted_count += 1
                            if submitted_count <= 20 or submitted_count % 100 == 0:
                                print(f"[Phase 2 Submit] Submitted task {submitted_count}/{len(pending_images)}: image_id={next_img[0]}")

                        break  # Check next result

                # Small sleep to avoid busy loop
                if pending_results:
                    time.sleep(0.01)

            if stop_requested:
                print(f"[Phase 2 Main] ⏸️ Stopped: Submitted {submitted_count}/{len(pending_images)}, Processed {processed_count}/{len(pending_images)}")

        elapsed = time.time() - start_time

        if stop_requested:
            print(f"[Phase 2] ⏸️ Stopped by user in {elapsed:.1f}s: processed {processed_count}/{len(pending_images)}, found {similarities_count} similarities")
        else:
            print(f"[Phase 2] ✅ Completed in {elapsed:.1f}s: processed {processed_count}, found {similarities_count} similarities")

        # Send final progress
        if progress_callback:
            if stop_requested:
                progress_callback(processed_count, len(pending_images), f"Stopped: saved {processed_count}/{len(pending_images)} images")
            else:
                progress_callback(len(pending_images), len(pending_images), f"Complete: processed {processed_count}, found {similarities_count} similarities")

        return {
            'processed': processed_count,
            'similarities_found': similarities_count,
            'elapsed': elapsed,
            'stopped': stop_requested  # 新增标志
        }

    def _hamming_distance(self, hash1: str, hash2: str) -> int:
        """Compute hamming distance between two phash strings"""
        return bin(int(hash1, 16) ^ int(hash2, 16)).count('1')

    # ========== Compare Folders (focused / scoped) ==========

    def compare_folders_focused(
        self,
        folders: List[str],
        threshold_distance: int = 12,
        progress_callback: Optional[Callable] = None,
    ) -> Dict:
        """
        Focused pairwise comparison limited to the given folders.

        Contract (no global side-effects):
          - reads `image_hashes` rows whose `dir_path` is inside the scope
            (exact match OR any subdirectory)
          - walks the filesystem under each scope folder, respecting
            `exclude_folder_paths`
          - for files on disk that aren't yet in the DB: compute phash and
            INSERT a new row (status='computed')
          - for files in DB whose phash column happens to be NULL/empty:
            also compute and UPDATE (defensive)
          - pairwise compares EVERY image in scope (old + newly-inserted)
            and INSERT OR IGNORE the matching pairs into `phash_similarities`
          - never deletes any image_hashes row (use global Phase 1 for that)
          - never touches scope-outside rows or scope-outside similarities

        Caller is expected to run `phase2_5_materialize_groups` afterwards
        to surface the new edges in Phase 3.
        """
        from .phash_cache import _compute_single_hash

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

        # ---- Step 1: read scoped DB rows (recursive — same folder OR subdir) ----
        cb(5, "Step 1/4: Reading scoped DB rows")
        clauses, params = [], []
        for f in folders_abs:
            clauses.append("(dir_path = ? OR dir_path LIKE ?)")
            params.append(f)
            params.append(f.rstrip(os.sep) + os.sep + '%')
        where_clause = ' OR '.join(clauses)
        cur.execute(
            f"SELECT id, file_path, phash FROM image_hashes WHERE {where_clause}",
            params,
        )
        db_by_path: Dict[str, Tuple[int, Optional[str]]] = {
            row[1]: (row[0], row[2]) for row in cur.fetchall()
        }
        print(f"[Compare Focused] Step 1: {len(db_by_path)} existing DB rows in scope")

        # ---- Step 2: walk the filesystem under each scope folder ----
        cb(10, "Step 2/4: Walking filesystem")
        try:
            from .settings_manager import settings_manager
            exclude_paths = settings_manager.get_settings().get('exclude_folder_paths', []) or []
        except Exception:
            exclude_paths = []
        exclude_abs = [os.path.abspath(p) for p in exclude_paths if p]

        def is_excluded(p: str) -> bool:
            p_abs = os.path.abspath(p)
            for ex in exclude_abs:
                if p_abs == ex or p_abs.startswith(ex + os.sep):
                    return True
            return False

        # Project-wide image extensions — match the rest of the codebase
        IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif')
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
                    if fname.lower().endswith(IMAGE_EXTS):
                        fs_files.append(os.path.join(root, fname))
        print(f"[Compare Focused] Step 2: {len(fs_files)} files on disk in scope")

        # ---- Step 3: build scope_images = (id, phash, file_path) for every FS file ----
        cb(20, "Step 3/4: Resolving phash for in-scope files")
        scope_images: List[Tuple[int, str, str]] = []
        new_computed = 0
        errors = 0
        need_compute: List[str] = []          # files not in DB at all
        need_phash_update: List[Tuple[int, str]] = []  # in DB but phash NULL/empty

        for fs_file in fs_files:
            existing = db_by_path.get(fs_file)
            if existing is not None:
                row_id, row_phash = existing
                if row_phash:
                    scope_images.append((row_id, row_phash, fs_file))
                else:
                    # Edge case: row exists but phash is missing — recompute
                    need_phash_update.append((row_id, fs_file))
            else:
                need_compute.append(fs_file)

        print(f"[Compare Focused] Step 3: {len(scope_images)} reused from DB, "
              f"{len(need_compute)} need compute (not in DB), "
              f"{len(need_phash_update)} need compute (DB phash missing)")

        # 3a: compute + INSERT for files not in DB
        for i, fs_file in enumerate(need_compute):
            result = _compute_single_hash(fs_file)
            if result.get('error'):
                errors += 1
                print(f"[Compare Focused] phash error: {fs_file}: {result.get('error_msg')}")
                continue
            filename = os.path.basename(fs_file)
            dir_path = os.path.dirname(fs_file)
            cur.execute('''
                INSERT OR IGNORE INTO image_hashes
                (filename, filesize, file_path, phash, resolution, status, dir_path, mtime)
                VALUES (?, ?, ?, ?, ?, 'computed', ?, ?)
            ''', (filename, result['filesize'], fs_file, result['phash'],
                  result['resolution'], dir_path, result.get('mtime')))
            cur.execute("SELECT id FROM image_hashes WHERE file_path = ?", (fs_file,))
            row = cur.fetchone()
            if row:
                scope_images.append((row[0], result['phash'], fs_file))
                new_computed += 1
            if (i + 1) % 50 == 0:
                cb(20 + int(30 * (i + 1) / max(1, len(need_compute))),
                   f"Step 3a: computing phash {i + 1}/{len(need_compute)}")

        # 3b: compute + UPDATE for in-DB rows with missing phash
        for i, (row_id, fs_file) in enumerate(need_phash_update):
            result = _compute_single_hash(fs_file)
            if result.get('error'):
                errors += 1
                continue
            cur.execute('''
                UPDATE image_hashes
                SET phash = ?, resolution = ?, filesize = ?, mtime = ?,
                    status = 'computed'
                WHERE id = ?
            ''', (result['phash'], result['resolution'], result['filesize'],
                  result.get('mtime'), row_id))
            scope_images.append((row_id, result['phash'], fs_file))
            new_computed += 1
            if (i + 1) % 50 == 0:
                cb(50 + int(10 * (i + 1) / max(1, len(need_phash_update))),
                   f"Step 3b: updating phash {i + 1}/{len(need_phash_update)}")

        if new_computed or errors:
            conn.commit()

        n = len(scope_images)
        print(f"[Compare Focused] Step 3 DONE: scope = {n} images ({new_computed} freshly computed, {errors} errors)")

        if n < 2:
            print("[Compare Focused] Less than 2 images in scope — nothing to compare")
            elapsed = time.time() - start
            return {
                'folders': folders_abs,
                'fs_files': len(fs_files),
                'scope_total': n,
                'new_phashes_computed': new_computed,
                'errors': errors,
                'pairs_found': 0,
                'new_similarities_inserted': 0,
                'elapsed': elapsed,
            }

        # ---- Step 4: pairwise compare WITHIN scope, INSERT OR IGNORE ----
        total_comparisons = n * (n - 1) // 2
        cb(60, f"Step 4/4: Pairwise compare ({total_comparisons} pairs)")
        print(f"[Compare Focused] Step 4: pairwise compare among {n} images "
              f"({total_comparisons} hamming-distance computations)")

        pairs: List[Tuple[int, int, int, int]] = []
        # ⚠️ Stable threshold key for the row — must match what the rest of the
        # pipeline writes (Phase 2 stores `threshold=80`). Phase 2.5 filters by
        # distance, so this column is the "schema threshold", NOT the UI %.
        SCHEMA_THRESHOLD = 80

        for i in range(n):
            id_a, phash_a, _ = scope_images[i]
            try:
                int_a = int(phash_a, 16)
            except (ValueError, TypeError):
                continue
            for j in range(i + 1, n):
                id_b, phash_b, _ = scope_images[j]
                try:
                    int_b = int(phash_b, 16)
                except (ValueError, TypeError):
                    continue
                if id_a == id_b:
                    continue
                dist = bin(int_a ^ int_b).count('1')
                if dist <= threshold_distance:
                    if id_a < id_b:
                        pairs.append((id_a, id_b, SCHEMA_THRESHOLD, dist))
                    else:
                        pairs.append((id_b, id_a, SCHEMA_THRESHOLD, dist))

        print(f"[Compare Focused] Step 4: {len(pairs)} similar pair(s) within scope (distance ≤ {threshold_distance})")

        # ---- Step 5: bulk INSERT OR IGNORE ----
        cb(90, "Inserting similarity edges")
        new_inserted = 0
        if pairs:
            BATCH = 5000
            for i in range(0, len(pairs), BATCH):
                chunk = pairs[i:i + BATCH]
                cur.executemany('''
                    INSERT OR IGNORE INTO phash_similarities
                    (image_id_a, image_id_b, threshold, distance)
                    VALUES (?, ?, ?, ?)
                ''', chunk)
                new_inserted += cur.rowcount
            conn.commit()
        print(f"[Compare Focused] Step 5: {new_inserted} new edges inserted "
              f"({len(pairs) - new_inserted} were already present)")

        elapsed = time.time() - start
        cb(100, f"Compare done — {new_inserted} new edges")
        print("=" * 80)
        print(f"[Compare Focused] ✅ COMPLETE in {elapsed:.2f}s")
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

    # ========== Phase 2.5: Materialize Groups ==========

    def phase2_5_materialize_groups(
        self,
        threshold_percent: int = 80,
        same_folder_filter: bool = True,
        progress_callback: Optional[Callable] = None,
    ) -> Dict:
        """
        Phase 2.5: Materialize duplicate groups + per-group stats into DB tables.

        Reads phash_similarities, filters (threshold + per-image whitelist + optional
        same-folder), builds connected components, drops fully-whitelisted groups,
        then writes everything into duplicate_groups + group_stats.

        Records the threshold used into duplicate_finder_meta so Phase 3 can detect
        staleness.

        Args:
            threshold_percent: UI similarity threshold (80, 90, 95, 100)
            same_folder_filter: whether to skip same-folder pairs
            progress_callback: optional callback(current, total, message)
        """
        self.clear_stop()
        start_time = time.time()
        conn = self._get_connection()
        cursor = conn.cursor()

        max_distance = int(64 * (100 - threshold_percent) / 100)

        print("=" * 80)
        print(f"[Phase 2.5] START")
        print(f"[Phase 2.5]   DB path             : {self.db_path}")
        print(f"[Phase 2.5]   threshold_percent   : {threshold_percent}% (max_distance ≤ {max_distance})")
        print(f"[Phase 2.5]   same_folder_filter  : {same_folder_filter}")
        print(f"[Phase 2.5]   stop_event.is_set() : {self._stop_event.is_set()}")
        print("=" * 80)

        # Pre-flight: log relevant DB stats
        try:
            n_images = cursor.execute("SELECT COUNT(*) FROM image_hashes").fetchone()[0]
            n_pending = cursor.execute("SELECT COUNT(*) FROM image_hashes WHERE status='pending'").fetchone()[0]
            n_computed = cursor.execute("SELECT COUNT(*) FROM image_hashes WHERE status='computed'").fetchone()[0]
            n_dir_null = cursor.execute("SELECT COUNT(*) FROM image_hashes WHERE dir_path IS NULL").fetchone()[0]
            n_sim = cursor.execute("SELECT COUNT(*) FROM phash_similarities WHERE threshold=80").fetchone()[0]
            n_wl_img = cursor.execute("SELECT COUNT(*) FROM whitelist").fetchone()[0]
            n_wl_grp = cursor.execute("SELECT COUNT(*) FROM whitelist_groups").fetchone()[0]
            n_old_dg = cursor.execute("SELECT COUNT(*) FROM duplicate_groups").fetchone()[0]
            n_old_gs = cursor.execute("SELECT COUNT(*) FROM group_stats").fetchone()[0]
            print(f"[Phase 2.5] Pre-flight DB stats:")
            print(f"[Phase 2.5]   image_hashes total   : {n_images} (pending={n_pending}, computed={n_computed}, dir_path NULL={n_dir_null})")
            print(f"[Phase 2.5]   phash_similarities   : {n_sim} (threshold=80)")
            print(f"[Phase 2.5]   whitelist (per-image): {n_wl_img}")
            print(f"[Phase 2.5]   whitelist_groups     : {n_wl_grp}")
            print(f"[Phase 2.5]   duplicate_groups OLD : {n_old_dg} (will be replaced)")
            print(f"[Phase 2.5]   group_stats OLD      : {n_old_gs} (will be replaced)")
        except Exception as e:
            print(f"[Phase 2.5] WARNING: pre-flight stats query failed: {e}")

        if n_pending > 0:
            print(f"[Phase 2.5] ⚠️ WARNING: {n_pending} images still have status='pending'. "
                  f"Phase 2 may not have finished — similarities for these images are missing.")

        def cb(pct: int, msg: str):
            if progress_callback:
                progress_callback(pct, 100, msg)

        def stopped() -> bool:
            if self._stop_event.is_set():
                print(f"[Phase 2.5] ⏸️ Stop event detected; aborting")
                return True
            return False

        step_start = time.time()

        try:
            # Step 1: filter edges in SQL
            cb(0, "Step 1/5: Filtering edges (SQL)")
            print(f"[Phase 2.5] Step 1/5: SQL filter (threshold + whitelist + same_folder={same_folder_filter})")
            same_folder_sql = "AND a.dir_path <> b.dir_path" if same_folder_filter else ""
            sql = f'''
                SELECT s.image_id_a, s.image_id_b, s.distance
                FROM phash_similarities s
                JOIN image_hashes a ON s.image_id_a = a.id
                JOIN image_hashes b ON s.image_id_b = b.id
                LEFT JOIN whitelist wa ON wa.image_id = s.image_id_a
                LEFT JOIN whitelist wb ON wb.image_id = s.image_id_b
                WHERE s.threshold = 80
                  AND s.distance <= ?
                  AND wa.image_id IS NULL
                  AND wb.image_id IS NULL
                  {same_folder_sql}
            '''
            cursor.execute(sql, (max_distance,))
            edges = cursor.fetchall()
            elapsed_step = time.time() - step_start
            print(f"[Phase 2.5] Step 1/5 DONE: {len(edges)} edges after SQL filter (took {elapsed_step:.2f}s)")
            if edges:
                # Sample a few edges for sanity check
                sample = edges[:3]
                print(f"[Phase 2.5]   Sample edges: {sample}")
            if stopped():
                return {'stopped': True, 'elapsed': time.time() - start_time}

            # Step 2: BFS connected components
            step_start = time.time()
            cb(20, "Step 2/5: Building connected components")
            print(f"[Phase 2.5] Step 2/5: BFS connected components from {len(edges)} edges")
            groups = self._build_groups(edges)
            elapsed_step = time.time() - step_start
            if groups:
                sizes = [len(g) for g in groups]
                print(f"[Phase 2.5] Step 2/5 DONE: {len(groups)} groups (took {elapsed_step:.2f}s)")
                print(f"[Phase 2.5]   group size: min={min(sizes)}, max={max(sizes)}, mean={sum(sizes)/len(sizes):.1f}, total_members={sum(sizes)}")
            else:
                print(f"[Phase 2.5] Step 2/5 DONE: 0 groups (took {elapsed_step:.2f}s) — no duplicates found at this threshold")
            if stopped():
                return {'stopped': True, 'elapsed': time.time() - start_time}

            # Step 3: filter fully-whitelisted groups
            step_start = time.time()
            cb(40, "Step 3/5: Filtering whitelisted groups")
            print(f"[Phase 2.5] Step 3/5: filtering whitelisted groups (n_whitelist_groups={n_wl_grp})")
            if n_wl_grp == 0:
                # Optimization: nothing to check; skip the per-group lookup loop
                filtered_groups = groups
                whitelisted_dropped = 0
                print(f"[Phase 2.5]   Skipping per-group whitelist check (no whitelist_groups rows)")
            else:
                cache = PHashCache(str(self.db_path))
                filtered_groups = [g for g in groups if not cache.is_group_whitelisted(g)]
                whitelisted_dropped = len(groups) - len(filtered_groups)
            elapsed_step = time.time() - step_start
            print(f"[Phase 2.5] Step 3/5 DONE: {len(filtered_groups)} groups remain, dropped {whitelisted_dropped} whitelisted (took {elapsed_step:.2f}s)")
            if stopped():
                return {'stopped': True, 'elapsed': time.time() - start_time}

            # Step 4: rewrite duplicate_groups
            step_start = time.time()
            cb(60, "Step 4/5: Writing duplicate_groups")
            print(f"[Phase 2.5] Step 4/5: clearing OLD tables + inserting new membership rows")
            cursor.execute("DELETE FROM group_stats")
            n_after_del_gs = cursor.execute("SELECT COUNT(*) FROM group_stats").fetchone()[0]
            cursor.execute("DELETE FROM duplicate_groups")
            n_after_del_dg = cursor.execute("SELECT COUNT(*) FROM duplicate_groups").fetchone()[0]
            print(f"[Phase 2.5]   After DELETE: group_stats={n_after_del_gs}, duplicate_groups={n_after_del_dg}")

            dg_rows = []
            for group_id, member_ids in enumerate(filtered_groups, start=1):
                for image_id in member_ids:
                    dg_rows.append((group_id, image_id))
            if dg_rows:
                cursor.executemany(
                    "INSERT INTO duplicate_groups (group_id, image_id) VALUES (?, ?)",
                    dg_rows,
                )
            n_after_ins_dg = cursor.execute("SELECT COUNT(*) FROM duplicate_groups").fetchone()[0]
            elapsed_step = time.time() - step_start
            print(f"[Phase 2.5] Step 4/5 DONE: wrote {len(dg_rows)} rows (verified count={n_after_ins_dg}), took {elapsed_step:.2f}s")
            if stopped():
                conn.rollback()
                print(f"[Phase 2.5]   Stop detected after Step 4; rolled back")
                return {'stopped': True, 'elapsed': time.time() - start_time}

            # Step 5: per-group aggregates via SQL (no Python iteration over members)
            step_start = time.time()
            cb(80, "Step 5/5: Computing group_stats")
            print(f"[Phase 2.5] Step 5/5: computing group_stats via SQL aggregates")

            print(f"[Phase 2.5]   Step 5a: INSERT base aggregates (count, max/min filesize, max/min mtime)")
            cursor.execute('''
                INSERT INTO group_stats (
                    group_id, member_count,
                    max_filesize, min_filesize,
                    max_mtime, min_mtime
                )
                SELECT
                    dg.group_id,
                    COUNT(*),
                    MAX(i.filesize), MIN(i.filesize),
                    MAX(i.mtime), MIN(i.mtime)
                FROM duplicate_groups dg
                JOIN image_hashes i ON dg.image_id = i.id
                GROUP BY dg.group_id
            ''')
            n_gs_after_5a = cursor.execute("SELECT COUNT(*) FROM group_stats").fetchone()[0]
            print(f"[Phase 2.5]   Step 5a DONE: {n_gs_after_5a} group_stats rows inserted")

            # primary_folder: the dir_path with most members in each group (ties broken by path)
            print(f"[Phase 2.5]   Step 5b: UPDATE primary_folder (per-group most-populous dir_path)")
            cursor.execute('''
                UPDATE group_stats
                SET primary_folder = (
                    SELECT i.dir_path
                    FROM duplicate_groups dg
                    JOIN image_hashes i ON dg.image_id = i.id
                    WHERE dg.group_id = group_stats.group_id
                    GROUP BY i.dir_path
                    ORDER BY COUNT(*) DESC, i.dir_path ASC
                    LIMIT 1
                )
            ''')
            n_pf_null = cursor.execute("SELECT COUNT(*) FROM group_stats WHERE primary_folder IS NULL").fetchone()[0]
            print(f"[Phase 2.5]   Step 5b DONE: primary_folder NULL count = {n_pf_null}")

            # folder_dup_count: total duplicate files (across ALL groups) sharing this group's primary_folder
            # Sort key for "folder with most duplicates first"
            print(f"[Phase 2.5]   Step 5c: UPDATE folder_dup_count (cross-group aggregate)")
            cursor.execute('''
                UPDATE group_stats
                SET folder_dup_count = (
                    SELECT COUNT(*)
                    FROM duplicate_groups dg2
                    JOIN image_hashes i2 ON dg2.image_id = i2.id
                    WHERE i2.dir_path = group_stats.primary_folder
                )
            ''')
            try:
                top = cursor.execute(
                    "SELECT primary_folder, folder_dup_count FROM group_stats "
                    "ORDER BY folder_dup_count DESC LIMIT 5"
                ).fetchall()
                print(f"[Phase 2.5]   Step 5c DONE. Top-5 folder_dup_count:")
                for pf, cnt in top:
                    print(f"[Phase 2.5]     {cnt:6d}  {pf}")
            except Exception as e:
                print(f"[Phase 2.5]   Step 5c stats query failed (non-fatal): {e}")

            elapsed_step = time.time() - step_start
            print(f"[Phase 2.5] Step 5/5 DONE in {elapsed_step:.2f}s")

            # Update meta
            now = time.time()
            print(f"[Phase 2.5] Writing duplicate_finder_meta: threshold={threshold_percent}, "
                  f"same_folder_filter={same_folder_filter}, group_count={len(filtered_groups)}, at={now}")
            cursor.executemany(
                "INSERT OR REPLACE INTO duplicate_finder_meta (key, value) VALUES (?, ?)",
                [
                    ("materialized_threshold", str(threshold_percent)),
                    ("materialized_at", str(now)),
                    ("materialized_same_folder_filter", "1" if same_folder_filter else "0"),
                    ("materialized_group_count", str(len(filtered_groups))),
                ],
            )
            conn.commit()
            print(f"[Phase 2.5] COMMIT done")

            elapsed = time.time() - start_time
            print("=" * 80)
            print(f"[Phase 2.5] ✅ COMPLETE in {elapsed:.2f}s")
            print(f"[Phase 2.5]   groups               : {len(filtered_groups)}")
            print(f"[Phase 2.5]   members              : {len(dg_rows)}")
            print(f"[Phase 2.5]   whitelisted_dropped  : {whitelisted_dropped}")
            print(f"[Phase 2.5]   threshold_percent    : {threshold_percent}%")
            print(f"[Phase 2.5]   same_folder_filter   : {same_folder_filter}")
            print("=" * 80)
            cb(100, f"Complete: {len(filtered_groups)} groups")

            return {
                'groups_count': len(filtered_groups),
                'members_count': len(dg_rows),
                'whitelisted_dropped': whitelisted_dropped,
                'threshold_percent': threshold_percent,
                'same_folder_filter': same_folder_filter,
                'elapsed': elapsed,
                'stopped': False,
            }

        except Exception as e:
            conn.rollback()
            elapsed = time.time() - start_time
            print("=" * 80)
            print(f"[Phase 2.5] ❌ EXCEPTION after {elapsed:.2f}s: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            print("=" * 80)
            raise

    def get_materialization_meta(self) -> Dict:
        """Read current Phase 2.5 materialization state from duplicate_finder_meta."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT key, value FROM duplicate_finder_meta")
            rows = cursor.fetchall()
        except sqlite3.OperationalError:
            return {}
        return {k: v for k, v in rows}

    # ========== Incremental stats repair (Step 5) ==========

    def stats_collect_affected_before_mutation(self, image_ids: List[int]) -> Dict:
        """
        Capture data needed to repair group_stats after a set of image_ids gets
        removed from the materialized view (either via image_hashes delete, or
        via whitelist add). Call BEFORE any DB mutation.

        Returns:
            {
                'image_ids': [...],
                'affected_groups': [...],         # group_ids that contained these images
                'old_primary_folders': [...],     # primary_folder values BEFORE mutation
                'affected_folders': [...],        # dir_path of the images being removed
            }
        """
        if not image_ids:
            return {
                'image_ids': [],
                'affected_groups': [],
                'old_primary_folders': [],
                'affected_folders': [],
            }

        cur = self._get_connection().cursor()
        affected_groups: set = set()
        affected_folders: set = set()

        BATCH = 900
        for i in range(0, len(image_ids), BATCH):
            chunk = list(image_ids)[i:i + BATCH]
            ph = ','.join('?' * len(chunk))
            cur.execute(
                f"SELECT DISTINCT group_id FROM duplicate_groups WHERE image_id IN ({ph})",
                chunk,
            )
            affected_groups.update(r[0] for r in cur.fetchall())

            cur.execute(
                f"SELECT DISTINCT dir_path FROM image_hashes "
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
                f"SELECT DISTINCT primary_folder FROM group_stats "
                f"WHERE group_id IN ({ph}) AND primary_folder IS NOT NULL",
                chunk,
            )
            old_primary_folders.update(r[0] for r in cur.fetchall())

        print(f"[Stats Repair] CAPTURE: image_ids={len(image_ids)}, "
              f"affected_groups={len(affected_groups)}, "
              f"affected_folders={len(affected_folders)}, "
              f"old_primary_folders={len(old_primary_folders)}")

        return {
            'image_ids': list(image_ids),
            'affected_groups': list(affected_groups),
            'old_primary_folders': list(old_primary_folders),
            'affected_folders': list(affected_folders),
        }

    def stats_repair_after_mutation(
        self,
        affected: Dict,
        remove_from_groups: bool = False,
    ) -> Dict:
        """
        Repair group_stats + duplicate_groups for the affected groups.

        Args:
            affected: result of stats_collect_affected_before_mutation()
            remove_from_groups: if True, manually DELETE the image_ids from
                duplicate_groups. Use for whitelist case where image_hashes
                row stays put. For deletion case CASCADE has already done it.
        """
        start = time.time()
        cur = self._get_connection().cursor()

        image_ids = affected.get('image_ids', [])
        affected_groups = affected.get('affected_groups', [])
        old_primary_folders = affected.get('old_primary_folders', [])
        affected_folders = affected.get('affected_folders', [])

        if not affected_groups:
            elapsed = time.time() - start
            print(f"[Stats Repair] No affected groups; nothing to do ({elapsed:.3f}s)")
            return {
                'image_ids_processed': len(image_ids),
                'affected_groups': 0,
                'orphan_groups_deleted': 0,
                'survivor_groups_updated': 0,
                'folders_refreshed': 0,
                'elapsed': elapsed,
            }

        BATCH = 900

        # Step A: whitelist case — manually remove image_ids from duplicate_groups
        if remove_from_groups and image_ids:
            removed_dg_rows = 0
            for i in range(0, len(image_ids), BATCH):
                chunk = image_ids[i:i + BATCH]
                ph = ','.join('?' * len(chunk))
                cur.execute(
                    f"DELETE FROM duplicate_groups WHERE image_id IN ({ph})",
                    chunk,
                )
                removed_dg_rows += cur.rowcount
            print(f"[Stats Repair] (whitelist mode) removed {removed_dg_rows} rows from duplicate_groups")

        # Step B: classify affected groups into orphan (< 2 members) vs survivor
        orphan_groups: set = set()
        survivor_groups: set = set()

        for i in range(0, len(affected_groups), BATCH):
            chunk = affected_groups[i:i + BATCH]
            ph = ','.join('?' * len(chunk))
            cur.execute(
                f"SELECT gs.group_id, COALESCE(dg.cnt, 0) "
                f"FROM group_stats gs "
                f"LEFT JOIN ("
                f"  SELECT group_id, COUNT(*) AS cnt FROM duplicate_groups "
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

        # Step C: delete orphan groups from both tables
        if orphan_groups:
            for i in range(0, len(orphan_groups), BATCH):
                chunk = list(orphan_groups)[i:i + BATCH]
                ph = ','.join('?' * len(chunk))
                cur.execute(f"DELETE FROM duplicate_groups WHERE group_id IN ({ph})", chunk)
                cur.execute(f"DELETE FROM group_stats WHERE group_id IN ({ph})", chunk)
            print(f"[Stats Repair] dropped {len(orphan_groups)} orphan groups (< 2 members)")

        # Step D: recompute stats for survivors
        if survivor_groups:
            for i in range(0, len(survivor_groups), BATCH):
                chunk = list(survivor_groups)[i:i + BATCH]
                ph = ','.join('?' * len(chunk))
                cur.execute(f'''
                    UPDATE group_stats
                    SET member_count = (
                            SELECT COUNT(*) FROM duplicate_groups dg
                            WHERE dg.group_id = group_stats.group_id
                        ),
                        max_filesize = (
                            SELECT MAX(i.filesize) FROM duplicate_groups dg
                            JOIN image_hashes i ON dg.image_id = i.id
                            WHERE dg.group_id = group_stats.group_id
                        ),
                        min_filesize = (
                            SELECT MIN(i.filesize) FROM duplicate_groups dg
                            JOIN image_hashes i ON dg.image_id = i.id
                            WHERE dg.group_id = group_stats.group_id
                        ),
                        max_mtime = (
                            SELECT MAX(i.mtime) FROM duplicate_groups dg
                            JOIN image_hashes i ON dg.image_id = i.id
                            WHERE dg.group_id = group_stats.group_id
                        ),
                        min_mtime = (
                            SELECT MIN(i.mtime) FROM duplicate_groups dg
                            JOIN image_hashes i ON dg.image_id = i.id
                            WHERE dg.group_id = group_stats.group_id
                        ),
                        primary_folder = (
                            SELECT i.dir_path FROM duplicate_groups dg
                            JOIN image_hashes i ON dg.image_id = i.id
                            WHERE dg.group_id = group_stats.group_id
                            GROUP BY i.dir_path
                            ORDER BY COUNT(*) DESC, i.dir_path ASC
                            LIMIT 1
                        )
                    WHERE group_id IN ({ph})
                ''', chunk)
            print(f"[Stats Repair] re-aggregated {len(survivor_groups)} survivor groups")

        # Step E: refresh folder_dup_count for affected folders + old/new primary_folders
        new_primary_folders: set = set()
        if survivor_groups:
            for i in range(0, len(survivor_groups), BATCH):
                chunk = list(survivor_groups)[i:i + BATCH]
                ph = ','.join('?' * len(chunk))
                cur.execute(
                    f"SELECT DISTINCT primary_folder FROM group_stats "
                    f"WHERE group_id IN ({ph}) AND primary_folder IS NOT NULL",
                    chunk,
                )
                new_primary_folders.update(r[0] for r in cur.fetchall())

        folders_to_refresh = set(affected_folders) | set(old_primary_folders) | new_primary_folders
        if folders_to_refresh:
            folders_list = list(folders_to_refresh)
            for i in range(0, len(folders_list), BATCH):
                chunk = folders_list[i:i + BATCH]
                ph = ','.join('?' * len(chunk))
                cur.execute(f'''
                    UPDATE group_stats
                    SET folder_dup_count = (
                        SELECT COUNT(*)
                        FROM duplicate_groups dg2
                        JOIN image_hashes i2 ON dg2.image_id = i2.id
                        WHERE i2.dir_path = group_stats.primary_folder
                    )
                    WHERE primary_folder IN ({ph})
                ''', chunk)
            print(f"[Stats Repair] refreshed folder_dup_count for {len(folders_to_refresh)} folders")

        # Update meta timestamp
        cur.execute(
            "INSERT OR REPLACE INTO duplicate_finder_meta (key, value) VALUES (?, ?)",
            ("last_incremental_update", str(time.time())),
        )
        self._get_connection().commit()

        elapsed = time.time() - start
        result = {
            'image_ids_processed': len(image_ids),
            'affected_groups': len(affected_groups),
            'orphan_groups_deleted': len(orphan_groups),
            'survivor_groups_updated': len(survivor_groups),
            'folders_refreshed': len(folders_to_refresh),
            'elapsed': elapsed,
        }
        print(f"[Stats Repair] DONE in {elapsed:.3f}s: {result}")
        return result

    # ========== Phase 3: Get Duplicates ==========

    # SQL injection guard: only these columns may be plugged into ORDER BY
    PHASE3_ALLOWED_SORTS = {
        'folder_dup_count',
        'max_filesize',
        'min_filesize',
        'max_mtime',
        'min_mtime',
        'member_count',
    }

    def phase3_get_duplicates(
        self,
        threshold_percent: int = 80,
        progress_callback: Optional[Callable] = None,
        page: int = 1,
        page_size: int = 100,
        sort_by: str = 'folder_dup_count',
        sort_order: str = 'desc',
        folder_paths: Optional[List[str]] = None,
    ) -> Dict:
        """
        Phase 3: Read materialized duplicate groups (strict mode).

        Requires phase2_5_materialize_groups() to have run first. Returns a
        structured error marker (error='no_materialization' or
        error='threshold_mismatch') if state is missing or stale — the caller
        maps these to HTTP 409.

        Args:
            threshold_percent:  UI similarity threshold (must match materialized)
            page:               1-indexed page number (0 = return all)
            page_size:          groups per page
            sort_by:            column from PHASE3_ALLOWED_SORTS
            sort_order:         'asc' or 'desc'
            folder_paths:       scan roots, used for display_path computation
        """
        start_time = time.time()
        conn = self._get_connection()
        cursor = conn.cursor()

        # 1. Strict materialization check
        meta = self.get_materialization_meta()
        empty_page = {
            'groups': [],
            'total_groups': 0,
            'total_duplicates': 0,
            'current_page': page if page > 0 else 1,
            'page_size': page_size,
            'total_pages': 0,
            'stopped': False,
            'materialization_meta': meta,
        }

        if not meta or 'materialized_threshold' not in meta:
            print(f"[Phase 3] no materialization meta; returning error marker")
            return {
                **empty_page,
                'error': 'no_materialization',
                'message': 'No materialized groups. Please run Phase 2.5 first.',
                'elapsed': time.time() - start_time,
            }

        try:
            materialized_threshold = int(meta['materialized_threshold'])
        except (TypeError, ValueError):
            materialized_threshold = -1

        if materialized_threshold != threshold_percent:
            print(f"[Phase 3] threshold mismatch: materialized={materialized_threshold}, requested={threshold_percent}")
            return {
                **empty_page,
                'error': 'threshold_mismatch',
                'message': (
                    f'Groups materialized at {materialized_threshold}%, but UI requests '
                    f'{threshold_percent}%. Re-run Phase 2.5 to refresh.'
                ),
                'materialized_threshold': materialized_threshold,
                'current_threshold': threshold_percent,
                'elapsed': time.time() - start_time,
            }

        # 2. Validate sort column (whitelist; SQL injection guard)
        if sort_by not in self.PHASE3_ALLOWED_SORTS:
            sort_by = 'folder_dup_count'
        sort_order_sql = 'DESC' if str(sort_order).lower() == 'desc' else 'ASC'

        # 3. Totals (single fast aggregate, both indexes already in place)
        cursor.execute("SELECT COUNT(*), COALESCE(SUM(member_count), 0) FROM group_stats")
        total_groups_all, total_duplicates = cursor.fetchone()
        total_duplicates = int(total_duplicates)

        if total_groups_all == 0:
            return {
                **empty_page,
                'total_pages': 0,
                'elapsed': time.time() - start_time,
                'sort_by': sort_by,
                'sort_order': sort_order_sql.lower(),
            }

        # 4. Page the group_ids — pagination happens entirely in SQL
        if page > 0:
            import math
            total_pages = max(1, math.ceil(total_groups_all / page_size)) if page_size > 0 else 1
            offset = max(0, (page - 1) * page_size)
            cursor.execute(
                f"SELECT group_id FROM group_stats "
                f"ORDER BY {sort_by} {sort_order_sql}, group_id ASC "
                f"LIMIT ? OFFSET ?",
                (page_size, offset),
            )
        else:
            total_pages = 1
            cursor.execute(
                f"SELECT group_id FROM group_stats "
                f"ORDER BY {sort_by} {sort_order_sql}, group_id ASC"
            )

        page_group_ids = [r[0] for r in cursor.fetchall()]
        if not page_group_ids:
            return {
                'groups': [],
                'total_groups': total_groups_all,
                'total_duplicates': total_duplicates,
                'current_page': page if page > 0 else 1,
                'page_size': page_size,
                'total_pages': total_pages,
                'elapsed': time.time() - start_time,
                'stopped': False,
                'materialization_meta': meta,
                'sort_by': sort_by,
                'sort_order': sort_order_sql.lower(),
            }

        # 5. Bulk-fetch members + image details for THIS page only (one JOIN, batched
        #    to stay under SQLite's 999 variable limit)
        images_by_group: Dict[int, List[Dict]] = {gid: [] for gid in page_group_ids}
        batch_size = 900
        for i in range(0, len(page_group_ids), batch_size):
            chunk = page_group_ids[i:i + batch_size]
            placeholders = ','.join('?' * len(chunk))
            cursor.execute(
                f"SELECT dg.group_id, i.id, i.filename, i.filesize, i.file_path, "
                f"       i.phash, i.resolution "
                f"FROM duplicate_groups dg "
                f"JOIN image_hashes i ON dg.image_id = i.id "
                f"WHERE dg.group_id IN ({placeholders})",
                chunk,
            )
            for gid, img_id, filename, filesize, file_path, phash, resolution in cursor.fetchall():
                images_by_group[gid].append({
                    'id': img_id,
                    'filename': filename,
                    'filesize': filesize,
                    'file_path': file_path,
                    'phash': phash,
                    'resolution': resolution,
                })

        # 6. Compute display_path for THIS page only (current page ≈ a few hundred images;
        #    folder_paths is fresh from settings each request — no staleness)
        if folder_paths is None:
            folder_paths = []
        folder_abs_list = []
        for folder in folder_paths:
            try:
                folder_abs_list.append(os.path.abspath(folder))
            except Exception:
                continue

        def compute_display_path(file_path: str) -> str:
            if not file_path:
                return '/'
            try:
                file_path_abs = os.path.abspath(file_path)
                for folder_abs in folder_abs_list:
                    if file_path_abs == folder_abs or file_path_abs.startswith(folder_abs + os.sep):
                        rel = os.path.relpath(file_path, folder_abs)
                        d = os.path.dirname(rel)
                        return d if d and d != '.' else '/'
            except Exception:
                pass
            return os.path.dirname(file_path)

        for imgs in images_by_group.values():
            for img in imgs:
                img['display_path'] = compute_display_path(img['file_path'])

        # 7. Assemble result preserving the SQL-ordered group_id sequence
        result_groups = [images_by_group[gid] for gid in page_group_ids if images_by_group[gid]]

        elapsed = time.time() - start_time
        print(f"[Phase 3] ✅ Page {page}/{total_pages}: {len(result_groups)} groups in {elapsed * 1000:.0f}ms "
              f"(sort_by={sort_by} {sort_order_sql})")

        return {
            'groups': result_groups,
            'total_groups': total_groups_all,
            'total_duplicates': total_duplicates,
            'current_page': page if page > 0 else 1,
            'page_size': page_size,
            'total_pages': total_pages if page > 0 else 1,
            'elapsed': elapsed,
            'stopped': False,
            'materialization_meta': meta,
            'sort_by': sort_by,
            'sort_order': sort_order_sql.lower(),
        }

    def _build_groups(self, edges: List[tuple]) -> List[List[int]]:
        """Build connected components from edge list using BFS"""
        # Build adjacency list
        graph = {}
        for a, b, _ in edges:
            graph.setdefault(a, []).append(b)
            graph.setdefault(b, []).append(a)

        visited = set()
        groups = []

        for node in graph:
            if node in visited:
                continue

            # BFS
            group = []
            queue = [node]
            visited.add(node)

            while queue:
                current = queue.pop(0)
                group.append(current)

                for neighbor in graph.get(current, []):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)

            if len(group) >= 2:
                groups.append(group)

        return groups
