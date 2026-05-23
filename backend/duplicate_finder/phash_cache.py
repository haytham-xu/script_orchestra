"""
Perceptual Hash Cache Manager

Uses SQLite to cache image hashes for fast duplicate detection.
"""
import sqlite3
import os
from pathlib import Path
from PIL import Image
import imagehash
from typing import Optional, Dict, List, Tuple
from multiprocessing import Pool, cpu_count

# Cache database path - use non-hidden file
CACHE_DB = Path(__file__).parent / 'phash_cache.db'


def _compute_single_hash(file_path: str) -> Optional[Dict]:
    """
    Compute hash for a single file. This function is used by multiprocessing.
    Must be a top-level function (not a method) for pickling.
    """
    try:
        # Check file exists
        if not os.path.exists(file_path):
            return None

        # Open image and compute hash
        img = Image.open(file_path)
        phash = str(imagehash.phash(img, hash_size=16))
        resolution = f"{img.width}x{img.height}"
        filesize = os.path.getsize(file_path)

        return {
            'file_path': file_path,
            'phash': phash,
            'resolution': resolution,
            'filesize': filesize
        }
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return None


class BKTreeNode:
    """Node in BK-Tree for fast duplicate search based on hamming distance"""
    def __init__(self, data: Dict):
        self.data = data  # Store full image data
        self.children = {}  # {distance: BKTreeNode}


class BKTree:
    """
    BK-Tree for efficient similarity search based on hamming distance.

    Time complexity:
    - Build: O(n log n)
    - Query: O(log n)

    Space complexity: O(n * k) where k is average children per node (~20)
    """
    def __init__(self):
        self.root = None
        self.size = 0

    def add(self, data: Dict):
        """Add image data to the tree"""
        if self.root is None:
            self.root = BKTreeNode(data)
            self.size = 1
            return

        current = self.root
        phash = data['phash']

        while True:
            # Calculate hamming distance to current node
            distance = current.data['phash'] - phash

            if distance == 0:
                # Duplicate hash found, don't add
                return

            if distance in current.children:
                # Continue down the tree
                current = current.children[distance]
            else:
                # Add as new child at this distance
                current.children[distance] = BKTreeNode(data)
                self.size += 1
                return

    def search(self, phash, threshold: int) -> List[Dict]:
        """
        Find all images within threshold distance of the given hash.

        Args:
            phash: ImageHash object to search for
            threshold: Maximum hamming distance to consider a match

        Returns:
            List of image data dicts that match within threshold
        """
        if self.root is None:
            return []

        results = []
        candidates = [self.root]

        while candidates:
            node = candidates.pop()
            distance = node.data['phash'] - phash

            # If within threshold, add to results
            if distance <= threshold:
                results.append(node.data)

            # Prune search space: only explore children in range [d-t, d+t]
            # This is the key optimization of BK-Tree
            for child_distance in range(max(0, distance - threshold), distance + threshold + 1):
                if child_distance in node.children:
                    candidates.append(node.children[child_distance])

        return results


