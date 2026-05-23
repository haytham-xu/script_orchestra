"""
Duplicate Finder API Controller
"""
import os
import uuid
import shutil
from pathlib import Path
from flask import request, send_file
from flask_restx import Namespace, Resource
from .phash_cache import PHashCache
from .settings_manager import settings_manager
from .websocket_service import emit_progress, emit_complete, emit_error
from .scan_manager import scan_manager

ns = Namespace("")

# Image extensions (excluding .heic as it's not in duplicate range)
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp')


@ns.route("/image")
class ImageResource(Resource):
    def get(self):
        """
        Get image file for preview

        Query params:
            path: Absolute path to the image file

        Returns:
            Image file with appropriate content type
        """
        file_path = request.args.get('path')
        if not file_path:
            return {"error": "Missing 'path' parameter"}, 400

        # Security: Check if file exists and is actually an image
        if not os.path.exists(file_path):
            return {"error": "File not found"}, 404

        if not file_path.lower().endswith(IMAGE_EXTS):
            return {"error": "Not an image file"}, 400

        try:
            return send_file(file_path, mimetype=f'image/{Path(file_path).suffix[1:]}')
        except Exception as e:
            return {"error": str(e)}, 500


@ns.route("/scan")
class ScanResource(Resource):
    def post(self):
        """
        Scan directories for duplicate images.

        Request body:
        {
            "paths": ["/path/1", "/path/2"],
            "threshold": 90,  // optional, override settings
            "scan_id": "scan-123"  // optional, for WebSocket progress tracking
        }

        Response:
        {
            "scan_id": "scan-123",
            "duplicate_groups": [
                [
                    {
                        "file_path": "/path/to/image1.jpg",
                        "phash": "abc123...",
                        "resolution": "1920x1080",
                        "filesize": 1234567
                    },
                    ...
                ]
            ],
            "total_files": 100,
            "duplicate_count": 10
        }
        """
        data = request.json
        if not data or 'paths' not in data:
            return {"error": "Missing 'paths' in request"}, 400

        paths = data['paths']
        threshold_pct = data.get('threshold', settings_manager.get_settings()['similarity_threshold'])
        scan_id = data.get('scan_id', str(uuid.uuid4()))

        # Convert percentage to hamming distance
        max_distance = 64
        threshold = int((100 - threshold_pct) / 100 * max_distance)

        print(f"[Duplicate Finder] Scan ID: {scan_id}")
        print(f"[Duplicate Finder] Scanning paths: {paths}")
        print(f"[Duplicate Finder] Threshold: {threshold_pct}% (hamming distance: {threshold})")

        # Get exclude paths from settings
        exclude_paths = settings_manager.get_settings().get('exclude_folder_paths', [])
        exclude_paths_abs = [os.path.abspath(p) for p in exclude_paths if os.path.exists(p)]
        if exclude_paths_abs:
            print(f"[Duplicate Finder] Excluding paths: {exclude_paths_abs}")

        # Collect all image files from paths
        image_files = []
        for path in paths:
            if not os.path.exists(path):
                print(f"[Duplicate Finder] Path not found: {path}")
                continue

            if os.path.isfile(path):
                if path.lower().endswith(IMAGE_EXTS):
                    image_files.append(os.path.abspath(path))
            elif os.path.isdir(path):
                # Recursively scan directory
                print(f"[Duplicate Finder] Scanning directory: {path}")
                for root, dirs, files in os.walk(path):
                    # Check if current directory should be excluded
                    root_abs = os.path.abspath(root)
                    should_exclude = any(
                        root_abs.startswith(exclude_path)
                        for exclude_path in exclude_paths_abs
                    )
                    if should_exclude:
                        print(f"[Duplicate Finder] Excluding directory: {root_abs}")
                        continue

                    for file in files:
                        if file.lower().endswith(IMAGE_EXTS):
                            full_path = os.path.join(root, file)
                            image_files.append(os.path.abspath(full_path))

        print(f"[Duplicate Finder] Found {len(image_files)} image files")

        if not image_files:
            result = {
                "scan_id": scan_id,
                "duplicate_groups": [],
                "total_files": 0,
                "duplicate_count": 0
            }
            emit_complete(scan_id, result)
            return result

        # Find duplicates with progress callback
        try:
            # Register scan for stop management
            stop_event = scan_manager.start_scan(scan_id)

            cache = PHashCache()
            print(f"[Duplicate Finder] Computing hashes and finding duplicates...")

            # Create progress callback that supports extra_data and stop checking
            def progress_callback(current, total, message, extra_data=None):
                # Check if scan should stop
                if scan_manager.is_stopped(scan_id):
                    raise InterruptedError(f"Scan {scan_id} was stopped by user")
                emit_progress(scan_id, current, total, message, extra_data)

            scan_result = cache.find_duplicates(image_files, threshold, progress_callback, stop_event)

            # Extract duplicate groups from result
            duplicate_groups = scan_result['duplicate_groups']
            error_files = scan_result.get('error_files', [])
            skipped_files = scan_result.get('skipped_files', [])

            print(f"[Duplicate Finder] Found {len(duplicate_groups)} duplicate groups")
            if error_files:
                print(f"[Duplicate Finder] ⚠️  {len(error_files)} files had errors")
            if skipped_files:
                print(f"[Duplicate Finder] 🚫 {len(skipped_files)} files were skipped")
        except InterruptedError as e:
            error_msg = str(e)
            print(f"[Duplicate Finder] Scan stopped: {error_msg}")
            scan_manager.complete_scan(scan_id)
            emit_error(scan_id, error_msg)
            return {"error": error_msg, "stopped": True}, 200
        except Exception as e:
            error_msg = str(e)
            print(f"[Duplicate Finder] Error: {error_msg}")
            scan_manager.complete_scan(scan_id)
            emit_error(scan_id, error_msg)
            return {"error": error_msg}, 500

        # Count total duplicates
        duplicate_count = sum(len(group) for group in duplicate_groups)

        # Get folder_root_paths from settings for path simplification
        folder_root_paths = settings_manager.get_settings().get('folder_root_paths', {})

        # Add display_path to each image (remove root_path prefix and filename)
        for group in duplicate_groups:
            for img in group:
                file_path = img['file_path']

                # Find the matching root path for this file
                root_path = None
                for folder_path, folder_root in folder_root_paths.items():
                    if file_path.startswith(folder_root):
                        root_path = folder_root
                        break

                # Remove root_path prefix if found
                if root_path:
                    relative_path = file_path[len(root_path):].lstrip('/')
                else:
                    relative_path = file_path

                # Remove filename, keep only directory path
                dir_path = os.path.dirname(relative_path)
                img['display_path'] = dir_path if dir_path else '/'
                img['filename'] = os.path.basename(file_path)

        result = {
            "scan_id": scan_id,
            "duplicate_groups": duplicate_groups,
            "total_files": scan_result.get('total_files', len(image_files)),
            "scanned_files": scan_result.get('scanned_files', len(image_files)),
            "duplicate_count": duplicate_count,
            "error_files": error_files,
            "skipped_files": skipped_files,
            "stats": scan_result.get('stats', {})
        }

        # Emit completion event with summary only (not full result)
        # This prevents WebSocket crashes when handling large datasets (e.g., 640k+ files)
        completion_summary = {
            "scan_id": scan_id,
            "total_files": result["total_files"],
            "scanned_files": result["scanned_files"],
            "duplicate_count": duplicate_count,
            "groups_count": len(duplicate_groups),
            "error_count": len(error_files),
            "skipped_count": len(skipped_files),
            "stats": result["stats"]
        }
        emit_complete(scan_id, completion_summary)

        # Clean up scan manager
        scan_manager.complete_scan(scan_id)

        return result


