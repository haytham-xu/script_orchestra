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

# Cache database path - use non-hidden file
CACHE_DB = Path(__file__).parent / 'phash_cache.db'

class PHashCache:
    def __init__(self, db_path: str = None):
        """
        Initialize PHash cache
        Args:
            db_path: Optional custom database path. If None, uses default location.
        """
        self.db_path = Path(db_path) if db_path else CACHE_DB
        self._init_db()

    def _init_db(self):
        """Initialize database and create tables if needed"""
        conn = sqlite3.connect(self.db_path)
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
        conn.close()

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

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # First try exact match (filename + filesize + file_path)
        cursor.execute(
            'SELECT phash, mtime, resolution FROM image_hashes WHERE filename = ? AND filesize = ? AND file_path = ?',
            (filename, filesize, file_path)
        )
        row = cursor.fetchone()

        if row and abs(row[1] - current_mtime) < 0.001:  # mtime match
            conn.close()
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
        conn.close()

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

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO image_hashes (filename, filesize, file_path, phash, mtime, resolution)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (filename, filesize, file_path, phash, mtime, resolution))

        conn.commit()
        conn.close()

    def update_file_path(self, filename: str, filesize: int, old_path: str, new_path: str, new_mtime: float):
        """Update file path when file is moved"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE image_hashes
            SET file_path = ?, mtime = ?
            WHERE filename = ? AND filesize = ? AND file_path = ?
        ''', (new_path, new_mtime, filename, filesize, old_path))

        conn.commit()
        conn.close()

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
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO whitelist (filename, filesize, added_time, note, preview_path)
            VALUES (?, ?, ?, ?, ?)
        ''', (filename, filesize, time.time(), note, preview_path))

        conn.commit()
        conn.close()

    def remove_from_whitelist(self, filename: str, filesize: int):
        """Remove a file from whitelist"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            DELETE FROM whitelist WHERE filename = ? AND filesize = ?
        ''', (filename, filesize))

        conn.commit()
        conn.close()

    def is_whitelisted(self, filename: str, filesize: int) -> bool:
        """Check if a file is in whitelist"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            'SELECT 1 FROM whitelist WHERE filename = ? AND filesize = ?',
            (filename, filesize)
        )
        result = cursor.fetchone()
        conn.close()

        return result is not None

    def get_whitelist(self) -> List[Dict]:
        """Get all whitelisted items"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('SELECT filename, filesize, added_time, note, preview_path FROM whitelist')
        rows = cursor.fetchall()
        conn.close()

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
        conn = sqlite3.connect(self.db_path)
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
        conn.close()

        return removed_hashes, removed_whitelist

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

        Args:
            file_paths: List of image file paths to compare
            threshold: Maximum hamming distance to consider duplicates (0-64)
                      Lower = more strict. 5 is good for compressed duplicates.
            progress_callback: Optional callback(current, total, message) for progress updates

        Returns:
            List of duplicate groups, each group is a list of file info dicts
        """
        total_files = len(file_paths)

        # Compute all hashes with progress updates
        image_data = []
        for i, file_path in enumerate(file_paths):
            if progress_callback:
                progress_callback(i + 1, total_files, f'Computing hash for {os.path.basename(file_path)}')

            hash_data = self.compute_hash(file_path)
            if hash_data:
                image_data.append({
                    'file_path': file_path,
                    'phash': imagehash.hex_to_hash(hash_data['phash']),
                    'resolution': hash_data['resolution'],
                    'filesize': hash_data['filesize']
                })

        # Notify hash computation complete
        if progress_callback:
            progress_callback(total_files, total_files, 'Hash computation complete. Finding duplicates...')

        # Find duplicates using hamming distance with progress updates
        duplicate_groups = []
        processed = set()
        total_comparisons = len(image_data)

        for i, img1 in enumerate(image_data):
            # Report progress every 10 images or at the end
            if progress_callback and (i % 10 == 0 or i == total_comparisons - 1):
                progress_callback(
                    i + 1,
                    total_comparisons,
                    f'Finding duplicates... ({i + 1}/{total_comparisons})'
                )

            if img1['file_path'] in processed:
                continue

            group = [img1]
            processed.add(img1['file_path'])

            # Compare with remaining images
            for img2 in image_data[i+1:]:
                if img2['file_path'] in processed:
                    continue

                # Calculate hamming distance
                distance = img1['phash'] - img2['phash']

                if distance <= threshold:
                    group.append(img2)
                    processed.add(img2['file_path'])

            # Only add groups with 2+ images
            if len(group) >= 2:
                # Check if this group should be filtered by whitelist
                # Get the filename+filesize from the first file in group
                first_file = group[0]['file_path']
                filename = os.path.basename(first_file)
                filesize = group[0]['filesize']

                # Skip if whitelisted
                if self.is_whitelisted(filename, filesize):
                    continue

                # Sort group by resolution (descending - highest first)
                # Parse resolution like "1920x1080" -> width * height
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

        return duplicate_groups
