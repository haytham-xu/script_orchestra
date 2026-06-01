"""
Perceptual Hash Cache Manager

Uses SQLite to cache image hashes for fast duplicate detection.
"""
import sqlite3
import os
import time
from pathlib import Path
from PIL import Image
import imagehash
from typing import Optional, Dict, List, Tuple
from multiprocessing import Pool, cpu_count
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    print("[Warning] psutil not available, memory optimization disabled")

# Cache database path - use non-hidden file
# Default path if not configured in settings
DEFAULT_CACHE_DB = Path(__file__).parent / 'phash_cache.db'


def get_default_cache_path():
    """
    Get the cache database path from settings, or use default if not configured.
    This ensures all code uses the same database path.
    """
    try:
        from .settings_manager import settings_manager
        configured_path = settings_manager.get_phash_db_path()
        if configured_path:
            return Path(configured_path)
    except Exception as e:
        print(f"[PHashCache] Could not load configured DB path: {e}")
    return DEFAULT_CACHE_DB

# Global variable for compute delay (accessible by multiprocessing workers)
_COMPUTE_DELAY = 0.0


def set_compute_delay(delay: float):
    """Set global compute delay for multiprocessing workers"""
    global _COMPUTE_DELAY
    _COMPUTE_DELAY = delay


def _compute_single_hash_with_delay(args):
    """Wrapper that accepts (file_path, delay) tuple for multiprocessing"""
    file_path, compute_delay = args
    # Apply compute delay
    if compute_delay > 0:
        time.sleep(compute_delay)
    return _compute_single_hash(file_path)