@ns.route("/stop")
class StopScanResource(Resource):
    def post(self):
        """
        Stop an active scan gracefully.

        Request body:
        {
            "scan_id": "scan-123"
        }

        Response:
        {
            "message": "Scan stop signal sent",
            "scan_id": "scan-123"
        }
        """
        data = request.json
        if not data or 'scan_id' not in data:
            return {"error": "Missing 'scan_id' in request"}, 400

        scan_id = data['scan_id']

        if scan_manager.stop_scan(scan_id):
            return {
                "message": f"Stop signal sent to scan {scan_id}",
                "scan_id": scan_id
            }
        else:
            return {
                "error": f"Scan {scan_id} not found or already completed",
                "scan_id": scan_id
            }, 404


@ns.route("/active-scans")
class ActiveScansResource(Resource):
    def get(self):
        """Get list of active scan IDs"""
        active_scans = scan_manager.get_active_scans()
        return {
            "active_scans": active_scans,
            "count": len(active_scans)
        }


@ns.route("/delete")
class DeleteResource(Resource):
    def post(self):
        """
        Delete (move) files to the configured delete target path.

        Request body:
        {
            "files": ["/path/to/file1.jpg", "/path/to/file2.jpg"],
            "deep_path_delete": "/path/to/match"  // optional: preserve folder structure for files under this path
        }

        Deep path delete behavior:
        - Files under deep_path_delete: preserve relative folder structure
          Example: /a/folder1/sub/file.jpg -> /to_del/sub/file.jpg
        - Files NOT under deep_path_delete: flatten with path suffix (original behavior)
          Example: /b/folder2/file.jpg -> /to_del/file_b_folder2.jpg

        Response:
        {
            "success": 2,
            "failed": 0,
            "errors": []
        }
        """
        data = request.json
        if not data or 'files' not in data:
            return {"error": "Missing 'files' in request"}, 400

        files = data['files']
        deep_path_delete = data.get('deep_path_delete')
        delete_target = settings_manager.get_delete_target_path()

        if not delete_target:
            return {"error": "Delete target path not configured"}, 400

        # Create delete target directory if needed
        os.makedirs(delete_target, exist_ok=True)

        success_count = 0
        failed_count = 0
        errors = []
        deleted_folders = []

        # Normalize deep_path_delete for comparison
        deep_path_abs = None
        if deep_path_delete:
            deep_path_abs = os.path.abspath(deep_path_delete)
            print(f"[Duplicate Finder] Deep path delete mode: {deep_path_abs}")

        # Delete files
        for file_path in files:
            if not os.path.exists(file_path):
                errors.append(f"File not found: {file_path}")
                failed_count += 1
                continue

            try:
                abs_file_path = os.path.abspath(file_path)

                # Check if file is under deep_path_delete
                if deep_path_abs and abs_file_path.startswith(deep_path_abs + os.sep):
                    # Deep path mode: preserve folder structure
                    # Calculate relative path from deep_path_delete
                    relative_path = os.path.relpath(abs_file_path, deep_path_abs)
                    dest_path = os.path.join(delete_target, relative_path)

                    # Create parent directories if needed
                    dest_dir = os.path.dirname(dest_path)
                    os.makedirs(dest_dir, exist_ok=True)

                    # Handle name collision
                    if os.path.exists(dest_path):
                        name_without_ext, ext = os.path.splitext(dest_path)
                        counter = 1
                        while os.path.exists(dest_path):
                            dest_path = f"{name_without_ext}_{counter}{ext}"
                            counter += 1

                    # Move file
                    shutil.move(abs_file_path, dest_path)
                    success_count += 1
                    print(f"[Duplicate Finder] Moved file (deep): {abs_file_path} -> {dest_path}")

                else:
                    # Normal mode: flatten to delete_target root with path suffix
                    original_name = os.path.basename(file_path)
                    name_without_ext, ext = os.path.splitext(original_name)
                    dir_path = os.path.dirname(file_path)

                    # Convert path to safe filename suffix
                    path_suffix = dir_path.replace('/', '_').replace('\\', '_')
                    path_suffix = path_suffix.lstrip('_')

                    new_filename = f"{name_without_ext}_{path_suffix}{ext}"
                    dest_path = os.path.join(delete_target, new_filename)

                    # Handle name collision
                    counter = 1
                    while os.path.exists(dest_path):
                        new_filename = f"{name_without_ext}_{path_suffix}_{counter}{ext}"
                        dest_path = os.path.join(delete_target, new_filename)
                        counter += 1

                    # Move file
                    shutil.move(file_path, dest_path)
                    success_count += 1

            except Exception as e:
                errors.append(f"Failed to move {file_path}: {str(e)}")
                failed_count += 1

        return {
            "success": success_count,
            "failed": failed_count,
            "errors": errors
        }


