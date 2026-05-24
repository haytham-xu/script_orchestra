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
from multiprocessing import Pool, cpu_count
import threading

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
    pending_batch, all_images, threshold_distance = args
    similarities = []

    def hamming_distance(hash1: str, hash2: str) -> int:
        return bin(int(hash1, 16) ^ int(hash2, 16)).count('1')

    for pending_id, pending_phash in pending_batch:
        for other_id, other_phash in all_images:
            if pending_id == other_id:
                continue

            distance = hamming_distance(pending_phash, other_phash)
            if distance <= threshold_distance:
                # Ensure id_a < id_b
                id_a, id_b = (pending_id, other_id) if pending_id < other_id else (other_id, pending_id)
                similarities.append((id_a, id_b, distance))

    return similarities


class DuplicateFinderWorkflow:
    """
    New workflow manager for duplicate finder.
    Implements 3-phase process with stop control.
    """

    def __init__(self, db_path: str = None):
        self.db_path = Path(db_path) if db_path else CACHE_DB
        self._conn = None
        self._stop_event = threading.Event()
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
        self._stop_event.set()

    def clear_stop(self):
        """Clear stop signal"""
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

        print(f"[Phase 1] Refreshing image table for {len(file_paths)} files...")

        # Step 1: Remove missing files from DB
        if progress_callback:
            progress_callback(0, len(file_paths), "Checking missing files...")

        cursor.execute("SELECT id, file_path FROM image_hashes")
        db_files = cursor.fetchall()
        db_file_set = {file_path for _, file_path in db_files}
        fs_file_set = set(file_paths)

        missing_files = db_file_set - fs_file_set
        removed_count = 0
        for db_id, file_path in db_files:
            if file_path in missing_files:
                cursor.execute("DELETE FROM image_hashes WHERE id = ?", (db_id,))
                removed_count += 1

        conn.commit()
        print(f"[Phase 1] Removed {removed_count} missing files from DB")

        # Step 2: Check existing files
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

        print(f"[Phase 1] Skipped {skipped_count} computed files, computing {len(files_to_compute)} new files")

        # Step 3: Compute phash for new/pending files
        added_count = 0
        error_files = []

        if files_to_compute:
            from .settings_manager import settings_manager
            num_workers = settings_manager.get_max_cpu_cores()
            BATCH_SIZE = 100

            with Pool(processes=num_workers) as pool:
                batch_buffer = []
                completed = 0

                for result in pool.imap_unordered(_compute_single_hash, files_to_compute):
                    if self._stop_event.is_set():
                        pool.terminate()
                        pool.join()
                        raise InterruptedError("Phase 1 stopped during hash computation")

                    if result.get('error'):
                        error_files.append(result)
                    else:
                        batch_buffer.append(result)

                        if len(batch_buffer) >= BATCH_SIZE:
                            self._insert_images_batch(batch_buffer)
                            added_count += len(batch_buffer)
                            batch_buffer = []

                    completed += 1
                    if progress_callback and completed % 100 == 0:
                        progress_callback(completed, len(files_to_compute), f"Computing phash... ({completed}/{len(files_to_compute)})")

                # Final batch
                if batch_buffer:
                    self._insert_images_batch(batch_buffer)
                    added_count += len(batch_buffer)

        elapsed = time.time() - start_time
        print(f"[Phase 1] ✅ Completed in {elapsed:.1f}s: +{added_count}, -{removed_count}, skipped {skipped_count}")

        return {
            'added': added_count,
            'removed': removed_count,
            'skipped': skipped_count,
            'errors': error_files,
            'elapsed': elapsed
        }

    def _insert_images_batch(self, batch: List[Dict]):
        """Insert batch of images with status='pending'"""
        conn = self._get_connection()
        cursor = conn.cursor()

        for item in batch:
            filename = Path(item['file_path']).name
            cursor.execute('''
                INSERT OR IGNORE INTO image_hashes
                (filename, filesize, file_path, phash, resolution, status)
                VALUES (?, ?, ?, ?, ?, 'pending')
            ''', (filename, item['filesize'], item['file_path'], item['phash'], item['resolution']))

        conn.commit()

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

        print(f"[Phase 2] Building similarities (threshold distance ≤ {threshold_distance})...")

        # Get pending images
        cursor.execute("SELECT id, phash FROM image_hashes WHERE status = 'pending'")
        pending_images = cursor.fetchall()

        if not pending_images:
            print("[Phase 2] No pending images, nothing to do")
            return {'processed': 0, 'similarities_found': 0, 'elapsed': 0}

        # Get all images (for distance comparison)
        cursor.execute("SELECT id, phash FROM image_hashes")
        all_images = cursor.fetchall()

        print(f"[Phase 2] Processing {len(pending_images)} pending images against {len(all_images)} total images")

        # Multi-process distance computation
        from .settings_manager import settings_manager
        num_workers = settings_manager.get_max_cpu_cores()
        batch_size = max(1, len(pending_images) // (num_workers * 4))  # Split into 4x workers batches

        print(f"[Phase 2] Using {num_workers} workers with batch size {batch_size}")

        # Split pending images into batches
        batches = []
        for i in range(0, len(pending_images), batch_size):
            batch = pending_images[i:i + batch_size]
            batches.append((batch, all_images, threshold_distance))

        similarities_count = 0
        processed_count = 0
        pending_ids_to_mark = []

        # Process batches in parallel
        with Pool(processes=num_workers) as pool:
            for batch_idx, batch_similarities in enumerate(pool.imap(_compute_similarities_batch, batches)):
                if self._stop_event.is_set():
                    pool.terminate()
                    pool.join()
                    raise InterruptedError("Phase 2 stopped by user")

                # Insert similarities in batch
                if batch_similarities:
                    cursor.executemany('''
                        INSERT OR REPLACE INTO phash_similarities
                        (image_id_a, image_id_b, threshold, distance)
                        VALUES (?, ?, 80, ?)
                    ''', batch_similarities)
                    similarities_count += len(batch_similarities)

                # Mark batch images as computed
                batch_pending = batches[batch_idx][0]
                for pending_id, _ in batch_pending:
                    pending_ids_to_mark.append((pending_id,))
                    processed_count += 1

                # Commit every 10 batches
                if (batch_idx + 1) % 10 == 0:
                    cursor.executemany("UPDATE image_hashes SET status = 'computed' WHERE id = ?", pending_ids_to_mark)
                    conn.commit()
                    pending_ids_to_mark = []

                    if progress_callback:
                        progress_callback(processed_count, len(pending_images), f"Building similarities... ({processed_count}/{len(pending_images)})")

                    print(f"[Phase 2] Progress: {processed_count}/{len(pending_images)}, found {similarities_count} similarities")

        # Final commit for remaining marks
        if pending_ids_to_mark:
            cursor.executemany("UPDATE image_hashes SET status = 'computed' WHERE id = ?", pending_ids_to_mark)

        conn.commit()

        elapsed = time.time() - start_time
        print(f"[Phase 2] ✅ Completed in {elapsed:.1f}s: processed {processed_count}, found {similarities_count} similarities")

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
