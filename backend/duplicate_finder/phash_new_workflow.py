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
    from .phash_cache import _compute_single_hash, CACHE_DB
except ImportError:
    from phash_cache import _compute_single_hash, CACHE_DB


def _compute_similarities_batch(args):
    """
    Compute similarities for a batch of pending images.
    This function is used by multiprocessing.

    Args:
        args: tuple of (pending_batch, all_images, threshold_distance)

    Returns:
        List of similarity tuples: (id_a, id_b, distance)
    """
    import os
    import multiprocessing

    pending_batch, all_images, threshold_distance = args
    similarities = []

    pid = os.getpid()
    worker_name = multiprocessing.current_process().name

    print(f"[Worker {worker_name} PID={pid}] START batch: {len(pending_batch)} pending vs {len(all_images)} total images")

    def hamming_distance(hash1: str, hash2: str) -> int:
        return bin(int(hash1, 16) ^ int(hash2, 16)).count('1')

    processed = 0
    for pending_id, pending_phash in pending_batch:
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


class DuplicateFinderWorkflow:
    """
    New workflow manager for duplicate finder.
    Implements 3-phase process with stop control.
    """

    def __init__(self, db_path: str = None):
        self.db_path = Path(db_path) if db_path else CACHE_DB
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

        for file_path in file_paths:
            if self._stop_event.is_set():
                print("[Phase 1] Stop signal received")
                raise InterruptedError("Phase 1 stopped by user")

            status = db_status.get(file_path)
            if status == 'computed':
                skipped_count += 1
            elif status is None:
                # New file, needs phash computation
                files_to_compute.append(file_path)
            # status='pending' will also be computed

        print(f"[Phase 1] Step 2 DONE: Skipped {skipped_count} computed files, need to compute {len(files_to_compute)} files")

        # Step 3: Compute phash for new/pending files
        added_count = 0
        error_files = []

        if files_to_compute:
            from .settings_manager import settings_manager
            num_workers = settings_manager.get_max_cpu_cores()
            BATCH_SIZE = 100

            print(f"[Phase 1] Step 3: Settings check - max_cpu_cores from settings: {settings_manager.get_settings().get('max_cpu_cores', 'NOT_SET')}")
            print(f"[Phase 1] Step 3: Computing phash using {num_workers} workers (from get_max_cpu_cores()), batch size {BATCH_SIZE}...")

            with Pool(processes=num_workers) as pool:
                batch_buffer = []
                completed = 0

                for result in pool.imap_unordered(_compute_single_hash, files_to_compute):
                    if self._stop_event.is_set():
                        print("[Phase 1 Main] STOP detected! Terminating pool...")
                        pool.terminate()
                        pool.join()
                        print("[Phase 1 Main] Pool terminated")
                        raise InterruptedError("Phase 1 stopped during hash computation")

                    filename = os.path.basename(result.get('file_path', 'unknown'))

                    if result.get('error'):
                        error_files.append(result)
                        print(f"[Phase 1 Main] Received ERROR for: {filename}")
                    else:
                        batch_buffer.append(result)
                        print(f"[Phase 1 Main] Received SUCCESS for: {filename} (batch: {len(batch_buffer)}/{BATCH_SIZE})")

                        if len(batch_buffer) >= BATCH_SIZE:
                            self._insert_images_batch(batch_buffer)
                            added_count += len(batch_buffer)
                            print(f"[Phase 1 Main] Inserted batch of {len(batch_buffer)} images: {added_count} total so far")
                            batch_buffer = []

                    completed += 1
                    if completed % 10 == 0:  # Summary log every 10 files
                        print(f"[Phase 1 Main] Progress Summary: {completed}/{len(files_to_compute)}, added={added_count}, errors={len(error_files)}, stop_event={self._stop_event.is_set()}")
                    if progress_callback and completed % 10 == 0:  # More frequent updates
                        progress_callback(completed, len(files_to_compute), f"Computing phash... ({completed}/{len(files_to_compute)})")

                # Final batch
                if batch_buffer:
                    self._insert_images_batch(batch_buffer)
                    added_count += len(batch_buffer)
        else:
            # No files to compute, send completion progress
            print(f"[Phase 1] No files to compute (all skipped)")
            if progress_callback:
                progress_callback(len(file_paths), len(file_paths), "All files already computed")

        elapsed = time.time() - start_time
        print(f"[Phase 1] ✅ Completed in {elapsed:.1f}s: +{added_count}, -{removed_count}, skipped {skipped_count}")

        # Send final 100% progress
        if progress_callback:
            total = len(file_paths)
            progress_callback(total, total, f"Complete: +{added_count}, -{removed_count}, skipped {skipped_count}")

        return {
            'added': added_count,
            'removed': removed_count,
            'skipped': skipped_count,
            'errors': error_files,
            'elapsed': elapsed
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

        # Multi-process distance computation
        from .settings_manager import settings_manager
        num_workers = settings_manager.get_max_cpu_cores()
        # Fixed batch size: 100 pending images per batch
        # This ensures we commit every 100 pending images (not by similarity count)
        batch_size = 100

        print(f"[Phase 2] Step 3: Settings check - max_cpu_cores from settings: {settings_manager.get_settings().get('max_cpu_cores', 'NOT_SET')}")
        print(f"[Phase 2] Step 3: Starting multiprocessing with {num_workers} workers, FIXED batch size {batch_size}, total {(len(pending_images) + batch_size - 1) // batch_size} batches")

        # Split pending images into batches
        batches = []
        for i in range(0, len(pending_images), batch_size):
            batch = pending_images[i:i + batch_size]
            batches.append((batch, all_images, threshold_distance))

        similarities_count = 0
        processed_count = 0

        # Process batches in parallel
        # Each batch is 100 pending images, commit after EACH batch completes
        print(f"[Phase 2 Main] Starting to process {len(batches)} batches (each batch = 100 pending images, commit after each batch)...")
        with Pool(processes=num_workers) as pool:
            for batch_idx, batch_similarities in enumerate(pool.imap(_compute_similarities_batch, batches)):
                if self._stop_event.is_set():
                    print("[Phase 2 Main] STOP detected! Terminating pool...")
                    pool.terminate()
                    pool.join()
                    print("[Phase 2 Main] Pool terminated")
                    raise InterruptedError("Phase 2 stopped by user")

                # Get the pending images for this batch
                batch_pending = batches[batch_idx][0]
                batch_size_actual = len(batch_pending)

                # Insert all similarities from this batch
                if batch_similarities:
                    cursor.executemany('''
                        INSERT OR REPLACE INTO phash_similarities
                        (image_id_a, image_id_b, threshold, distance)
                        VALUES (?, ?, 80, ?)
                    ''', batch_similarities)

                # Update status for all images in this batch
                pending_ids = [(pid,) for pid, _ in batch_pending]
                cursor.executemany("UPDATE image_hashes SET status = 'computed' WHERE id = ?", pending_ids)

                # Commit after each batch (every ~100 pending images)
                conn.commit()
                processed_count += batch_size_actual
                similarities_count += len(batch_similarities)
                print(f"[Phase 2 Main] ✓ Committed batch {batch_idx+1}/{len(batches)}: {len(batch_similarities)} similarities + {batch_size_actual} status updates (total: {processed_count}/{len(pending_images)} images, {similarities_count} similarities)")

                # Progress update every 10 batches
                if (batch_idx + 1) % 10 == 0 or (batch_idx + 1) == len(batches):
                    if progress_callback:
                        progress_callback(processed_count, len(pending_images), f"Building similarities... ({processed_count}/{len(pending_images)})")

                    print(f"[Phase 2 Main] Progress Summary: batch {batch_idx+1}/{len(batches)}, processed {processed_count}/{len(pending_images)} images, found {similarities_count} similarities, stop_event={self._stop_event.is_set()}")

        elapsed = time.time() - start_time
        print(f"[Phase 2] ✅ Completed in {elapsed:.1f}s: processed {processed_count}, found {similarities_count} similarities")

        # Send final 100% progress
        if progress_callback:
            total = len(pending_images)
            progress_callback(total, total, f"Complete: processed {processed_count}, found {similarities_count} similarities")

        return {
            'processed': processed_count,
            'similarities_found': similarities_count,
            'elapsed': elapsed
        }

    def _hamming_distance(self, hash1: str, hash2: str) -> int:
        """Compute hamming distance between two phash strings"""
        return bin(int(hash1, 16) ^ int(hash2, 16)).count('1')

    # ========== Phase 3: Get Duplicates ==========

    def phase3_get_duplicates(
        self,
        threshold_percent: int = 90,  # UI setting
        progress_callback: Optional[Callable] = None
    ) -> Dict:
        """
        Phase 3: Get duplicate groups
        - Query phash_similarities where distance matches threshold
        - Build connected components (groups)
        - Filter out whitelist images

        Args:
            threshold_percent: Similarity threshold (80, 85, 90, etc.)
            progress_callback: Optional callback(current, total, message)

        Returns:
            {
                'groups': List[List[Dict]],  # Each group contains image info
                'total_groups': int,
                'total_duplicates': int,
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

        # Get full image info for each group
        result_groups = []
        total_groups = len(groups)
        for group_idx, group_ids in enumerate(groups):
            if self._stop_event.is_set():
                raise InterruptedError("Phase 3 stopped by user")

            group_images = []
            for image_id in group_ids:
                cursor.execute('''
                    SELECT id, filename, filesize, file_path, phash, resolution
                    FROM image_hashes WHERE id = ?
                ''', (image_id,))
                row = cursor.fetchone()
                if row:
                    group_images.append({
                        'id': row[0],
                        'filename': row[1],
                        'filesize': row[2],
                        'file_path': row[3],
                        'phash': row[4],
                        'resolution': row[5]
                    })

            if len(group_images) >= 2:
                result_groups.append(group_images)

            # Progress update every 10 groups
            if progress_callback and (group_idx + 1) % 10 == 0:
                progress_callback(group_idx + 1, total_groups, f"Loading groups... ({group_idx + 1}/{total_groups})")

        elapsed = time.time() - start_time
        total_duplicates = sum(len(g) for g in result_groups)
        print(f"[Phase 3] ✅ Completed in {elapsed:.1f}s: {len(result_groups)} groups, {total_duplicates} total duplicates")

        # Send final 100% progress
        if progress_callback and total_groups > 0:
            progress_callback(total_groups, total_groups, f"Complete: {len(result_groups)} groups, {total_duplicates} duplicates")

        return {
            'groups': result_groups,
            'total_groups': len(result_groups),
            'total_duplicates': total_duplicates,
            'elapsed': elapsed
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