@ns.route("/settings")
class SettingsResource(Resource):
    def get(self):
        """Get current settings"""
        return settings_manager.get_settings()

    def post(self):
        """Update settings"""
        data = request.json
        if not data:
            return {"error": "No data provided"}, 400

        current = settings_manager.get_settings()
        current.update(data)
        settings_manager.save_settings(current)

        return {"message": "Settings updated", "settings": current}


@ns.route("/open-folder")
class OpenFolderResource(Resource):
    def post(self):
        """
        Open folder in system file manager.

        Request body:
        {
            "folder_path": "/path/to/folder"
        }

        Response:
        {
            "success": true,
            "message": "Folder opened successfully"
        }
        """
        import subprocess
        import platform

        data = request.json
        if not data or 'folder_path' not in data:
            return {"error": "Missing 'folder_path' in request"}, 400

        folder_path = data['folder_path']

        if not os.path.exists(folder_path):
            return {"error": "Folder not found"}, 404

        if not os.path.isdir(folder_path):
            return {"error": "Path is not a directory"}, 400

        try:
            # Open folder based on OS
            system = platform.system()
            if system == 'Darwin':  # macOS
                subprocess.Popen(['open', folder_path])
            elif system == 'Windows':
                subprocess.Popen(['explorer', folder_path])
            elif system == 'Linux':
                subprocess.Popen(['xdg-open', folder_path])
            else:
                return {"error": f"Unsupported operating system: {system}"}, 400

            return {
                "success": True,
                "message": "Folder opened successfully"
            }
        except Exception as e:
            return {"error": str(e)}, 500


