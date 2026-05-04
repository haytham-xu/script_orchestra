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

# Cache database path
CACHE_DB = Path(__file__).parent / '.phash_cache.db'

class PHashCache:
    def __init__(self):
        self.db_path = CACHE_DB
        self._init_db()

    def _init_db(self):
        """Initialize database and create tables if needed"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS image_hashes (
                file_path TEXT PRIMARY KEY,
                phash TEXT NOT NULL,
                mtime REAL NOT NULL,
                resolution TEXT NOT NULL,
                filesize INTEGER NOT NULL
            )
        ''')

        # Create index for faster lookups
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_phash ON image_hashes(phash)
        ''')

        conn.commit()
        conn.close()

    def get_hash(self, file_path: str) -> Optional[Dict]:
        """
        Get cached hash for a file.
        Returns None if not cached or file was modified.
        """
        if not os.path.exists(file_path):
            return None

        stat = os.stat(file_path)
        current_mtime = stat.st_mtime

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            'SELECT phash, mtime, resolution, filesize FROM image_hashes WHERE file_path = ?',
            (file_path,)
        )
        row = cursor.fetchone()
        conn.close()

        if row and abs(row[1] - current_mtime) < 0.001:  # mtime match
            return {
                'phash': row[0],
                'resolution': row[2],
                'filesize': row[3]
            }

        return None

    def set_hash(self, file_path: str, phash: str, resolution: str, filesize: int):
        """Cache hash for a file"""
        stat = os.stat(file_path)
        mtime = stat.st_mtime

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO image_hashes (file_path, phash, mtime, resolution, filesize)
            VALUES (?, ?, ?, ?, ?)
        ''', (file_path, phash, mtime, resolution, filesize))

        conn.commit()
        conn.close()

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