class PHashCache:
    def __init__(self, db_path: str = None):
        """
        Initialize PHash cache
        Args:
            db_path: Optional custom database path. If None, uses default location.
        """
        self.db_path = Path(db_path) if db_path else CACHE_DB
        self._conn = None  # Persistent connection for better performance
        self._init_db()

    def _get_connection(self):
        """Get or create a persistent database connection"""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        return self._conn

    def close(self):
        """Close the database connection"""
        if self._conn:
            self._conn.close()
            self._conn = None

    def _init_db(self):
        """Initialize database and create tables if needed"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS image_hashes (
                filename TEXT NOT NULL,
                filesize INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                phash TEXT NOT NULL,
                mtime REAL NOT NULL,
                resolution TEXT NOT NULL,
                PRIMARY KEY (filename, filesize, file_path)
            )
        ''')

        # Create whitelist table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS whitelist (
                filename TEXT NOT NULL,
                filesize INTEGER NOT NULL,
                added_time REAL NOT NULL,
                note TEXT,
                preview_path TEXT,
                PRIMARY KEY (filename, filesize)
            )
        ''')

        # Migration: Add preview_path column if it doesn't exist
        cursor.execute("PRAGMA table_info(whitelist)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'preview_path' not in columns:
            cursor.execute('ALTER TABLE whitelist ADD COLUMN preview_path TEXT')

        # Create index for faster lookups
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_phash ON image_hashes(phash)
        ''')

        # Create index for filename+filesize lookups
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_filename_filesize ON image_hashes(filename, filesize)
        ''')

        conn.commit()
        # Don't close, keep connection alive

    def get_hash(self, file_path: str) -> Optional[Dict]:
        """
        Get cached hash for a file.
        First looks up by filename+filesize, then validates mtime.
        Returns None if not cached or file was modified.
        """
        if not os.path.exists(file_path):
            return None

        stat = os.stat(file_path)
        current_mtime = stat.st_mtime
        filesize = stat.st_size
        filename = os.path.basename(file_path)

        conn = self._get_connection()
        cursor = conn.cursor()

        # First try exact match (filename + filesize + file_path)
        cursor.execute(
            'SELECT phash, mtime, resolution FROM image_hashes WHERE filename = ? AND filesize = ? AND file_path = ?',
            (filename, filesize, file_path)
        )
        row = cursor.fetchone()

        if row and abs(row[1] - current_mtime) < 0.001:  # mtime match
            return {
                'phash': row[0],
                'resolution': row[2],
                'filesize': filesize
            }

        # If no exact match, try filename+filesize only (file might have moved)
        cursor.execute(
            'SELECT phash, mtime, resolution, file_path FROM image_hashes WHERE filename = ? AND filesize = ? LIMIT 1',
            (filename, filesize)
        )
        row = cursor.fetchone()

        if row:
            # Found same filename+filesize, assume same file (moved location)
            # Update the database with new path
            self.update_file_path(filename, filesize, row[3], file_path, current_mtime)
            return {
                'phash': row[0],
                'resolution': row[2],
                'filesize': filesize
            }

        return None

    def set_hash(self, file_path: str, phash: str, resolution: str, filesize: int):
        """Cache hash for a file"""
        stat = os.stat(file_path)
        mtime = stat.st_mtime
        filename = os.path.basename(file_path)

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO image_hashes (filename, filesize, file_path, phash, mtime, resolution)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (filename, filesize, file_path, phash, mtime, resolution))

        conn.commit()

    def set_hash_batch(self, hash_data_list: List[Tuple[str, str, str, int]]):
        """
        Batch insert/update multiple hashes at once for better performance.
        Args:
            hash_data_list: List of tuples (file_path, phash, resolution, filesize)
        """
        if not hash_data_list:
            return

        conn = self._get_connection()
        cursor = conn.cursor()

        # Prepare batch data
        batch_data = []
        for file_path, phash, resolution, filesize in hash_data_list:
            stat = os.stat(file_path)
            mtime = stat.st_mtime
            filename = os.path.basename(file_path)
            batch_data.append((filename, filesize, file_path, phash, mtime, resolution))

        # Batch insert
        cursor.executemany('''
            INSERT OR REPLACE INTO image_hashes (filename, filesize, file_path, phash, mtime, resolution)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', batch_data)

        conn.commit()

    def update_file_path(self, filename: str, filesize: int, old_path: str, new_path: str, new_mtime: float):
        """Update file path when file is moved"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE image_hashes
            SET file_path = ?, mtime = ?
            WHERE filename = ? AND filesize = ? AND file_path = ?
        ''', (new_path, new_mtime, filename, filesize, old_path))

        conn.commit()

    def find_exact_duplicates(self, file_paths: List[str]) -> List[List[Dict]]:
        """
        Find exact duplicates based on filename + filesize.
        These are files with same name and size but different paths.
        Returns immediately without computing phash.
        Automatically filters out whitelisted groups.
        """
        # Group files by (filename, filesize)
        file_groups = {}
        for file_path in file_paths:
            if not os.path.exists(file_path):
                continue

            filename = os.path.basename(file_path)
            filesize = os.path.getsize(file_path)
            key = (filename, filesize)

            if key not in file_groups:
                file_groups[key] = []

            file_groups[key].append({
                'file_path': file_path,
                'filename': filename,
                'filesize': filesize
            })

        # Find groups with multiple files, exclude whitelisted
        duplicate_groups = []
        for (filename, filesize), files in file_groups.items():
            if len(files) >= 2:
                # Skip if this group is whitelisted
                if not self.is_whitelisted(filename, filesize):
                    duplicate_groups.append(files)

        return duplicate_groups

    def add_to_whitelist(self, filename: str, filesize: int, note: str = None, preview_path: str = None):
        """
        Add a file (by filename + filesize) to whitelist
        Args:
            filename: File name
            filesize: File size in bytes
            note: Optional note about why this is whitelisted
            preview_path: Optional path to a representative image for preview
        """
        import time
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO whitelist (filename, filesize, added_time, note, preview_path)
            VALUES (?, ?, ?, ?, ?)
        ''', (filename, filesize, time.time(), note, preview_path))

        conn.commit()

    def remove_from_whitelist(self, filename: str, filesize: int):
        """Remove a file from whitelist"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            DELETE FROM whitelist WHERE filename = ? AND filesize = ?
        ''', (filename, filesize))

        conn.commit()

    def is_whitelisted(self, filename: str, filesize: int) -> bool:
        """Check if a file is in whitelist"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            'SELECT 1 FROM whitelist WHERE filename = ? AND filesize = ?',
            (filename, filesize)
        )
        result = cursor.fetchone()

        return result is not None

    def get_whitelist(self) -> List[Dict]:
        """Get all whitelisted items"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT filename, filesize, added_time, note, preview_path FROM whitelist')
        rows = cursor.fetchall()

        return [
            {
                'filename': row[0],
                'filesize': row[1],
                'added_time': row[2],
                'note': row[3],
                'preview_path': row[4]
            }
            for row in rows
        ]

    def cleanup_missing_files(self, existing_files: set) -> Tuple[int, int]:
        """
        Remove database entries for files that no longer exist.

        Args:
            existing_files: Set of absolute file paths that currently exist

        Returns:
            Tuple of (removed_hashes_count, removed_whitelist_count)
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Get all file_paths from image_hashes table
        cursor.execute('SELECT file_path FROM image_hashes')
        db_files = [row[0] for row in cursor.fetchall()]

        # Find files in DB that don't exist anymore
        missing_files = [f for f in db_files if f not in existing_files]

        # Remove missing files from image_hashes
        removed_hashes = 0
        for file_path in missing_files:
            cursor.execute('DELETE FROM image_hashes WHERE file_path = ?', (file_path,))
            removed_hashes += cursor.rowcount

        # Get all filename+filesize combinations from whitelist
        cursor.execute('SELECT filename, filesize FROM whitelist')
        whitelist_items = cursor.fetchall()

        # Check if any files with these filename+filesize combinations still exist
        removed_whitelist = 0
        for filename, filesize in whitelist_items:
            # Check if any existing file matches this filename+filesize
            exists = any(
                os.path.basename(f) == filename and os.path.getsize(f) == filesize
                for f in existing_files
                if os.path.exists(f)
            )
            if not exists:
                cursor.execute(
                    'DELETE FROM whitelist WHERE filename = ? AND filesize = ?',
                    (filename, filesize)
                )
                removed_whitelist += cursor.rowcount

        conn.commit()

        return removed_hashes, removed_whitelist

    def verify_files_exist(self, file_paths: List[str]) -> Dict:
        """
        Verify which files in the list still exist on filesystem.

        Args:
            file_paths: List of file paths to check

        Returns:
            Dict with 'existing' and 'missing' lists
        """
        existing = []
        missing = []

        for path in file_paths:
            if os.path.exists(path):
                existing.append(path)
            else:
                missing.append(path)

        return {
            'existing': existing,
            'missing': missing
        }

    def compute_hash(self, file_path: str) -> Dict:
        """
        Compute perceptual hash and metadata for an image.
        Uses cache if available and file hasn't changed.
        """
        # Try cache first
        cached = self.get_hash(file_path)
        if cached:
            return cached

        # Compute new hash
        try:
            img = Image.open(file_path)

            # Compute perceptual hash (16x16 = 256 bits)
            phash = str(imagehash.phash(img, hash_size=16))

            # Get resolution
            resolution = f"{img.width}x{img.height}"

            # Get file size
            filesize = os.path.getsize(file_path)

            # Cache result
            self.set_hash(file_path, phash, resolution, filesize)

            return {
                'phash': phash,
                'resolution': resolution,
                'filesize': filesize
            }
        except Exception as e:
            print(f"Error processing {file_path}: {e}")
            return None

    def find_duplicates(self, file_paths: List[str], threshold: int = 5, progress_callback=None) -> List[List[Dict]]:
        """
        Find duplicate images based on perceptual hash similarity.
        Uses multiprocessing for parallel hash computation and batch database writes.

        Args:
            file_paths: List of image file paths to compare
            threshold: Maximum hamming distance to consider duplicates (0-64)
                      Lower = more strict. 5 is good for compressed duplicates.
            progress_callback: Optional callback(current, total, message) for progress updates

        Returns:
            List of duplicate groups, each group is a list of file info dicts
        """
        total_files = len(file_paths)
        print(f"[Duplicate Finder] Starting hash computation for {total_files} files")
        print(f"[Duplicate Finder] Using {cpu_count()} CPU cores for parallel processing")

        # Step 1: Check cache for existing hashes
        cached_data = []
        files_to_compute = []

        for i, file_path in enumerate(file_paths):
            # Update progress less frequently (every 100 files)
            if progress_callback and i % 100 == 0:
                progress_callback(i, total_files, f'Checking cache... ({i}/{total_files})')

            cached = self.get_hash(file_path)
            if cached:
                cached_data.append({
                    'file_path': file_path,
                    'phash': cached['phash'],
                    'resolution': cached['resolution'],
                    'filesize': cached['filesize']
                })
            else:
                files_to_compute.append(file_path)

        print(f"[Duplicate Finder] Cache hits: {len(cached_data)}, Need to compute: {len(files_to_compute)}")

        # Step 2: Compute hashes for uncached files using multiprocessing
        computed_data = []
        # Write to database every 100 images to keep in sync with frontend progress updates
        BATCH_WRITE_SIZE = 100
        PROGRESS_UPDATE_INTERVAL = 100  # Must match BATCH_WRITE_SIZE for consistency

        if files_to_compute:
            # Use multiprocessing pool
            num_workers = max(1, cpu_count() - 1)  # Leave one core free
            chunk_size = max(1, len(files_to_compute) // (num_workers * 4))

            print(f"[Duplicate Finder] Computing hashes with {num_workers} workers, chunk size: {chunk_size}")

            with Pool(processes=num_workers) as pool:
                # Process files in parallel
                completed = 0
                batch_buffer = []  # Buffer for batch writing

                for result in pool.imap_unordered(_compute_single_hash, files_to_compute, chunksize=chunk_size):
                    if result:
                        computed_data.append(result)
                        batch_buffer.append(result)

                        # Batch write every BATCH_WRITE_SIZE images
                        if len(batch_buffer) >= BATCH_WRITE_SIZE:
                            batch_data = [
                                (item['file_path'], item['phash'], item['resolution'], item['filesize'])
                                for item in batch_buffer
                            ]
                            self.set_hash_batch(batch_data)
                            print(f"[Duplicate Finder] Batch wrote {len(batch_buffer)} hashes to database")
                            batch_buffer = []  # Clear buffer

                    completed += 1
                    # Update progress every PROGRESS_UPDATE_INTERVAL files
                    if progress_callback and completed % PROGRESS_UPDATE_INTERVAL == 0:
                        progress_callback(
                            len(cached_data) + completed,
                            total_files,
                            f'Computing hashes... ({len(cached_data) + completed}/{total_files})'
                        )

                # Write remaining items in buffer
                if batch_buffer:
                    batch_data = [
                        (item['file_path'], item['phash'], item['resolution'], item['filesize'])
                        for item in batch_buffer
                    ]
                    self.set_hash_batch(batch_data)
                    print(f"[Duplicate Finder] Final batch wrote {len(batch_buffer)} hashes to database")

            print(f"[Duplicate Finder] Computed {len(computed_data)} hashes")

        # Combine cached and computed data
        image_data = cached_data + computed_data

        # Convert phash strings to hash objects for comparison
        for img in image_data:
            img['phash'] = imagehash.hex_to_hash(img['phash'])

        # Notify hash computation complete
        if progress_callback:
            progress_callback(total_files, total_files, 'Hash computation complete. Finding duplicates...')

        print(f"[Duplicate Finder] Starting duplicate detection for {len(image_data)} images")

        # Step 4: Build BK-Tree for efficient similarity search
        print(f"[Duplicate Finder] Building BK-Tree for fast duplicate search...")
        bktree = BKTree()
        for img in image_data:
            bktree.add(img)
        print(f"[Duplicate Finder] BK-Tree built with {bktree.size} nodes")

        # Step 5: Find duplicates using BK-Tree (much faster than O(n²))
        duplicate_groups = []
        processed = set()

        for i, img1 in enumerate(image_data):
            # Report progress every 100 images
            if progress_callback and i % 100 == 0:
                progress_callback(
                    i,
                    len(image_data),
                    f'Finding duplicates... ({i}/{len(image_data)})'
                )

            if img1['file_path'] in processed:
                continue

            # Use BK-Tree to find similar images (O(log n) instead of O(n))
            similar = bktree.search(img1['phash'], threshold)

            # Filter out already processed and self
            group = []
            for img2 in similar:
                if img2['file_path'] not in processed:
                    group.append(img2)
                    processed.add(img2['file_path'])

            # Only add groups with 2+ images
            if len(group) >= 2:
                # Check if this group should be filtered by whitelist
                first_file = group[0]['file_path']
                filename = os.path.basename(first_file)
                filesize = group[0]['filesize']

                # Skip if whitelisted
                if self.is_whitelisted(filename, filesize):
                    continue

                # Sort group by resolution (descending - highest first)
                def get_resolution_pixels(img):
                    try:
                        w, h = img['resolution'].split('x')
                        return int(w) * int(h)
                    except:
                        return 0

                group.sort(key=get_resolution_pixels, reverse=True)

                # Convert phash back to string for JSON serialization
                for img in group:
                    img['phash'] = str(img['phash'])
                duplicate_groups.append(group)

        print(f"[Duplicate Finder] Found {len(duplicate_groups)} duplicate groups")
        return duplicate_groups