@ns.route("/whitelist")
class WhitelistResource(Resource):
    def get(self):
        """Get all whitelisted items"""
        try:
            cache = PHashCache()
            whitelist = cache.get_whitelist()
            return {"whitelist": whitelist}
        except Exception as e:
            return {"error": str(e)}, 500

    def post(self):
        """
        Add files to whitelist by filename + filesize

        Request body:
        {
            "filename": "IMG_001.jpg",
            "filesize": 1234567,
            "note": "Optional note",
            "preview_path": "Optional path to preview image"
        }
        """
        data = request.json
        if not data or 'filename' not in data or 'filesize' not in data:
            return {"error": "Missing 'filename' or 'filesize'"}, 400

        filename = data['filename']
        filesize = data['filesize']
        note = data.get('note')
        preview_path = data.get('preview_path')

        try:
            cache = PHashCache()
            cache.add_to_whitelist(filename, filesize, note, preview_path)
            return {"message": "Added to whitelist successfully"}
        except Exception as e:
            return {"error": str(e)}, 500

    def delete(self):
        """
        Remove from whitelist

        Query params:
            filename: File name
            filesize: File size in bytes
        """
        filename = request.args.get('filename')
        filesize = request.args.get('filesize')

        if not filename or not filesize:
            return {"error": "Missing 'filename' or 'filesize'"}, 400

        try:
            filesize = int(filesize)
            cache = PHashCache()
            cache.remove_from_whitelist(filename, filesize)
            return {"message": "Removed from whitelist successfully"}
        except ValueError:
            return {"error": "Invalid filesize value"}, 400
        except Exception as e:
            return {"error": str(e)}, 500


@ns.route("/cleanup")
class CleanupResource(Resource):
    def post(self):
        """
        Clean up database by removing entries for files that no longer exist.

        This will:
        1. Scan folder_paths to get all existing image files
        2. Get all records from database
        3. Remove database entries for files that don't exist
        4. Also remove from whitelist if file doesn't exist

        Response:
        {
            "removed_hashes": 10,
            "removed_whitelist": 2,
            "message": "Cleanup complete"
        }
        """
        try:
            cache = PHashCache()
            settings = settings_manager.get_settings()
            folder_paths = settings.get('folder_paths', [])

            if not folder_paths:
                return {"error": "No folder paths configured"}, 400

            print(f"[Duplicate Finder] Starting cleanup for paths: {folder_paths}")

            # Step 1: Collect all existing image files
            existing_files = set()
            for path in folder_paths:
                if not os.path.exists(path):
                    print(f"[Duplicate Finder] Path not found: {path}")
                    continue

                if os.path.isdir(path):
                    for root, dirs, files in os.walk(path):
                        for file in files:
                            if file.lower().endswith(IMAGE_EXTS):
                                full_path = os.path.abspath(os.path.join(root, file))
                                existing_files.add(full_path)

            print(f"[Duplicate Finder] Found {len(existing_files)} existing image files")

            # Step 2: Clean up database
            removed_hashes, removed_whitelist = cache.cleanup_missing_files(existing_files)

            print(f"[Duplicate Finder] Cleanup complete: removed {removed_hashes} hash entries, {removed_whitelist} whitelist entries")

            return {
                "removed_hashes": removed_hashes,
                "removed_whitelist": removed_whitelist,
                "message": f"Cleanup complete: removed {removed_hashes} hash entries and {removed_whitelist} whitelist entries"
            }
        except Exception as e:
            error_msg = str(e)
            print(f"[Duplicate Finder] Cleanup error: {error_msg}")
            return {" error": error_msg}, 500


