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
            cache = PHashCache()
            print(f"[Duplicate Finder] Computing hashes and finding duplicates...")

            # Create progress callback
            def progress_callback(current, total, message):
                emit_progress(scan_id, current, total, message)

            duplicate_groups = cache.find_duplicates(image_files, threshold, progress_callback)
            print(f"[Duplicate Finder] Found {len(duplicate_groups)} duplicate groups")
        except Exception as e:
            error_msg = str(e)
            print(f"[Duplicate Finder] Error: {error_msg}")
            emit_error(scan_id, error_msg)
            return {"error": error_msg}, 500

        # Count total duplicates
        duplicate_count = sum(len(group) for group in duplicate_groups)

        result = {
            "scan_id": scan_id,
            "duplicate_groups": duplicate_groups,
            "total_files": len(image_files),
            "duplicate_count": duplicate_count
        }

        # Emit completion event
        emit_complete(scan_id, result)

        return result


@ns.route("/delete")
class DeleteResource(Resource):
    def post(self):
        """
        Delete (move) files to the configured delete target path.

        Request body:
        {
            "files": ["/path/to/file1.jpg", "/path/to/file2.jpg"]
        }

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
        delete_target = settings_manager.get_delete_target_path()

        if not delete_target:
            return {"error": "Delete target path not configured"}, 400

        # Create delete target directory if needed
        os.makedirs(delete_target, exist_ok=True)

        success_count = 0
        failed_count = 0
        errors = []

        for file_path in files:
            if not os.path.exists(file_path):
                errors.append(f"File not found: {file_path}")
                failed_count += 1
                continue

            try:
                # Generate new filename with path suffix
                # /Users/you/Photos/2023/IMG_001.jpg -> IMG_001_Users_you_Photos_2023.jpg
                original_name = os.path.basename(file_path)
                name_without_ext, ext = os.path.splitext(original_name)
                dir_path = os.path.dirname(file_path)

                # Convert path to safe filename suffix
                path_suffix = dir_path.replace('/', '_').replace('\\', '_')
                # Remove leading underscores
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
