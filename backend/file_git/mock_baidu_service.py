"""
Mock Baidu Cloud Service
Simulates Baidu Pan API for local testing
"""
import os
import json
import time
import uuid
import shutil
from typing import Dict, List


# Default storage path - relative to project root
DEFAULT_STORAGE_ROOT = os.path.join(
    os.path.dirname(__file__),
    '../../test_data/fgit/mock_baidu_cloud'
)


class MockBaiduCloudService:
    """Mock Baidu Cloud service that simulates the real API"""

    def __init__(self, storage_root: str = DEFAULT_STORAGE_ROOT):
        """
        Initialize mock service

        Args:
            storage_root: Root directory for mock cloud storage
        """
        self.storage_root = os.path.abspath(storage_root)
        os.makedirs(storage_root, exist_ok=True)
        print(f"[MockBaidu] Initialized with storage at: {self.storage_root}")

    def _convert_to_unix_path(self, path: str) -> str:
        """Convert path to Unix format"""
        path = path.replace('\\', '/')
        if not path.startswith('/'):
            path = '/' + path
        return path

    def _get_mock_path(self, cloud_path: str) -> str:
        """Get local mock storage path from cloud path"""
        cloud_path = self._convert_to_unix_path(cloud_path)
        return os.path.join(self.storage_root, cloud_path.lstrip('/'))

    def pre_upload(self, cloud_path: str, file_size: int, md5_list: List[str]) -> Dict:
        """
        Mock pre-upload (precreate)

        Args:
            cloud_path: Remote path
            file_size: File size
            md5_list: List of chunk MD5s

        Returns:
            Response with upload_id
        """
        time.sleep(0.5)  # Simulate network delay
        upload_id = str(uuid.uuid4())

        print(f"[MockBaidu] Pre-upload: {cloud_path} ({file_size} bytes)")

        return {
            "errno": 0,
            "uploadid": upload_id,
            "return_type": 1,
            "path": cloud_path
        }

    def upload_chunk(self, upload_id: str, chunk_content: bytes, chunk_id: int, cloud_path: str) -> Dict:
        """
        Mock chunk upload

        Args:
            upload_id: Upload session ID
            chunk_content: Chunk data
            chunk_id: Chunk sequence number
            cloud_path: Remote path

        Returns:
            Success response
        """
        time.sleep(1)  # Simulate upload delay

        # Store chunk temporarily
        chunk_dir = os.path.join(self.storage_root, '.chunks', upload_id)
        os.makedirs(chunk_dir, exist_ok=True)

        chunk_file = os.path.join(chunk_dir, f'chunk_{chunk_id}')
        with open(chunk_file, 'wb') as f:
            f.write(chunk_content)

        print(f"[MockBaidu] Uploaded chunk {chunk_id} for {cloud_path}")

        return {
            "errno": 0,
            "md5": "mock_md5"
        }

    def create_file(self, cloud_path: str, upload_id: str, md5_list: List[str], file_size: int) -> Dict:
        """
        Mock create file (finalize upload)

        Args:
            cloud_path: Remote path
            upload_id: Upload session ID
            md5_list: List of chunk MD5s
            file_size: File size

        Returns:
            Response with fs_id
        """
        time.sleep(0.5)  # Simulate finalization delay

        # Merge chunks
        chunk_dir = os.path.join(self.storage_root, '.chunks', upload_id)
        mock_path = self._get_mock_path(cloud_path)
        os.makedirs(os.path.dirname(mock_path), exist_ok=True)

        with open(mock_path, 'wb') as outfile:
            chunk_id = 0
            while True:
                chunk_file = os.path.join(chunk_dir, f'chunk_{chunk_id}')
                if not os.path.exists(chunk_file):
                    break
                with open(chunk_file, 'rb') as infile:
                    outfile.write(infile.read())
                chunk_id += 1

        # Clean up chunks
        if os.path.exists(chunk_dir):
            shutil.rmtree(chunk_dir)

        print(f"[MockBaidu] Created file: {cloud_path}")

        return {
            "errno": 0,
            "fs_id": abs(hash(cloud_path)) % (10 ** 8),
            "md5": "mock_md5",
            "server_filename": os.path.basename(cloud_path),
            "path": cloud_path,
            "size": file_size
        }

    def download_file(self, cloud_path: str, local_path: str) -> Dict:
        """
        Mock download file

        Args:
            cloud_path: Remote path
            local_path: Local destination path

        Returns:
            Success response
        """
        time.sleep(1)  # Simulate download delay

        mock_path = self._get_mock_path(cloud_path)

        if not os.path.exists(mock_path):
            return {
                "errno": -9,
                "error": "File not found"
            }

        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        shutil.copy2(mock_path, local_path)

        print(f"[MockBaidu] Downloaded: {cloud_path} -> {local_path}")

        return {
            "errno": 0
        }

    def list_folder(self, cloud_dir: str) -> Dict:
        """
        Mock list folder

        Args:
            cloud_dir: Remote directory path

        Returns:
            Response with file list
        """
        time.sleep(0.5)  # Simulate API delay

        mock_path = self._get_mock_path(cloud_dir)

        file_list = []
        if os.path.exists(mock_path) and os.path.isdir(mock_path):
            for item in os.listdir(mock_path):
                if item.startswith('.'):
                    continue
                full_path = os.path.join(mock_path, item)
                item_cloud_path = os.path.join(cloud_dir, item).replace('\\', '/')

                file_info = {
                    "fs_id": abs(hash(item_cloud_path)) % (10 ** 8),
                    "path": item_cloud_path,
                    "server_filename": item,
                    "size": os.path.getsize(full_path) if os.path.isfile(full_path) else 0,
                    "isdir": 1 if os.path.isdir(full_path) else 0
                }
                file_list.append(file_info)

        print(f"[MockBaidu] Listed folder: {cloud_dir} ({len(file_list)} items)")

        return {
            "errno": 0,
            "list": file_list
        }

    def list_all_recursive(self, cloud_dir: str, start: int = 0, limit: int = 1000) -> Dict:
        """
        Mock recursive list (get_multimedia_listall)

        Args:
            cloud_dir: Remote directory path
            start: Start index
            limit: Limit per page

        Returns:
            Response with file list and pagination
        """
        time.sleep(1)  # Simulate scanning delay

        mock_path = self._get_mock_path(cloud_dir)

        all_files = []
        if os.path.exists(mock_path):
            for root, dirs, files in os.walk(mock_path):
                # Filter hidden directories
                dirs[:] = [d for d in dirs if not d.startswith('.')]

                for filename in files:
                    if filename.startswith('.'):
                        continue

                    full_path = os.path.join(root, filename)
                    relative_path = os.path.relpath(full_path, mock_path)
                    cloud_file_path = os.path.join(cloud_dir, relative_path).replace('\\', '/')

                    file_info = {
                        "fs_id": abs(hash(cloud_file_path)) % (10 ** 8),
                        "path": cloud_file_path,
                        "server_filename": filename,
                        "size": os.path.getsize(full_path),
                        "isdir": 0
                    }
                    all_files.append(file_info)

        # Pagination
        chunk = all_files[start:start + limit]
        has_more = 1 if len(all_files) > start + limit else 0

        print(f"[MockBaidu] Listed recursively: {cloud_dir} ({len(all_files)} files, returned {len(chunk)})")

        return {
            "errno": 0,
            "has_more": has_more,
            "list": chunk
        }

    def delete_file_folder(self, cloud_path: str) -> Dict:
        """
        Mock delete file/folder

        Args:
            cloud_path: Remote path to delete

        Returns:
            Success response
        """
        time.sleep(0.5)  # Simulate API delay

        mock_path = self._get_mock_path(cloud_path)

        if not os.path.exists(mock_path):
            return {
                "errno": -9,
                "error": "File not found"
            }

        if os.path.isdir(mock_path):
            shutil.rmtree(mock_path)
        else:
            os.remove(mock_path)

        print(f"[MockBaidu] Deleted: {cloud_path}")

        return {
            "errno": 0
        }

    def create_folder(self, cloud_path: str) -> Dict:
        """
        Mock create folder

        Args:
            cloud_path: Remote folder path

        Returns:
            Success response
        """
        time.sleep(0.5)  # Simulate API delay

        mock_path = self._get_mock_path(cloud_path)
        os.makedirs(mock_path, exist_ok=True)

        print(f"[MockBaidu] Created folder: {cloud_path}")

        return {
            "errno": 0,
            "fs_id": abs(hash(cloud_path)) % (10 ** 8),
            "path": cloud_path
        }


# Global instance
mock_baidu_instance = MockBaiduCloudService()
