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
from typing import List, Dict, Optional, Callable
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
                UNIQUE (filename, filesize, file_path)
            )
        ''')

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_phash ON image_hashes(phash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_filename_filesize ON image_hashes(filename, filesize)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_status ON image_hashes(status)')

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
        progress_callback: Optional[Callable] = None
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
        print(f"[Phase 1] Step 1: Checking for missing files in DB...")
        if progress_callback:
            progress_callback(0, len(file_paths), "Checking missing files...")

        cursor.execute("SELECT id, file_path FROM image_hashes")
        db_files = cursor.fetchall()
        print(f"[Phase 1] Found {len(db_files)} files in DB")

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
            filename = Path(item['file_path']).name
            batch_data.append((filename, item['filesize'], item['file_path'], item['phash'], item['resolution']))

        # Use executemany for better performance
        cursor.executemany('''
            INSERT OR IGNORE INTO image_hashes
            (filename, filesize, file_path, phash, resolution, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
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

    # ========== Phase 3: Get Duplicates ==========

    def phase3_get_duplicates(
        self,
        threshold_percent: int = 90,  # UI setting
        progress_callback: Optional[Callable] = None,
        page: int = 1,  # Pagination: page number (1-indexed, 0=all groups)
        page_size: int = 20,  # Pagination: groups per page
        folder_paths: Optional[List[str]] = None  # For display_path calculation
    ) -> Dict:
        """
        Phase 3: Get duplicate groups (with pagination support)
        - Query phash_similarities where distance matches threshold
        - Build connected components (groups)
        - Filter out whitelist images
        - Return paginated results

        Args:
            threshold_percent: Similarity threshold (80, 85, 90, etc.)
            progress_callback: Optional callback(current, total, message)
            page: Page number (1-indexed, 0=return all groups)
            page_size: Number of groups per page

        Returns:
            {
                'groups': List[List[Dict]],  # Current page groups (or all if page=0)
                'total_groups': int,  # Total number of groups (all pages)
                'total_duplicates': int,  # Total duplicates in all groups
                'current_page': int,
                'page_size': int,
                'total_pages': int,
                'elapsed': float
            }
        """
        self.clear_stop()
        start_time = time.time()
        conn = self._get_connection()
        cursor = conn.cursor()

        # Convert threshold % to distance
        max_distance = int(64 * (100 - threshold_percent) / 100)
        print(f"[Phase 3] Getting duplicates (threshold {threshold_percent}% = distance ≤ {max_distance})...")

        # Get similarities
        cursor.execute('''
            SELECT image_id_a, image_id_b, distance
            FROM phash_similarities
            WHERE threshold = 80 AND distance <= ?
        ''', (max_distance,))
        edges = cursor.fetchall()

        print(f"[Phase 3] Found {len(edges)} similar pairs")

        # Get whitelist
        cursor.execute("SELECT image_id FROM whitelist")
        whitelist_ids = {row[0] for row in cursor.fetchall()}

        # Filter out whitelist
        filtered_edges = [
            (a, b, d) for a, b, d in edges
            if a not in whitelist_ids and b not in whitelist_ids
        ]

        print(f"[Phase 3] After whitelist filter: {len(filtered_edges)} pairs")

        # Build graph and find connected components
        groups = self._build_groups(filtered_edges)

        # Filter out whitelisted groups
        print(f"[Phase 3] Checking for whitelisted groups...")
        cache = PHashCache(str(self.db_path))

        filtered_groups = []
        for group in groups:
            if not cache.is_group_whitelisted(group):
                filtered_groups.append(group)

        whitelisted_count = len(groups) - len(filtered_groups)
        if whitelisted_count > 0:
            print(f"[Phase 3] Filtered out {whitelisted_count} whitelisted groups")
        groups = filtered_groups

        # Get full image info for each group - OPTIMIZED: bulk query instead of N individual queries
        result_groups = []
        total_groups = len(groups)

        # Collect all unique image IDs from all groups
        all_duplicate_ids = list(set(img_id for group in groups for img_id in group))

        print(f"[Phase 3] Fetching details for {len(all_duplicate_ids)} unique duplicate images (from {total_groups} groups)...")

        if all_duplicate_ids:
            # Bulk query with batching to avoid SQLite's 999 variable limit
            # SQLite has SQLITE_MAX_VARIABLE_NUMBER limit (default 999)
            batch_size = 900  # Use 900 to be safe
            all_images_dict = {}

            for i in range(0, len(all_duplicate_ids), batch_size):
                batch = all_duplicate_ids[i:i + batch_size]
                placeholders = ','.join('?' * len(batch))
                cursor.execute(f'''
                    SELECT id, filename, filesize, file_path, phash, resolution
                    FROM image_hashes
                    WHERE id IN ({placeholders})
                ''', batch)

                # Add to lookup dictionary
                for row in cursor.fetchall():
                    all_images_dict[row[0]] = {
                        'id': row[0],
                        'filename': row[1],
                        'filesize': row[2],
                        'file_path': row[3],
                        'phash': row[4],
                        'resolution': row[5]
                    }

                if len(all_duplicate_ids) > batch_size:
                    print(f"[Phase 3] Fetched batch {i // batch_size + 1}/{(len(all_duplicate_ids) + batch_size - 1) // batch_size} ({len(batch)} images)")

            print(f"[Phase 3] Fetched {len(all_images_dict)} image details, now assembling groups...")

            # Get folder_paths (scan folders) for display_path calculation - use them directly as root
            try:
                if not folder_paths:
                    print(f"[Phase 3] Warning: No folder_paths provided, display_path will use absolute paths")
                    folder_paths = []

                print(f"[Phase 3] Adding display_path to {len(all_images_dict)} images...")
                print(f"[Phase 3] Using {len(folder_paths)} scan folders as root: {folder_paths}")

                # Add display_path to each image
                for img_id, img in all_images_dict.items():
                    file_path = img.get('file_path', '')
                    if not file_path:
                        img['display_path'] = '/'
                        continue

                    # Find the scan folder that contains this file (use it as root)
                    scan_folder = None
                    for folder in folder_paths:
                        try:
                            folder_abs = os.path.abspath(folder)
                            file_path_abs = os.path.abspath(file_path)
                            if file_path_abs.startswith(folder_abs + os.sep) or file_path_abs == folder_abs:
                                scan_folder = folder_abs
                                break
                        except Exception as e:
                            print(f"[Phase 3] Warning: Error checking path {file_path}: {e}")
                            continue

                    if scan_folder:
                        # Calculate relative path from scan folder
                        try:
                            rel_path = os.path.relpath(file_path, scan_folder)
                            # Remove filename, keep only directory path
                            dir_path = os.path.dirname(rel_path)
                            img['display_path'] = dir_path if dir_path and dir_path != '.' else '/'
                        except (ValueError, Exception) as e:
                            # Fallback
                            print(f"[Phase 3] Warning: Cannot calculate relative path for {file_path}: {e}")
                            img['display_path'] = os.path.dirname(file_path)
                    else:
                        # Fallback: use absolute directory path
                        img['display_path'] = os.path.dirname(file_path)

                print(f"[Phase 3] Display paths added successfully")

            except Exception as e:
                print(f"[Phase 3] Error adding display_path, using fallback: {e}")
                import traceback
                traceback.print_exc()
                # Fallback: add simple display_path to all images
                for img in all_images_dict.values():
                    img['display_path'] = os.path.dirname(img.get('file_path', ''))

            # Assemble groups from lookup dictionary (fast, in-memory operation)
            stop_requested = False
            for group_idx, group_ids in enumerate(groups):
                if self._stop_event.is_set():
                    print(f"[Phase 3] ⏸️ Stop requested, returning partial results...")
                    stop_requested = True
                    break  # Exit early, return partial results

                group_images = [all_images_dict[img_id] for img_id in group_ids if img_id in all_images_dict]

                if len(group_images) >= 2:
                    result_groups.append(group_images)

                    # Progress update every 10 groups
                if progress_callback and (group_idx + 1) % 10 == 0:
                    progress_callback(group_idx + 1, total_groups, f"Loading groups... ({group_idx + 1}/{total_groups})")
        else:
            print(f"[Phase 3] No duplicate images to fetch")
            stop_requested = False

        # Sort groups by directory path first, then by filename
        if result_groups:
            def get_sort_key(group):
                if not group:
                    return ('', '')
                file_path = group[0].get('file_path', '')
                filename = group[0].get('filename', '')
                dir_path = os.path.dirname(file_path)
                return (dir_path, filename)

            result_groups.sort(key=get_sort_key)
            print(f"[Phase 3] Groups sorted by path and filename")

        elapsed = time.time() - start_time
        total_duplicates = sum(len(g) for g in result_groups)
        total_groups_all = len(result_groups)

        # Apply pagination
        if page > 0:  # page=0 means return all groups
            import math
            total_pages = math.ceil(total_groups_all / page_size) if page_size > 0 else 1
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size

            paginated_groups = result_groups[start_idx:end_idx]

            # Calculate how many files are being returned
            paginated_file_count = sum(len(g) for g in paginated_groups)

            print(f"[Phase 3] 📄 Pagination Applied:")
            print(f"[Phase 3]   - Page: {page}/{total_pages}")
            print(f"[Phase 3]   - Total groups in DB: {total_groups_all}")
            print(f"[Phase 3]   - Groups returned: {len(paginated_groups)} (groups {start_idx+1}-{min(end_idx, total_groups_all)})")
            print(f"[Phase 3]   - Files returned: {paginated_file_count} files (out of {total_duplicates} total)")
        else:
            # Return all groups
            paginated_groups = result_groups
            total_pages = 1
            print(f"[Phase 3] 📄 Returning all {total_groups_all} groups (pagination disabled)")

        if stop_requested:
            print(f"[Phase 3] ⏸️ Stopped by user in {elapsed:.1f}s: {total_groups_all} groups loaded, {total_duplicates} duplicates")
        else:
            print(f"[Phase 3] ✅ Completed in {elapsed:.1f}s: {total_groups_all} groups, {total_duplicates} total duplicates")

        # Send final progress
        if progress_callback:
            if stop_requested:
                progress_callback(total_groups_all, total_groups, f"Stopped: {total_groups_all}/{total_groups} groups")
            elif total_groups > 0:
                progress_callback(total_groups, total_groups, f"Complete: {total_groups_all} groups, {total_duplicates} duplicates")

        return {
            'groups': paginated_groups,
            'total_groups': total_groups_all,
            'total_duplicates': total_duplicates,
            'current_page': page if page > 0 else 1,
            'page_size': page_size,
            'total_pages': total_pages if page > 0 else 1,
            'elapsed': elapsed,
            'stopped': stop_requested
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