@ns.route("/verify")
class VerifyResource(Resource):
    def post(self):
        """
        Verify which files from the provided list still exist on filesystem.
        Returns detailed information about missing files and affected groups.

        Request body:
        {
            "duplicate_groups": [  // The duplicate groups to verify
                [
                    {"file_path": "/path/to/file1.jpg", ...},
                    {"file_path": "/path/to/file2.jpg", ...}
                ],
                ...
            ]
        }

        Response:
        {
            "missing_files": ["/path/to/file1.jpg", ...],
            "missing_count": 10,
            "affected_groups": [
                {
                    "group_index": 0,
                    "missing_files": ["/path/to/file1.jpg"],
                    "remaining_files": ["/path/to/file2.jpg"]
                }
            ],
            "cleaned_groups": [  // Groups with missing files removed and groups with <2 files removed
                [
                    {"file_path": "/path/to/file2.jpg", ...}
                ]
            ],
            "removed_groups_count": 5  // Number of groups removed due to <2 remaining files
        }
        """
        data = request.json
        if not data or 'duplicate_groups' not in data:
            return {"error": "Missing 'duplicate_groups' in request"}, 400

        duplicate_groups = data['duplicate_groups']

        try:
            cache = PHashCache()

            # Collect all file paths from all groups
            all_files = []
            file_to_group_indices = {}  # Map file_path to list of group indices

            for group_idx, group in enumerate(duplicate_groups):
                for img in group:
                    file_path = img['file_path']
                    all_files.append(file_path)
                    if file_path not in file_to_group_indices:
                        file_to_group_indices[file_path] = []
                    file_to_group_indices[file_path].append(group_idx)

            # Verify which files still exist
            verification = cache.verify_files_exist(all_files)
            missing_files = verification['missing']

            if not missing_files:
                return {
                    "missing_files": [],
                    "missing_count": 0,
                    "affected_groups": [],
                    "cleaned_groups": duplicate_groups,
                    "removed_groups_count": 0
                }

            # Find affected groups
            affected_group_indices = set()
            for missing_file in missing_files:
                if missing_file in file_to_group_indices:
                    affected_group_indices.update(file_to_group_indices[missing_file])

            # Build detailed response
            affected_groups = []
            cleaned_groups = []
            removed_groups_count = 0

            for group_idx, group in enumerate(duplicate_groups):
                group_missing = []
                group_remaining = []

                for img in group:
                    if img['file_path'] in missing_files:
                        group_missing.append(img['file_path'])
                    else:
                        group_remaining.append(img)

                if group_idx in affected_group_indices:
                    affected_groups.append({
                        'group_index': group_idx,
                        'missing_files': group_missing,
                        'remaining_files': [img['file_path'] for img in group_remaining]
                    })

                # Only keep groups with 2+ remaining files
                if len(group_remaining) >= 2:
                    cleaned_groups.append(group_remaining)
                else:
                    removed_groups_count += 1

            print(f"[Duplicate Finder] Verify complete: {len(missing_files)} missing files, {removed_groups_count} groups removed")

            return {
                "missing_files": missing_files,
                "missing_count": len(missing_files),
                "affected_groups": affected_groups,
                "cleaned_groups": cleaned_groups,
                "removed_groups_count": removed_groups_count
            }

        except Exception as e:
            error_msg = str(e)
            print(f"[Duplicate Finder] Verify error: {error_msg}")
            return {"error": error_msg}, 500