def _compute_single_hash(file_path: str) -> Optional[Dict]:
    """
    Compute hash for a single file. This function is used by multiprocessing.
    Must be a top-level function (not a method) for pickling.

    Returns:
        Dict with image data or error info. Always returns a dict (never None).
        Success: {'file_path': ..., 'phash': ..., 'resolution': ..., 'filesize': ..., 'error': False}
        Error: {'error': True, 'file_path': ..., 'error_type': ..., 'error_msg': ...}
    """
    import os
    import multiprocessing

    pid = os.getpid()
    worker_name = multiprocessing.current_process().name
    filename = os.path.basename(file_path)

    print(f"[Worker {worker_name} PID={pid}] START processing: {filename}")

    try:
        # Check file exists
        if not os.path.exists(file_path):
            print(f"[Worker {worker_name} PID={pid}] ERROR: File not found - {filename}")
            return {
                'error': True,
                'file_path': file_path,
                'error_type': 'file_not_found',
                'error_msg': 'File not found'
            }

        # Open image and compute hash
        img = Image.open(file_path)
        phash = str(imagehash.phash(img, hash_size=16))
        resolution = f"{img.width}x{img.height}"
        filesize = os.path.getsize(file_path)

        print(f"[Worker {worker_name} PID={pid}] SUCCESS: {filename} - phash={phash[:8]}..., res={resolution}, size={filesize}")

        return {
            'file_path': file_path,
            'phash': phash,
            'resolution': resolution,
            'filesize': filesize,
            'error': False
        }
    except OSError as e:
        # Handle truncated/corrupted files
        error_msg = str(e)
        if 'truncated' in error_msg.lower():
            error_type = 'truncated'
        elif 'cannot identify' in error_msg.lower():
            error_type = 'unrecognized_format'
        else:
            error_type = 'io_error'

        print(f"[Worker {worker_name} PID={pid}] ERROR: {error_type} - {filename}: {error_msg}")

        return {
            'error': True,
            'file_path': file_path,
            'error_type': error_type,
            'error_msg': error_msg
        }
    except Exception as e:
        # Catch all other errors
        print(f"[Worker {worker_name} PID={pid}] ERROR: unknown_error - {filename}: {str(e)}")
        return {
            'error': True,
            'file_path': file_path,
            'error_type': 'unknown_error',
            'error_msg': str(e)
        }


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
            db_path: Optional custom database path. If None, uses configured path from settings or default.
        """
        if db_path:
            self.db_path = Path(db_path)
        else:
            self.db_path = get_default_cache_path()

        print(f"[PHashCache] Using database: {self.db_path}")
        self._conn = None  # Persistent connection for better performance
        self._stop_event = None  # For stop control
        self._init_db()

    def _get_connection(self):
        """Get or create a persistent database connection"""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            # Enable foreign key constraints (required for CASCADE DELETE)
            self._conn.execute('PRAGMA foreign_keys = ON')
        return self._conn

    def close(self):
        """Close the database connection"""
        if self._conn:
            self._conn.close()
            self._conn = None

    def _init_db(self):
        """Initialize database and create tables if needed (NEW SCHEMA)"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Migration check: if old schema exists, user should run migrate_to_new_schema.py first
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='image_hashes'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(image_hashes)")
            columns = {col[1] for col in cursor.fetchall()}
            if 'id' not in columns:
                print("[ERROR] Old database schema detected!")
                print("[ERROR] Please run: python migrate_to_new_schema.py")
                raise RuntimeError("Database migration required. Run migrate_to_new_schema.py first.")

        # Create new schema tables
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

        # Create whitelist table - stores image IDs to exclude from duplicate detection
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS whitelist (
                image_id INTEGER PRIMARY KEY,
                added_time REAL NOT NULL,
                FOREIGN KEY (image_id) REFERENCES image_hashes(id) ON DELETE CASCADE
            )
        ''')

        # Create whitelist_groups table - stores duplicate groups to exclude from detection
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS whitelist_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                added_time REAL NOT NULL
            )
        ''')

        # Create whitelist_group_members table - stores members of each whitelist group
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS whitelist_group_members (
                group_id INTEGER NOT NULL,
                image_id INTEGER NOT NULL,
                FOREIGN KEY (group_id) REFERENCES whitelist_groups(id) ON DELETE CASCADE,
                FOREIGN KEY (image_id) REFERENCES image_hashes(id) ON DELETE CASCADE,
                PRIMARY KEY (group_id, image_id)
            )
        ''')

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_whitelist_group_members_group ON whitelist_group_members(group_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_whitelist_group_members_image ON whitelist_group_members(image_id)')

        # Create phash_similarities table
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

        # Create view
        cursor.execute('''
            CREATE VIEW IF NOT EXISTS phash_similarities_view AS
            SELECT image_id_a as image_id, image_id_b as neighbor_id, threshold, distance
            FROM phash_similarities
            UNION ALL
            SELECT image_id_b as image_id, image_id_a as neighbor_id, threshold, distance
            FROM phash_similarities
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

    def get_all_cached_images(self, file_exists_check: bool = True) -> List[Dict]:
        """
        Load all cached image hashes from database.

        Args:
            file_exists_check: Whether to verify files still exist (default: True)

        Returns:
            List of image data dicts with phash, file_path, resolution, filesize
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT file_path, phash, resolution, filesize, mtime
            FROM image_hashes
            ORDER BY file_path
        ''')

        results = []
        missing_count = 0

        for row in cursor.fetchall():
            file_path, phash, resolution, filesize, cached_mtime = row

            # Optionally check if file still exists
            if file_exists_check:
                if not os.path.exists(file_path):
                    missing_count += 1
                    continue

                # Check if file was modified
                try:
                    stat = os.stat(file_path)
                    if stat.st_mtime != cached_mtime or stat.st_size != filesize:
                        # File was modified, skip it
                        missing_count += 1
                        continue
                except OSError:
                    missing_count += 1
                    continue

            results.append({
                'file_path': file_path,
                'phash': phash,
                'resolution': resolution,
                'filesize': filesize
            })

        if missing_count > 0:
            print(f"[Duplicate Finder] Skipped {missing_count} files (missing or modified)")

        return results

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

    def add_to_whitelist(self, image_id: int):
        """
        Add an image to whitelist by its image_id
        Args:
            image_id: The ID of the image in image_hashes table
        """
        import time
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO whitelist (image_id, added_time)
            VALUES (?, ?)
        ''', (image_id, time.time()))

        conn.commit()

    def remove_from_whitelist(self, image_id: int):
        """Remove an image from whitelist by its image_id"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            DELETE FROM whitelist WHERE image_id = ?
        ''', (image_id,))

        conn.commit()

    def is_whitelisted(self, image_id: int) -> bool:
        """Check if an image is in whitelist"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            'SELECT 1 FROM whitelist WHERE image_id = ?',
            (image_id,)
        )
        result = cursor.fetchone()

        return result is not None

    def get_whitelist(self) -> List[Dict]:
        """
        Get all whitelisted items with full image information
        Returns list of dicts with image details joined from image_hashes table
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT w.image_id, w.added_time, i.filename, i.filesize, i.file_path, i.phash, i.resolution
            FROM whitelist w
            JOIN image_hashes i ON w.image_id = i.id
        ''')
        rows = cursor.fetchall()

        return [
            {
                'image_id': row[0],
                'added_time': row[1],
                'filename': row[2],
                'filesize': row[3],
                'file_path': row[4],
                'phash': row[5],
                'resolution': row[6]
            }
            for row in rows
        ]

    def add_group_to_whitelist(self, image_ids: List[int]):
        """
        Add a duplicate group to whitelist
        Args:
            image_ids: List of image IDs that form a duplicate group
        """
        if not image_ids or len(image_ids) < 2:
            raise ValueError("Group must have at least 2 images")

        import time
        conn = self._get_connection()
        cursor = conn.cursor()

        # Create new group
        cursor.execute('INSERT INTO whitelist_groups (added_time) VALUES (?)', (time.time(),))
        group_id = cursor.lastrowid

        # Add members
        for image_id in image_ids:
            cursor.execute('''
                INSERT INTO whitelist_group_members (group_id, image_id)
                VALUES (?, ?)
            ''', (group_id, image_id))

        conn.commit()
        print(f"[Whitelist] Added group {group_id} with {len(image_ids)} members")

    def remove_whitelist_group(self, group_id: int):
        """Delete a whitelist group (members will be CASCADE deleted)"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM whitelist_groups WHERE id = ?', (group_id,))
        conn.commit()
        print(f"[Whitelist] Removed group {group_id}")

    def is_group_whitelisted(self, image_ids: List[int]) -> bool:
        """
        Check if a specific combination of image_ids is whitelisted
        Returns True only if there's an exact match with a whitelist group
        """
        if not image_ids or len(image_ids) < 2:
            return False

        conn = self._get_connection()
        cursor = conn.cursor()
        image_ids_set = set(image_ids)

        # Get all whitelist groups with their members
        cursor.execute('''
            SELECT group_id, GROUP_CONCAT(image_id) as members
            FROM whitelist_group_members
            GROUP BY group_id
        ''')

        for row in cursor.fetchall():
            whitelist_ids = set(map(int, row[1].split(',')))
            if image_ids_set == whitelist_ids:
                return True
        return False

    def get_whitelist_groups(self) -> List[Dict]:
        """
        Get all whitelist groups with their members' full information
        Returns list of groups with member details
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Get all groups
        cursor.execute('SELECT id, added_time FROM whitelist_groups ORDER BY added_time DESC')
        groups = cursor.fetchall()

        result = []
        for group_id, added_time in groups:
            # Get members for this group
            cursor.execute('''
                SELECT m.image_id, i.filename, i.filesize, i.file_path, i.phash, i.resolution
                FROM whitelist_group_members m
                JOIN image_hashes i ON m.image_id = i.id
                WHERE m.group_id = ?
            ''', (group_id,))

            members = [
                {
                    'image_id': row[0],
                    'filename': row[1],
                    'filesize': row[2],
                    'file_path': row[3],
                    'phash': row[4],
                    'resolution': row[5]
                }
                for row in cursor.fetchall()
            ]

            # Boundary handling: if group has < 2 members, delete it
            if len(members) < 2:
                cursor.execute('DELETE FROM whitelist_groups WHERE id = ?', (group_id,))
                conn.commit()
                print(f"[Whitelist] Auto-removed invalid group {group_id} (< 2 members)")
                continue

            result.append({
                'group_id': group_id,
                'added_time': added_time,
                'members': members
            })

        return result

    def cleanup_whitelist_groups(self) -> int:
        """
        Clean up invalid whitelist groups (with < 2 members)
        Returns number of groups removed
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Find groups with < 2 members
        cursor.execute('''
            SELECT group_id, COUNT(*) as member_count
            FROM whitelist_group_members
            GROUP BY group_id
            HAVING member_count < 2
        ''')

        invalid_groups = [row[0] for row in cursor.fetchall()]

        if invalid_groups:
            placeholders = ','.join('?' * len(invalid_groups))
            cursor.execute(f'DELETE FROM whitelist_groups WHERE id IN ({placeholders})', invalid_groups)
            conn.commit()
            print(f"[Whitelist] Cleaned up {len(invalid_groups)} invalid groups")

        return len(invalid_groups)

    def cleanup_missing_files(self, existing_files: set) -> Tuple[int, int]:
        """
        Remove database entries for files that no longer exist.

        Args:
            existing_files: Set of absolute file paths that currently exist

        Returns:
            Tuple of (removed_hashes_count, removed_whitelist_count)
            Note: whitelist_count will always be 0 since ON DELETE CASCADE handles it automatically
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Get all file_paths from image_hashes table
        cursor.execute('SELECT file_path FROM image_hashes')
        db_files = [row[0] for row in cursor.fetchall()]

        # Find files in DB that don't exist anymore
        missing_files = [f for f in db_files if f not in existing_files]

        # Remove missing files from image_hashes
        # Whitelist records will be automatically removed by ON DELETE CASCADE
        removed_hashes = 0
        for file_path in missing_files:
            cursor.execute('DELETE FROM image_hashes WHERE file_path = ?', (file_path,))
            removed_hashes += cursor.rowcount

        conn.commit()

        # Return 0 for whitelist since CASCADE handles it automatically
        return (removed_hashes, 0)

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

    def _compute_file_list_hash(self, file_paths: List[str]) -> str:
        """
        Compute a hash representing the file list to use as cache key.
        Uses sorted file paths and their mtimes.
        """
        import hashlib
        import json

        # Sort file paths for consistent hashing
        sorted_paths = sorted(file_paths)

        # Create a signature from file paths and their mtimes
        signature_data = []
        for path in sorted_paths:
            if os.path.exists(path):
                mtime = os.path.getmtime(path)
                signature_data.append({'path': path, 'mtime': mtime})

        # Compute hash of the signature
        signature_json = json.dumps(signature_data, sort_keys=True)
        return hashlib.sha256(signature_json.encode()).hexdigest()

    def get_cached_scan(self, file_paths: List[str], threshold: int) -> Optional[List[List[Dict]]]:
        """
        Get cached scan results if available and valid.

        Args:
            file_paths: List of file paths being scanned
            threshold: Hamming distance threshold

        Returns:
            Cached duplicate groups or None if not cached or invalid
        """
        import json

        file_list_hash = self._compute_file_list_hash(file_paths)

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            'SELECT scan_result, file_count FROM scan_cache WHERE file_list_hash = ? AND threshold = ?',
            (file_list_hash, threshold)
        )
        row = cursor.fetchone()

        if row:
            # Verify file count matches
            if row[1] == len(file_paths):
                try:
                    scan_result = json.loads(row[0])
                    return scan_result
                except json.JSONDecodeError:
                    # Invalid cached data, delete it
                    cursor.execute(
                        'DELETE FROM scan_cache WHERE file_list_hash = ? AND threshold = ?',
                        (file_list_hash, threshold)
                    )
                    conn.commit()

        return None

    def save_neighbors(self, neighbors_list: List[tuple]):
        """
        Save phash neighbor relationships to cache.

        Args:
            neighbors_list: List of (phash1, phash2, distance) tuples
        """
        if not neighbors_list:
            return

        conn = self._get_connection()
        cursor = conn.cursor()
        current_time = time.time()

        # Prepare data with last_checked timestamp
        data = [(p1, p2, dist, current_time) for p1, p2, dist in neighbors_list]

        cursor.executemany('''
            INSERT OR REPLACE INTO phash_neighbors (phash, neighbor_phash, distance, last_checked)
            VALUES (?, ?, ?, ?)
        ''', data)

        conn.commit()

    def get_neighbors_from_cache(self, phashes: List[str], threshold: int) -> Dict[str, List[tuple]]:
        """
        Get cached neighbor relationships for given phashes.

        Args:
            phashes: List of phash values to query
            threshold: Maximum distance to consider

        Returns:
            Dict mapping phash -> list of (neighbor_phash, distance) tuples
        """
        if not phashes:
            return {}

        conn = self._get_connection()
        cursor = conn.cursor()

        # Query neighbors for all phashes at once
        placeholders = ','.join('?' * len(phashes))
        query = f'''
            SELECT phash, neighbor_phash, distance
            FROM phash_neighbors
            WHERE phash IN ({placeholders})
            AND distance <= ?
        '''

        cursor.execute(query, phashes + [threshold])

        # Build result dict
        result = {}
        for row in cursor.fetchall():
            phash, neighbor_phash, distance = row
            if phash not in result:
                result[phash] = []
            result[phash].append((neighbor_phash, distance))

        return result

    def get_cached_phashes(self) -> set:
        """
        Get set of all phashes that have cached neighbors.

        Returns:
            Set of phash values that have neighbor records
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT DISTINCT phash FROM phash_neighbors')
        return {row[0] for row in cursor.fetchall()}

    def cleanup_orphaned_neighbors(self):
        """
        Remove neighbor records for phashes no longer in image_hashes table.
        This is a maintenance operation to keep database clean.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Delete neighbors where phash not in image_hashes
        cursor.execute('''
            DELETE FROM phash_neighbors
            WHERE phash NOT IN (SELECT phash FROM image_hashes)
            OR neighbor_phash NOT IN (SELECT phash FROM image_hashes)
        ''')

        removed = cursor.rowcount
        conn.commit()

        return removed

    def save_scan_cache(self, file_paths: List[str], threshold: int, duplicate_groups: List[List[Dict]]):
        """
        Save scan results to cache for faster future scans.

        Args:
            file_paths: List of file paths scanned
            threshold: Hamming distance threshold used
            duplicate_groups: Duplicate groups found
        """
        import json

        file_list_hash = self._compute_file_list_hash(file_paths)
        scan_time = time.time()
        file_count = len(file_paths)
        scan_result = json.dumps(duplicate_groups)

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO scan_cache (file_list_hash, threshold, scan_result, scan_time, file_count)
            VALUES (?, ?, ?, ?, ?)
        ''', (file_list_hash, threshold, scan_result, scan_time, file_count))

        conn.commit()

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

    def _should_skip_file(self, file_path: str) -> tuple[bool, str]:
        """
        Check if a file should be skipped (Windows hidden files, system files, etc.)

        Args:
            file_path: Path to check

        Returns:
            (should_skip: bool, reason: str)
        """
        filename = os.path.basename(file_path)
        filename_lower = filename.lower()

        # Skip common system/temporary files (check first before hidden file check)
        skip_patterns = [
            'thumbs.db',
            '.ds_store',
            'desktop.ini',
            '.picasa.ini',
            '.localized',
            '@eadir',  # Synology NAS
        ]

        for pattern in skip_patterns:
            if filename_lower == pattern or filename_lower.startswith(pattern):
                return (True, 'system_file')

        # Skip temp files starting with ~$
        if filename.startswith('~$'):
            return (True, 'system_file')

        # Skip Windows hidden files starting with dot (e.g., .0279.jpg)
        # But exclude common extensions that might be legitimate
        if filename.startswith('.') and len(filename) > 1:
            # Allow .jpg, .png, etc. if they're actual image files (macOS sometimes creates these)
            # But skip things like .0279.jpg which are Windows artifacts
            if filename.count('.') >= 2:  # e.g., .0279.jpg has 2 dots
                return (True, 'windows_hidden_file')

        return (False, '')

    def find_duplicates(self, file_paths: List[str], threshold: int = 5, progress_callback=None, stop_event=None) -> List[List[Dict]]:
        """
        Find duplicate images based on perceptual hash similarity.
        Uses multiprocessing for parallel hash computation and batch database writes.

        Args:
            file_paths: List of image file paths to compare
            threshold: Maximum hamming distance to consider duplicates (0-64)
                      Lower = more strict. 5 is good for compressed duplicates.
            progress_callback: Optional callback(current, total, message, extra_data) for progress updates
            stop_event: Optional threading.Event to signal stop

        Returns:
            List of duplicate groups, each group is a list of file info dicts
        """
        total_files = len(file_paths)
        start_time = time.time()

        print(f"[Duplicate Finder] Starting duplicate detection for {total_files} files")

        # Filter out files that should be skipped
        skipped_files = []
        filtered_paths = []
        for file_path in file_paths:
            should_skip, skip_reason = self._should_skip_file(file_path)
            if should_skip:
                skipped_files.append({
                    'file_path': file_path,
                    'skip_reason': skip_reason
                })
            else:
                filtered_paths.append(file_path)

        if skipped_files:
            print(f"[Duplicate Finder] 🚫 Skipped {len(skipped_files)} system/hidden files")
            # Count by reason
            skip_reasons = {}
            for item in skipped_files:
                reason = item['skip_reason']
                skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
            for reason, count in skip_reasons.items():
                reason_name = {
                    'windows_hidden_file': 'Windows hidden files (starting with .)',
                    'system_file': 'System/temporary files'
                }.get(reason, reason)
                print(f"   - {reason_name}: {count}")

        # Use filtered list for scanning
        file_paths = filtered_paths
        total_files = len(file_paths)
        print(f"[Duplicate Finder] 📊 {total_files} files to scan")

        # Check scan cache first
        if progress_callback:
            progress_callback(0, total_files, '📦 Checking scan cache...')

        cached_scan = self.get_cached_scan(file_paths, threshold)
        if cached_scan is not None:
            cache_time = time.time() - start_time
            print(f"[Duplicate Finder] ✅ Using cached scan results ({len(cached_scan)} groups, {cache_time:.1f}s)")
            if progress_callback:
                progress_callback(total_files, total_files, f'✅ Used cached scan ({len(cached_scan)} groups)')

            # Return cached result with metadata
            result = {
                'duplicate_groups': cached_scan,
                'total_files': len(file_paths) + len(skipped_files),
                'scanned_files': len(file_paths),
                'skipped_files': skipped_files,
                'error_files': [],  # No errors when using cache
                'stats': {
                    'total_time': cache_time,
                    'groups_found': len(cached_scan),
                    'files_skipped': len(skipped_files),
                    'files_errored': 0,
                    'from_cache': True
                }
            }
            return result

        print(f"[Duplicate Finder] 🔄 No cached scan found, computing...")
        print(f"[Duplicate Finder] Starting hash computation for {total_files} files")

        # Get CPU usage configuration from settings
        try:
            from .settings_manager import settings_manager
            max_cpu_percent = settings_manager.get_max_cpu_usage_percent()
        except:
            max_cpu_percent = 50  # Fallback default

        # Monitor memory and optimize worker count
        if HAS_PSUTIL:
            process = psutil.Process()
            initial_memory_mb = process.memory_info().rss / 1024 / 1024
            available_memory_gb = psutil.virtual_memory().available / 1024 / 1024 / 1024
            print(f"[Duplicate Finder] Initial memory: {initial_memory_mb:.1f} MB, Available: {available_memory_gb:.1f} GB")

            # Calculate max workers from CPU percentage setting
            max_workers_from_cpu = max(1, int(cpu_count() * max_cpu_percent / 100))

            # Further limit based on available memory for safety
            if available_memory_gb < 2:
                num_workers = max(1, min(max_workers_from_cpu, cpu_count() // 4))
                print(f"[Duplicate Finder] ⚠️  Low memory ({available_memory_gb:.1f} GB), using {num_workers}/{cpu_count()} workers (limited from {max_workers_from_cpu})")
            elif available_memory_gb < 4:
                num_workers = max(1, min(max_workers_from_cpu, cpu_count() // 2))
                print(f"[Duplicate Finder] ⚠️  Limited memory ({available_memory_gb:.1f} GB), using {num_workers}/{cpu_count()} workers (limited from {max_workers_from_cpu})")
            else:
                num_workers = max_workers_from_cpu
                print(f"[Duplicate Finder] ✅ Using {num_workers}/{cpu_count()} workers ({max_cpu_percent}% CPU configured, {available_memory_gb:.1f} GB available)")
        else:
            # No psutil, just use CPU percentage setting
            num_workers = max(1, int(cpu_count() * max_cpu_percent / 100))
            print(f"[Duplicate Finder] Using {num_workers}/{cpu_count()} CPU cores ({max_cpu_percent}% configured)")

        # Step 1: Check cache for existing hashes
        if progress_callback:
            progress_callback(0, total_files, '📝 Checking hash cache...')

        cached_data = []
        files_to_compute = []
        cache_check_start = time.time()

        for i, file_path in enumerate(file_paths):
            # Check for stop signal during cache check
            if stop_event and i % 1000 == 0 and stop_event.is_set():
                print(f"[Duplicate Finder] Stop signal received during cache check")
                raise InterruptedError(f"Scan stopped by user during cache check")

            # Update progress less frequently for cache check (every 1000 files)
            if progress_callback and i > 0 and i % 1000 == 0:
                progress_callback(i, total_files, f'📝 Checking cache... ({i}/{total_files})')

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

        cache_check_time = time.time() - cache_check_start
        print(f"[Duplicate Finder] ✅ Cache: {len(cached_data)} hits, ❌ New: {len(files_to_compute)} ({cache_check_time:.1f}s)")

        # Step 2: Compute hashes for uncached files using multiprocessing
        computed_data = []
        error_files = []  # Track files with errors
        BATCH_WRITE_SIZE = 100
        PROGRESS_UPDATE_INTERVAL = 100

        if files_to_compute:
            hash_compute_start = time.time()

            # Smaller chunk size for better memory management
            chunk_size = max(1, min(10, len(files_to_compute) // (num_workers * 4)))
            print(f"[Duplicate Finder] Computing {len(files_to_compute)} hashes (chunk_size: {chunk_size})")

            with Pool(processes=num_workers) as pool:
                completed = 0
                batch_buffer = []
                computed_count = 0
                error_count = 0

                for result in pool.imap_unordered(_compute_single_hash, files_to_compute, chunksize=chunk_size):
                    if result:
                        if result.get('error'):
                            # Handle error result
                            error_files.append(result)
                            error_count += 1
                        else:
                            # Handle success result
                            computed_data.append(result)
                            batch_buffer.append(result)
                            computed_count += 1

                            # Batch write every BATCH_WRITE_SIZE images
                            if len(batch_buffer) >= BATCH_WRITE_SIZE:
                                batch_data = [
                                    (item['file_path'], item['phash'], item['resolution'], item['filesize'])
                                    for item in batch_buffer
                                ]
                                self.set_hash_batch(batch_data)
                                batch_buffer = []

                    completed += 1

                    # Check for stop signal during hash computation
                    if stop_event and completed % 100 == 0 and stop_event.is_set():
                        print(f"[Duplicate Finder] Stop signal received during hash computation")
                        pool.terminate()  # Immediately terminate worker processes
                        pool.join()
                        raise InterruptedError(f"Scan stopped by user during hash computation")

                    # Update progress with ETA
                    if progress_callback and completed % PROGRESS_UPDATE_INTERVAL == 0:
                        elapsed = time.time() - hash_compute_start
                        speed = completed / elapsed if elapsed > 0 else 0
                        remaining = len(files_to_compute) - completed
                        eta_seconds = remaining / speed if speed > 0 else 0

                        if eta_seconds > 60:
                            eta_str = f"{int(eta_seconds // 60)}m{int(eta_seconds % 60)}s"
                        else:
                            eta_str = f"{int(eta_seconds)}s"

                        total_progress = len(cached_data) + completed
                        error_suffix = f" | ⚠️  {error_count} errors" if error_count > 0 else ""
                        progress_callback(
                            total_progress,
                            total_files,
                            f'🔄 Computing... {computed_count} new | {len(cached_data)} cached | ETA: {eta_str}{error_suffix}'
                        )

                # Write remaining items
                if batch_buffer:
                    batch_data = [
                        (item['file_path'], item['phash'], item['resolution'], item['filesize'])
                        for item in batch_buffer
                    ]
                    self.set_hash_batch(batch_data)

            hash_compute_time = time.time() - hash_compute_start
            print(f"[Duplicate Finder] ✅ Computed {len(computed_data)} hashes in {hash_compute_time:.1f}s")

            # Report errors if any
            if error_files:
                print(f"[Duplicate Finder] ⚠️  {len(error_files)} files failed to process")

                # Count errors by type
                error_types = {}
                for error in error_files:
                    error_type = error.get('error_type', 'unknown')
                    error_types[error_type] = error_types.get(error_type, 0) + 1

                # Print error summary
                for error_type, count in error_types.items():
                    type_name = {
                        'truncated': 'Truncated/corrupted',
                        'unrecognized_format': 'Unrecognized format',
                        'file_not_found': 'File not found',
                        'io_error': 'I/O error',
                        'unknown_error': 'Unknown error'
                    }.get(error_type, error_type)
                    print(f"   - {type_name}: {count}")

                # Save error report to file
                error_report_path = Path(__file__).parent / 'error_files.txt'
                try:
                    with open(error_report_path, 'w', encoding='utf-8') as f:
                        f.write(f"Duplicate Finder - Error Report\n")
                        f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                        f.write(f"Total errors: {len(error_files)}\n")
                        f.write(f"\n{'='*80}\n\n")

                        # Group by error type
                        for error_type in sorted(error_types.keys()):
                            type_name = {
                                'truncated': 'Truncated/Corrupted Files',
                                'unrecognized_format': 'Unrecognized Format',
                                'file_not_found': 'File Not Found',
                                'io_error': 'I/O Error',
                                'unknown_error': 'Unknown Error'
                            }.get(error_type, error_type.upper())

                            f.write(f"{type_name} ({error_types[error_type]} files):\n")
                            f.write(f"{'-'*80}\n")

                            for error in error_files:
                                if error.get('error_type') == error_type:
                                    f.write(f"{error['file_path']}\n")
                                    f.write(f"  Error: {error['error_msg']}\n")
                                    f.write(f"\n")

                            f.write(f"\n")

                    print(f"[Duplicate Finder] 📄 Error report saved to: {error_report_path}")
                except Exception as e:
                    print(f"[Duplicate Finder] ⚠️  Failed to save error report: {e}")

            if HAS_PSUTIL:
                current_memory_mb = process.memory_info().rss / 1024 / 1024
                memory_increase = current_memory_mb - initial_memory_mb
                print(f"[Duplicate Finder] Memory: {current_memory_mb:.1f} MB (+{memory_increase:.1f} MB)")

        # Combine and free memory
        image_data = cached_data + computed_data
        del cached_data
        del computed_data
        del files_to_compute

        # Convert phash strings to hash objects
        for img in image_data:
            img['phash'] = imagehash.hex_to_hash(img['phash'])

        if progress_callback:
            progress_callback(total_files, total_files, '✅ Hash complete. Building search tree...')

        print(f"[Duplicate Finder] Starting duplicate detection for {len(image_data)} images")

        # Check neighbor cache coverage
        current_phashes = [img['phash'] for img in image_data]
        cached_phashes = self.get_cached_phashes()

        # Separate cached and uncached files
        cached_images = []
        uncached_images = []
        for img in image_data:
            if img['phash'] in cached_phashes:
                cached_images.append(img)
            else:
                uncached_images.append(img)

        cache_coverage = len(cached_images) / len(image_data) * 100 if image_data else 0
        print(f"[Duplicate Finder] Neighbor cache coverage: {len(cached_images)}/{len(image_data)} ({cache_coverage:.1f}%)")

        # Try to load neighbors from cache for cached images
        neighbors_from_cache = {}
        neighbors_to_save = []  # Track new neighbors found for caching

        if cached_images:
            print(f"[Duplicate Finder] Loading {len(cached_images)} cached neighbor relationships...")
            if progress_callback:
                progress_callback(0, len(image_data), f'💾 Loading cache... {len(cached_images)} files')

            cached_phashes_list = [img['phash'] for img in cached_images]
            neighbors_from_cache = self.get_neighbors_from_cache(cached_phashes_list, threshold)
            print(f"[Duplicate Finder] ✅ Loaded neighbors for {len(neighbors_from_cache)} phashes from cache")

        # Step 3: Build BK-Tree (only if we need to search uncached files)
        bktree = None
        if uncached_images:
            if progress_callback:
                progress_callback(0, len(image_data), f'🌳 Building search tree for {len(uncached_images)} new files...')

            tree_build_start = time.time()
            bktree = BKTree()
            for idx, img in enumerate(image_data):  # Build tree with ALL images for accurate searching
                # Check for stop signal during BK-Tree build
                if stop_event and idx % 10000 == 0 and stop_event.is_set():
                    print(f"[Duplicate Finder] Stop signal received during BK-Tree build")
                    raise InterruptedError(f"Scan stopped by user during BK-Tree build")
                bktree.add(img)
            tree_build_time = time.time() - tree_build_start
            print(f"[Duplicate Finder] ✅ BK-Tree built: {bktree.size} nodes in {tree_build_time:.1f}s")

            if HAS_PSUTIL:
                current_memory_mb = process.memory_info().rss / 1024 / 1024
                print(f"[Duplicate Finder] Memory: {current_memory_mb:.1f} MB")
        else:
            print(f"[Duplicate Finder] ✅ All files in cache, skipping BK-Tree build")

        # Step 4: Find duplicates (hybrid: cache + BK-Tree)
        if progress_callback:
            progress_callback(0, len(image_data), '🔍 Finding duplicates...')

        duplicate_search_start = time.time()
        duplicate_groups = []
        processed = set()

        # Build a lookup map: phash -> image data
        phash_to_img = {img['phash']: img for img in image_data}

        for i, img1 in enumerate(image_data):
            # Check for stop signal more frequently (every iteration for better responsiveness)
            if stop_event and stop_event.is_set():
                print(f"[Duplicate Finder] Stop signal received, halting at {i}/{len(image_data)}")
                break

            # Report progress every 100 images with ETA
            if progress_callback and i > 0 and i % 100 == 0:
                elapsed = time.time() - duplicate_search_start
                speed = i / elapsed if elapsed > 0 else 0
                remaining = len(image_data) - i
                eta_seconds = remaining / speed if speed > 0 else 0

                if eta_seconds > 60:
                    eta_str = f"{int(eta_seconds // 60)}m{int(eta_seconds % 60)}s"
                else:
                    eta_str = f"{int(eta_seconds)}s"

                cache_info = f" | 💾 {len(cached_images)} cached" if cached_images else ""
                progress_callback(
                    i,
                    len(image_data),
                    f'🔍 Finding duplicates... ({i}/{len(image_data)}) | ETA: {eta_str}{cache_info}'
                )

            if img1['file_path'] in processed:
                continue

            # Try to get neighbors from cache first
            similar = []
            if img1['phash'] in neighbors_from_cache:
                # Use cached neighbors
                cached_neighbors = neighbors_from_cache[img1['phash']]
                for neighbor_phash, distance in cached_neighbors:
                    if neighbor_phash in phash_to_img:
                        similar.append(phash_to_img[neighbor_phash])
            elif bktree:
                # Use BK-Tree to find similar images (for uncached files)
                similar = bktree.search(img1['phash'], threshold)

                # Save new neighbors to cache
                for img2 in similar:
                    if img2['phash'] != img1['phash']:  # Don't save self-reference
                        # Calculate distance
                        dist = img1['phash'] - img2['phash']
                        neighbors_to_save.append((str(img1['phash']), str(img2['phash']), dist))
            else:
                # No tree and no cache (shouldn't happen)
                continue

            # Filter and build group
            group = []
            for img2 in similar:
                if img2['file_path'] not in processed:
                    # Create a copy to avoid modifying tree data
                    group.append(img2.copy())
                    processed.add(img2['file_path'])

            # Only add groups with 2+ images
            if len(group) >= 2:
                filename = os.path.basename(group[0]['file_path'])
                filesize = group[0]['filesize']

                # Skip if whitelisted
                if self.is_whitelisted(filename, filesize):
                    continue

                # Sort by resolution (descending)
                def get_resolution_pixels(img):
                    try:
                        w, h = img['resolution'].split('x')
                        return int(w) * int(h)
                    except:
                        return 0

                group.sort(key=get_resolution_pixels, reverse=True)

                # Remove phash from response (frontend doesn't need it, saves bandwidth)
                # Keep only essential fields for display
                for img in group:
                    # Remove phash to reduce JSON size (64-char hex string per image)
                    img.pop('phash', None)

                duplicate_groups.append(group)

                # Emit group in real-time (every 10 groups to reduce WebSocket overhead)
                if progress_callback and len(duplicate_groups) % 10 == 0:
                    # Send the last 10 groups
                    batch_start = max(0, len(duplicate_groups) - 10)
                    batch_groups = duplicate_groups[batch_start:]
                    progress_callback(
                        i,
                        len(image_data),
                        f'🔍 Finding duplicates... ({i}/{len(image_data)}) | Groups: {len(duplicate_groups)}',
                        {'groups_batch': batch_groups}
                    )

        duplicate_search_time = time.time() - duplicate_search_start
        total_time = time.time() - start_time

        print(f"[Duplicate Finder] ✅ Found {len(duplicate_groups)} groups in {duplicate_search_time:.1f}s")
        print(f"[Duplicate Finder] ⏱️  Total time: {total_time:.1f}s")

        # Save new neighbors to cache
        if neighbors_to_save:
            print(f"[Duplicate Finder] 💾 Saving {len(neighbors_to_save)} new neighbor relationships to cache...")
            self.save_neighbors(neighbors_to_save)
            print(f"[Duplicate Finder] ✅ Neighbor cache updated")

        if HAS_PSUTIL:
            final_memory_mb = process.memory_info().rss / 1024 / 1024
            print(f"[Duplicate Finder] Final memory: {final_memory_mb:.1f} MB")

        # Save scan results to cache for future use
        print(f"[Duplicate Finder] 💾 Saving scan results to cache...")
        self.save_scan_cache(file_paths, threshold, duplicate_groups)
        print(f"[Duplicate Finder] ✅ Scan results cached")

        # Return results with metadata
        result = {
            'duplicate_groups': duplicate_groups,
            'total_files': len(file_paths) + len(skipped_files),
            'scanned_files': len(file_paths),
            'skipped_files': skipped_files,
            'error_files': error_files,
            'stats': {
                'total_time': total_time,
                'groups_found': len(duplicate_groups),
                'files_skipped': len(skipped_files),
                'files_errored': len(error_files)
            }
        }

        return result
