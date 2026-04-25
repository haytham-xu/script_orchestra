"""
File-Git Sync Service - Push and Pull operations
"""
import os
import json
import hashlib
from typing import Dict, List
from .file_index_service import FileIndexService
from .mock_baidu_service import mock_baidu_instance
from .websocket_service import emit_progress, emit_log


class SyncService:
    """Handles push and pull operations between local and cloud"""

    @staticmethod
    def _read_chunk(file_path: str, chunk_size: int = 4 * 1024 * 1024) -> List[bytes]:
        """
        Read file in chunks

        Args:
            file_path: Path to file
            chunk_size: Size of each chunk (default 4MB)

        Returns:
            List of chunk bytes
        """
        chunks = []
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                chunks.append(chunk)
        return chunks

    @staticmethod
    def _calculate_md5_list(chunks: List[bytes]) -> List[str]:
        """Calculate MD5 for each chunk"""
        return [hashlib.md5(chunk).hexdigest() for chunk in chunks]

    @staticmethod
    def push_file(local_file_path: str, remote_path: str, progress_callback=None) -> Dict:
        """
        Push a file to cloud

        Args:
            local_file_path: Local file path
            remote_path: Remote cloud path
            progress_callback: Optional callback(current, total, message)

        Returns:
            Result dict with success status
        """
        try:
            # Read file in chunks
            if progress_callback:
                progress_callback(0, 100, f"Reading file: {os.path.basename(local_file_path)}")

            file_size = os.path.getsize(local_file_path)
            chunks = SyncService._read_chunk(local_file_path)
            md5_list = SyncService._calculate_md5_list(chunks)

            # Pre-upload
            if progress_callback:
                progress_callback(10, 100, "Preparing upload...")

            pre_response = mock_baidu_instance.pre_upload(remote_path, file_size, md5_list)
            if pre_response.get('errno') != 0:
                return {
                    'success': False,
                    'error': 'Pre-upload failed',
                    'response': pre_response
                }

            upload_id = pre_response['uploadid']

            # Upload chunks
            for idx, chunk in enumerate(chunks):
                progress = 10 + int((idx / len(chunks)) * 70)
                if progress_callback:
                    progress_callback(progress, 100, f"Uploading chunk {idx + 1}/{len(chunks)}...")

                chunk_response = mock_baidu_instance.upload_chunk(
                    upload_id, chunk, idx, remote_path
                )
                if chunk_response.get('errno') != 0:
                    return {
                        'success': False,
                        'error': f'Chunk upload failed at chunk {idx}',
                        'response': chunk_response
                    }

            # Finalize
            if progress_callback:
                progress_callback(90, 100, "Finalizing upload...")

            create_response = mock_baidu_instance.create_file(
                remote_path, upload_id, md5_list, file_size
            )
            if create_response.get('errno') != 0:
                return {
                    'success': False,
                    'error': 'File creation failed',
                    'response': create_response
                }

            if progress_callback:
                progress_callback(100, 100, "Upload complete")

            return {
                'success': True,
                'fs_id': create_response.get('fs_id'),
                'path': remote_path
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    @staticmethod
    def pull_file(remote_path: str, local_file_path: str, progress_callback=None) -> Dict:
        """
        Pull a file from cloud

        Args:
            remote_path: Remote cloud path
            local_file_path: Local destination path
            progress_callback: Optional callback(current, total, message)

        Returns:
            Result dict with success status
        """
        try:
            if progress_callback:
                progress_callback(0, 100, f"Downloading: {os.path.basename(remote_path)}")

            # Ensure parent directory exists
            os.makedirs(os.path.dirname(local_file_path), exist_ok=True)

            # Download file
            response = mock_baidu_instance.download_file(remote_path, local_file_path)

            if response.get('errno') != 0:
                return {
                    'success': False,
                    'error': 'Download failed',
                    'response': response
                }

            if progress_callback:
                progress_callback(100, 100, "Download complete")

            return {
                'success': True,
                'path': local_file_path
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    @staticmethod
    def push_changes(repo_path: str, remote_root: str, changes: Dict, repo_id: str = None) -> Dict:
        """
        Push all changes to cloud with file-level granularity

        Strategy: Process files one by one, update buffer_index after each success
        This allows resume on failure - already uploaded files won't be re-uploaded

        Args:
            repo_path: Local repository path
            remote_root: Remote cloud root path
            changes: Dict with 'added', 'modified', 'deleted' lists
            repo_id: Optional repository ID for WebSocket progress updates

        Returns:
            Result dict with statistics
        """
        results = {
            'success': True,
            'uploaded': 0,
            'deleted': 0,
            'errors': []
        }

        # Load current buffer index
        buffer_index = FileIndexService.load_buffer_index(repo_path)

        # Calculate total operations
        files_to_upload = changes.get('added', []) + changes.get('modified', [])
        files_to_delete = changes.get('deleted', [])
        total_ops = len(files_to_upload) + len(files_to_delete)
        current_op = 0

        if repo_id:
            emit_progress(repo_id, 'push', 'starting', 0, total_ops, 'Starting push operation...')
            emit_log(repo_id, 'info', f'Pushing {len(files_to_upload)} files, deleting {len(files_to_delete)} files')

        # Upload added and modified files - one by one
        for file_info in files_to_upload:
            current_op += 1
            middle_path = file_info['middle_path']
            local_path = os.path.join(repo_path, middle_path)
            remote_path = os.path.join(remote_root, middle_path).replace('\\', '/')

            is_new = file_info in changes.get('added', [])
            action = 'new' if is_new else 'modified'

            if repo_id:
                emit_progress(repo_id, 'push', 'uploading', current_op, total_ops, f'Uploading ({action}): {middle_path}')
                emit_log(repo_id, 'info', f'Uploading {middle_path} ({action})')

            result = SyncService.push_file(local_path, remote_path)

            if result['success']:
                results['uploaded'] += 1

                # Immediately update buffer_index for this file
                path_hash = hashlib.md5(middle_path.encode('utf-8')).hexdigest()
                stat = os.stat(local_path)
                buffer_index[path_hash] = {
                    'middle_path': middle_path,
                    'size': stat.st_size,
                    'mtime': stat.st_mtime
                }
                # Save buffer index after each successful upload
                FileIndexService.save_buffer_index(repo_path, buffer_index)

                if repo_id:
                    emit_log(repo_id, 'info', f'✓ Uploaded: {middle_path}')
            else:
                error_msg = result.get('error', 'Upload failed')
                results['errors'].append({
                    'file': middle_path,
                    'operation': 'upload',
                    'error': error_msg
                })
                if repo_id:
                    emit_log(repo_id, 'error', f'✗ Failed: {middle_path} - {error_msg}')

        # Delete removed files from cloud - one by one
        for file_info in files_to_delete:
            current_op += 1
            middle_path = file_info['middle_path']
            remote_path = os.path.join(remote_root, middle_path).replace('\\', '/')

            if repo_id:
                emit_progress(repo_id, 'push', 'deleting', current_op, total_ops, f'Deleting: {middle_path}')
                emit_log(repo_id, 'info', f'Deleting {middle_path}')

            response = mock_baidu_instance.delete_file_folder(remote_path)

            if response.get('errno') == 0 or response.get('errno') == -9:  # Success or already not exists
                results['deleted'] += 1

                # Remove from buffer_index immediately
                path_hash = hashlib.md5(middle_path.encode('utf-8')).hexdigest()
                if path_hash in buffer_index:
                    del buffer_index[path_hash]
                    # Save buffer index after each successful deletion
                    FileIndexService.save_buffer_index(repo_path, buffer_index)

                if repo_id:
                    emit_log(repo_id, 'info', f'✓ Deleted: {middle_path}')
            else:
                error_msg = response.get('error', 'Delete failed')
                results['errors'].append({
                    'file': middle_path,
                    'operation': 'delete',
                    'error': error_msg
                })
                if repo_id:
                    emit_log(repo_id, 'error', f'✗ Failed to delete: {middle_path} - {error_msg}')

        # Final status
        if repo_id:
            if len(results['errors']) == 0:
                emit_progress(repo_id, 'push', 'complete', total_ops, total_ops, 'Push completed successfully')
                emit_log(repo_id, 'info', f'✓ Push complete: {results["uploaded"]} uploaded, {results["deleted"]} deleted')
            else:
                emit_progress(repo_id, 'push', 'error', current_op, total_ops, f'Push completed with {len(results["errors"])} errors')
                emit_log(repo_id, 'warning', f'⚠ Push completed with errors: {len(results["errors"])} failed')

        results['success'] = len(results['errors']) == 0
        return results

    @staticmethod
    def pull_changes(repo_path: str, remote_root: str, repo_id: str = None) -> Dict:
        """
        Pull all changes from cloud with file-level granularity

        Strategy: Compare remote (buffer_index) with local files
        - Download files that exist in buffer but missing/modified locally
        - Delete local files that don't exist in buffer (deleted from cloud)

        Args:
            repo_path: Local repository path
            remote_root: Remote cloud root path
            repo_id: Optional repository ID for WebSocket progress updates

        Returns:
            Result dict with statistics
        """
        results = {
            'success': True,
            'downloaded': 0,
            'deleted': 0,
            'errors': []
        }

        try:
            # Load buffer index (this is our source of truth for what's on cloud)
            buffer_index = FileIndexService.load_buffer_index(repo_path)

            if not buffer_index:
                return {
                    'success': False,
                    'error': 'No buffer index found - nothing to pull'
                }

            # Scan current local state
            local_scan = FileIndexService.scan_repository(repo_path)
            local_files = {}
            for file_info in local_scan.get('files', []):
                middle_path = file_info['middle_path']
                local_files[middle_path] = file_info

            # Determine what needs to be downloaded and deleted
            files_to_download = []
            files_to_delete = []

            # Files in buffer that are missing or modified locally should be downloaded
            for path_hash, buf_file in buffer_index.items():
                middle_path = buf_file['middle_path']

                if middle_path not in local_files:
                    # File exists in cloud but not locally -> download
                    files_to_download.append({
                        'middle_path': middle_path,
                        'size': buf_file.get('size', 0),
                        'action': 'new'
                    })
                else:
                    local_file = local_files[middle_path]
                    # Check if modified (different size or mtime)
                    if (local_file.get('size') != buf_file.get('size') or
                        abs(local_file.get('mtime', 0) - buf_file.get('mtime', 0)) > 1):
                        files_to_download.append({
                            'middle_path': middle_path,
                            'size': buf_file.get('size', 0),
                            'action': 'modified'
                        })

            # Local files not in buffer should be deleted
            buffer_paths = set(f['middle_path'] for f in buffer_index.values())
            for middle_path in local_files.keys():
                if middle_path not in buffer_paths:
                    files_to_delete.append({
                        'middle_path': middle_path,
                        'size': local_files[middle_path].get('size', 0)
                    })

            total_ops = len(files_to_download) + len(files_to_delete)
            current_op = 0

            if repo_id:
                emit_progress(repo_id, 'pull', 'starting', 0, total_ops, 'Starting pull operation...')
                emit_log(repo_id, 'info', f'Pulling {len(files_to_download)} files, deleting {len(files_to_delete)} local files')

            # Download files - one by one
            for file_info in files_to_download:
                current_op += 1
                middle_path = file_info['middle_path']
                local_path = os.path.join(repo_path, middle_path)
                remote_path = os.path.join(remote_root, middle_path).replace('\\', '/')
                action = file_info['action']

                if repo_id:
                    emit_progress(repo_id, 'pull', 'downloading', current_op, total_ops, f'Downloading ({action}): {middle_path}')
                    emit_log(repo_id, 'info', f'Downloading {middle_path} ({action})')

                result = SyncService.pull_file(remote_path, local_path)

                if result['success']:
                    results['downloaded'] += 1

                    if repo_id:
                        emit_log(repo_id, 'info', f'✓ Downloaded: {middle_path}')
                else:
                    results['errors'].append({
                        'path': middle_path,
                        'error': result.get('error', 'Unknown error')
                    })

                    if repo_id:
                        emit_log(repo_id, 'error', f'✗ Failed: {middle_path} - {result.get("error")}')

            # Delete local files that don't exist in cloud
            for file_info in files_to_delete:
                current_op += 1
                middle_path = file_info['middle_path']
                local_path = os.path.join(repo_path, middle_path)

                if repo_id:
                    emit_progress(repo_id, 'pull', 'deleting', current_op, total_ops, f'Local deleting: {middle_path}')
                    emit_log(repo_id, 'info', f'Deleting local file {middle_path}')

                try:
                    if os.path.exists(local_path):
                        os.remove(local_path)
                        results['deleted'] += 1

                        # Remove empty parent directories
                        parent_dir = os.path.dirname(local_path)
                        while parent_dir != repo_path:
                            if os.path.isdir(parent_dir) and not os.listdir(parent_dir):
                                os.rmdir(parent_dir)
                                parent_dir = os.path.dirname(parent_dir)
                            else:
                                break

                        if repo_id:
                            emit_log(repo_id, 'info', f'✓ Deleted: {middle_path}')
                    else:
                        if repo_id:
                            emit_log(repo_id, 'warning', f'⚠ File not found: {middle_path}')

                except Exception as e:
                    results['errors'].append({
                        'path': middle_path,
                        'error': str(e)
                    })

                    if repo_id:
                        emit_log(repo_id, 'error', f'✗ Failed to delete: {middle_path} - {str(e)}')

            # Final status
            if repo_id:
                if len(results['errors']) == 0:
                    emit_progress(repo_id, 'pull', 'complete', total_ops, total_ops, 'Pull completed successfully')
                    emit_log(repo_id, 'info', f'✓ Pull complete: {results["downloaded"]} downloaded, {results["deleted"]} deleted')
                else:
                    emit_progress(repo_id, 'pull', 'error', current_op, total_ops, f'Pull completed with {len(results["errors"])} errors')
                    emit_log(repo_id, 'warning', f'⚠ Pull completed with errors: {len(results["errors"])} failed')

            results['success'] = len(results['errors']) == 0
            return results

        except Exception as e:
            if repo_id:
                emit_log(repo_id, 'error', f'✗ Pull failed: {str(e)}')
            return {
                'success': False,
                'error': str(e),
                'downloaded': results['downloaded'],
                'deleted': results['deleted'],
                'errors': results['errors']
            }
