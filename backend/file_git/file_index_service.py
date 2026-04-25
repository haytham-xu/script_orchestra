"""
File Index Service - Scans files and tracks changes
Uses file size + mtime for change detection (cross-platform compatible)
"""
import os
import hashlib
import json
from typing import Dict, List, Tuple
from datetime import datetime


class FileIndexService:
    """Scans local files and generates index for change tracking"""

    @staticmethod
    def scan_local_files(local_path: str, progress_callback=None) -> Dict[str, Dict]:
        """
        Scan local folder and generate file index

        Args:
            local_path: Absolute path to local folder
            progress_callback: Optional callback(current, total, filename)

        Returns:
            Dict of {path_hash: {middle_path, size, mtime}}
        """
        local_dict = {}
        all_files = []

        # First pass: collect all files
        for root, dirnames, filenames in os.walk(local_path):
            # Skip hidden directories
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]

            for filename in filenames:
                # Skip hidden files
                if filename.startswith('.'):
                    continue

                file_path = os.path.join(root, filename)
                all_files.append(file_path)

        total = len(all_files)

        # Second pass: index files with progress
        for idx, file_path in enumerate(all_files):
            try:
                # Get relative path (middle_path)
                middle_path = os.path.relpath(file_path, local_path)
                middle_path = middle_path.replace('\\', '/')  # Normalize to Unix path

                # Get file stats (size + mtime)
                stat = os.stat(file_path)
                file_size = stat.st_size
                file_mtime = stat.st_mtime

                # Generate hash of middle_path as key
                path_hash = hashlib.md5(middle_path.encode('utf-8')).hexdigest()

                local_dict[path_hash] = {
                    'middle_path': middle_path,
                    'size': file_size,
                    'mtime': file_mtime
                }

                # Progress callback
                if progress_callback:
                    progress_callback(idx + 1, total, middle_path)

            except Exception as e:
                print(f"[FileIndex] Error scanning {file_path}: {e}")
                continue

        return local_dict

    @staticmethod
    def load_buffer_index(repo_path: str) -> Dict[str, Dict]:
        """
        Load buffer index (last synced state)

        Args:
            repo_path: Repository root path

        Returns:
            Buffer index dict
        """
        buffer_index_path = os.path.join(repo_path, '.fgit', 'buffer_index.json')

        if not os.path.exists(buffer_index_path):
            return {}

        try:
            with open(buffer_index_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[FileIndex] Error loading buffer index: {e}")
            return {}

    @staticmethod
    def save_buffer_index(repo_path: str, index_dict: Dict[str, Dict]):
        """
        Save buffer index

        Args:
            repo_path: Repository root path
            index_dict: Index to save
        """
        buffer_index_path = os.path.join(repo_path, '.fgit', 'buffer_index.json')

        try:
            with open(buffer_index_path, 'w', encoding='utf-8') as f:
                json.dump(index_dict, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[FileIndex] Error saving buffer index: {e}")

    @staticmethod
    def compare_indexes(local_index: Dict, buffer_index: Dict) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        """
        Compare local and buffer indexes to find changes

        Args:
            local_index: Current local file index
            buffer_index: Last synced buffer index

        Returns:
            Tuple of (added, modified, deleted) file lists
        """
        added = []
        modified = []
        deleted = []

        # Find added and modified files
        for path_hash, local_file in local_index.items():
            if path_hash not in buffer_index:
                # New file
                added.append({
                    'middle_path': local_file['middle_path'],
                    'size': local_file['size'],
                    'mtime': local_file['mtime']
                })
            else:
                buffer_file = buffer_index[path_hash]
                # Check if modified (size or mtime changed)
                if (local_file['size'] != buffer_file['size'] or
                    local_file['mtime'] != buffer_file['mtime']):
                    modified.append({
                        'middle_path': local_file['middle_path'],
                        'size': local_file['size'],
                        'mtime': local_file['mtime'],
                        'old_size': buffer_file['size'],
                        'old_mtime': buffer_file['mtime']
                    })

        # Find deleted files
        for path_hash, buffer_file in buffer_index.items():
            if path_hash not in local_index:
                deleted.append({
                    'middle_path': buffer_file['middle_path'],
                    'size': buffer_file['size'],
                    'mtime': buffer_file['mtime']
                })

        return added, modified, deleted

    @staticmethod
    def get_repo_status(repo_path: str, progress_callback=None) -> Dict:
        """
        Get repository status (added/modified/deleted files)

        Args:
            repo_path: Repository root path
            progress_callback: Optional progress callback

        Returns:
            Status dict with added, modified, deleted lists
        """
        print(f"[FileIndex] Scanning repository: {repo_path}")

        # Scan current local files
        local_index = FileIndexService.scan_local_files(repo_path, progress_callback)

        # Load last synced state
        buffer_index = FileIndexService.load_buffer_index(repo_path)

        # Compare to find changes
        added, modified, deleted = FileIndexService.compare_indexes(local_index, buffer_index)

        print(f"[FileIndex] Changes found - Added: {len(added)}, Modified: {len(modified)}, Deleted: {len(deleted)}")

        return {
            'added': added,
            'modified': modified,
            'deleted': deleted,
            'total_files': len(local_index)
        }
