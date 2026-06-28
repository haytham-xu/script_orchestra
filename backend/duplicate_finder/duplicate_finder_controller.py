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
from .cypress_test_support import TestDataSetup

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


@ns.route("/rescan-from-cache")
class RescanFromCacheResource(Resource):
    def post(self):
        """
        Rescan for duplicates using cached phash data from database.
        No file scanning needed - only recalculates duplicate groups with new threshold.

        Request body:
        {
            "threshold": 90,
            "scan_id": "optional-scan-id",
            "verify_files": true  // optional: verify files still exist (default: true)
        }

        Response: Same as /scan endpoint
        """
        data = request.json or {}
        threshold_percent = data.get('threshold', settings_manager.get_settings()['similarity_threshold'])
        verify_files = data.get('verify_files', True)

        # Convert percentage to hamming distance (0-64)
        threshold = int((100 - threshold_percent) / 100 * 64)

        # Generate or use provided scan ID
        scan_id = data.get('scan_id', str(uuid.uuid4()))

        print(f"[Duplicate Finder] Rescan from cache: {scan_id}")
        print(f"[Duplicate Finder] Threshold: {threshold_percent}% (hamming distance: {threshold})")
        print(f"[Duplicate Finder] Verify files exist: {verify_files}")

        try:
            # Register scan for stop management
            stop_event = scan_manager.start_scan(scan_id)

            cache = PHashCache()

            # Load all cached images from database
            print(f"[Duplicate Finder] Loading cached phash data from database...")
            if progress_callback:
                emit_progress(scan_id, 0, 1, "Loading cached phash data...")

            image_data = cache.get_all_cached_images(file_exists_check=verify_files)

            if not image_data:
                scan_manager.complete_scan(scan_id)
                emit_error(scan_id, "No cached image data found in database")
                return {"error": "No cached image data found. Please run a full scan first."}, 400

            print(f"[Duplicate Finder] Loaded {len(image_data)} images from cache")

            # Create progress callback that supports stop checking
            def progress_callback(current, total, message, extra_data=None):
                if scan_manager.is_stopped(scan_id):
                    raise InterruptedError(f"Scan {scan_id} was stopped by user")
                emit_progress(scan_id, current, total, message, extra_data)

            # Use find_duplicates with cached data (skipping hash computation)
            # We need to convert phash strings back to hash objects
            import imagehash
            for img in image_data:
                img['phash'] = imagehash.hex_to_hash(img['phash'])

            # Call the internal duplicate detection logic
            # This will use neighbor cache and skip hash computation
            print(f"[Duplicate Finder] Finding duplicates with cached data...")

            # Simulate the duplicate detection part of find_duplicates
            # We'll call a helper method that only does BK-Tree + duplicate detection
            from .phash_cache import BKTree
            import time

            start_time = time.time()

            # Check neighbor cache coverage
            current_phashes = [str(img['phash']) for img in image_data]
            cached_phashes = cache.get_cached_phashes()

            cached_images = []
            uncached_images = []
            for img in image_data:
                if str(img['phash']) in cached_phashes:
                    cached_images.append(img)
                else:
                    uncached_images.append(img)

            cache_coverage = len(cached_images) / len(image_data) * 100 if image_data else 0
            print(f"[Duplicate Finder] Neighbor cache coverage: {len(cached_images)}/{len(image_data)} ({cache_coverage:.1f}%)")

            # Load neighbors from cache
            neighbors_from_cache = {}
            neighbors_to_save = []

            if cached_images:
                print(f"[Duplicate Finder] Loading {len(cached_images)} cached neighbor relationships...")
                emit_progress(scan_id, 0, len(image_data), f'💾 Loading cache... {len(cached_images)} files')

                cached_phashes_list = [str(img['phash']) for img in cached_images]
                neighbors_from_cache = cache.get_neighbors_from_cache(cached_phashes_list, threshold)
                print(f"[Duplicate Finder] ✅ Loaded neighbors for {len(neighbors_from_cache)} phashes from cache")

            # Build BK-Tree if needed
            bktree = None
            if uncached_images:
                emit_progress(scan_id, 0, len(image_data), f'🌳 Building search tree for {len(uncached_images)} new files...')

                tree_build_start = time.time()
                bktree = BKTree()
                for img in image_data:
                    bktree.add(img)
                tree_build_time = time.time() - tree_build_start
                print(f"[Duplicate Finder] ✅ BK-Tree built: {bktree.size} nodes in {tree_build_time:.1f}s")
            else:
                print(f"[Duplicate Finder] ✅ All files in cache, skipping BK-Tree build")

            # Find duplicates
            emit_progress(scan_id, 0, len(image_data), '🔍 Finding duplicates...')

            duplicate_search_start = time.time()
            duplicate_groups = []
            processed = set()

            # Build lookup map
            phash_to_img = {img['phash']: img for img in image_data}

            for i, img1 in enumerate(image_data):
                # Check for stop signal
                if stop_event and stop_event.is_set():
                    print(f"[Duplicate Finder] Stop signal received, halting at {i}/{len(image_data)}")
                    break

                # Report progress
                if i > 0 and i % 100 == 0:
                    elapsed = time.time() - duplicate_search_start
                    speed = i / elapsed if elapsed > 0 else 0
                    remaining = len(image_data) - i
                    eta_seconds = remaining / speed if speed > 0 else 0

                    if eta_seconds > 60:
                        eta_str = f"{int(eta_seconds // 60)}m{int(eta_seconds % 60)}s"
                    else:
                        eta_str = f"{int(eta_seconds)}s"

                    cache_info = f" | 💾 {len(cached_images)} cached" if cached_images else ""
                    emit_progress(
                        i,
                        len(image_data),
                        f'🔍 Finding duplicates... ({i}/{len(image_data)}) | ETA: {eta_str}{cache_info}'
                    )

                if img1['file_path'] in processed:
                    continue

                # Try cache first, then BK-Tree
                similar = []
                phash_str = str(img1['phash'])

                if phash_str in neighbors_from_cache:
                    # Use cached neighbors
                    cached_neighbors = neighbors_from_cache[phash_str]
                    for neighbor_phash, distance in cached_neighbors:
                        try:
                            neighbor_hash = imagehash.hex_to_hash(neighbor_phash)
                            if neighbor_hash in phash_to_img:
                                similar.append(phash_to_img[neighbor_hash])
                        except:
                            pass
                elif bktree:
                    # Use BK-Tree
                    similar = bktree.search(img1['phash'], threshold)

                    # Save new neighbors
                    for img2 in similar:
                        if img2['phash'] != img1['phash']:
                            dist = img1['phash'] - img2['phash']
                            neighbors_to_save.append((str(img1['phash']), str(img2['phash']), dist))

                # Build group
                group = []
                for img2 in similar:
                    if img2['file_path'] not in processed:
                        group.append(img2.copy())
                        processed.add(img2['file_path'])

                # Only add groups with 2+ images
                if len(group) >= 2:
                    filename = os.path.basename(group[0]['file_path'])
                    filesize = group[0]['filesize']

                    # Skip if whitelisted
                    if cache.is_whitelisted(filename, filesize):
                        continue

                    # Sort by resolution
                    def get_resolution_pixels(img):
                        try:
                            w, h = img['resolution'].split('x')
                            return int(w) * int(h)
                        except:
                            return 0

                    group.sort(key=get_resolution_pixels, reverse=True)

                    # Remove phash from response
                    for img in group:
                        img.pop('phash', None)

                    duplicate_groups.append(group)

                    # Emit groups in real-time
                    if len(duplicate_groups) % 10 == 0:
                        batch_start = max(0, len(duplicate_groups) - 10)
                        batch_groups = duplicate_groups[batch_start:]
                        emit_progress(
                            i,
                            len(image_data),
                            f'🔍 Finding duplicates... ({i}/{len(image_data)}) | Groups: {len(duplicate_groups)}',
                            {'groups_batch': batch_groups}
                        )

            duplicate_search_time = time.time() - duplicate_search_start
            total_time = time.time() - start_time

            print(f"[Duplicate Finder] ✅ Found {len(duplicate_groups)} groups in {duplicate_search_time:.1f}s")
            print(f"[Duplicate Finder] ⏱️  Total time: {total_time:.1f}s")

            # Save new neighbors
            if neighbors_to_save:
                print(f"[Duplicate Finder] 💾 Saving {len(neighbors_to_save)} new neighbor relationships...")
                cache.save_neighbors(neighbors_to_save)
                print(f"[Duplicate Finder] ✅ Neighbor cache updated")

            scan_result = {'duplicate_groups': duplicate_groups}

            duplicate_groups = scan_result['duplicate_groups']

            print(f"[Duplicate Finder] Found {len(duplicate_groups)} duplicate groups")

        except InterruptedError as e:
            error_msg = str(e)
            print(f"[Duplicate Finder] Rescan stopped: {error_msg}")
            scan_manager.complete_scan(scan_id)
            emit_error(scan_id, error_msg)
            return {"error": error_msg, "stopped": True}, 200
        except Exception as e:
            error_msg = str(e)
            print(f"[Duplicate Finder] Error during rescan: {error_msg}")
            import traceback
            traceback.print_exc()
            scan_manager.complete_scan(scan_id)
            emit_error(scan_id, error_msg)
            return {"error": error_msg}, 500

        # Count total duplicates
        duplicate_count = sum(len(group) for group in duplicate_groups)

        # Get folder_root_paths from settings
        folder_root_paths = settings_manager.get_settings().get('folder_root_paths', {})

        # Add display_path to each image
        for group in duplicate_groups:
            for img in group:
                file_path = img['file_path']

                # Find matching root_path
                dir_path = None
                for root_name, root_path in folder_root_paths.items():
                    if file_path.startswith(root_path):
                        rel_path = file_path[len(root_path):].lstrip(os.sep)
                        dir_path = os.path.dirname(rel_path)
                        break

                if dir_path is None:
                    dir_path = os.path.dirname(file_path)

                img['display_path'] = dir_path if dir_path else '/'
                img['filename'] = os.path.basename(file_path)

        result = {
            "scan_id": scan_id,
            "duplicate_groups": duplicate_groups,
            "total_files": len(image_data),
            "scanned_files": len(image_data),
            "duplicate_count": duplicate_count,
            "from_cache": True  # Indicate this was from cache
        }

        # Emit completion
        completion_summary = {
            "scan_id": scan_id,
            "total_files": result["total_files"],
            "scanned_files": result["scanned_files"],
            "duplicate_count": duplicate_count,
            "groups_count": len(duplicate_groups),
            "from_cache": True
        }
        emit_complete(scan_id, completion_summary)

        # Clean up scan manager
        scan_manager.complete_scan(scan_id)

        return result

@ns.route("/delete")
class DeleteResource(Resource):
    def post(self):
        """
        Delete (move) files to the configured delete target path.
        Files are moved preserving their relative path from the configured root_path.

        Request body:
        {
            "files": ["/path/to/file1.jpg", "/path/to/file2.jpg"],
            "deep_path_delete": "/path/to/match"  // optional: for backward compatibility (deprecated)
        }

        Deletion behavior:
        - Find the root_path for the file from folder_root_paths configuration
        - Calculate relative path from root_path
        - Move to: delete_target_path + relative_path

        Example:
        - Original file: /Users/.../duplicate_finder/test_delete/B_dup1/b_049.jpg
        - Root path: /Users/.../duplicate_finder/
        - Delete target: /Users/.../test_delete/to_del
        - Result: /Users/.../test_delete/to_del/test_delete/B_dup1/b_049.jpg

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

        # Get folder_paths (scan folders) - use them directly as root
        folder_paths = settings_manager.get_settings().get('folder_paths', [])

        # Create delete target directory if needed
        os.makedirs(delete_target, exist_ok=True)

        # === Step 5: pre-capture state for incremental group_stats repair ===
        workflow = get_workflow()
        try:
            abs_paths = [os.path.abspath(f) for f in files]
            ids_to_delete: list = []
            BATCH = 900
            conn0 = workflow._get_connection()
            cur0 = conn0.cursor()
            for i in range(0, len(abs_paths), BATCH):
                chunk = abs_paths[i:i + BATCH]
                ph = ','.join('?' * len(chunk))
                cur0.execute(f"SELECT id FROM image_hashes WHERE file_path IN ({ph})", chunk)
                ids_to_delete.extend(r[0] for r in cur0.fetchall())
            affected_capture = workflow.stats_collect_affected_before_mutation(ids_to_delete)
            print(f"[Delete] Pre-captured stats repair state for {len(ids_to_delete)} image_ids")
        except Exception as e:
            print(f"[Delete] WARNING: stats pre-capture failed (continuing without incremental repair): {e}")
            affected_capture = None

        success_count = 0
        failed_count = 0
        errors = []

        print(f"[Delete] Target directory: {delete_target}")
        print(f"[Delete] Scan folders configured: {len(folder_paths)} folders")

        # Delete files
        for file_path in files:
            if not os.path.exists(file_path):
                errors.append(f"File not found: {file_path}")
                failed_count += 1
                continue

            try:
                abs_file_path = os.path.abspath(file_path)

                # Find the scan folder that contains this file (use it as root)
                scan_folder = None
                for folder in folder_paths:
                    folder_abs = os.path.abspath(folder)
                    if abs_file_path.startswith(folder_abs + os.sep) or abs_file_path == folder_abs:
                        scan_folder = folder_abs
                        break

                if not scan_folder:
                    # Fallback: if no scan folder found, use the file's parent directory
                    scan_folder = os.path.dirname(abs_file_path)
                    print(f"[Delete] Warning: No scan folder found for {abs_file_path}, using parent directory")

                # Calculate relative path from scan folder
                try:
                    relative_path = os.path.relpath(abs_file_path, scan_folder)
                except ValueError:
                    # Different drives on Windows, fallback to filename only
                    relative_path = os.path.basename(abs_file_path)
                    print(f"[Delete] Warning: Cannot calculate relative path (different drives?), using filename only")

                # Construct destination path
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
                print(f"[Delete] ✓ Moved: {abs_file_path}")
                print(f"[Delete]   Scan folder: {scan_folder}")
                print(f"[Delete]   Relative: {relative_path}")
                print(f"[Delete]   Destination: {dest_path}")

                # Delete from database (image_hashes and phash_similarities)
                try:
                    workflow = get_workflow()
                    conn = workflow._get_connection()
                    cursor = conn.cursor()

                    # Find the image ID
                    cursor.execute('SELECT id FROM image_hashes WHERE file_path = ?', (abs_file_path,))
                    row = cursor.fetchone()

                    if row:
                        image_id = row[0]
                        # Delete from phash_similarities (where this image is involved)
                        cursor.execute('DELETE FROM phash_similarities WHERE image_id_a = ? OR image_id_b = ?',
                                     (image_id, image_id))
                        similarity_count = cursor.rowcount

                        # Delete from image_hashes
                        cursor.execute('DELETE FROM image_hashes WHERE id = ?', (image_id,))
                        conn.commit()

                        print(f"[Delete]   DB cleaned: removed image record (ID={image_id}) and {similarity_count} similarity records")
                    else:
                        print(f"[Delete]   DB: image not found in database (already cleaned or never scanned)")

                except Exception as db_error:
                    print(f"[Delete] Warning: Failed to clean database for {abs_file_path}: {db_error}")
                    # Don't fail the whole operation if DB cleanup fails

            except Exception as e:
                error_msg = f"Failed to move {file_path}: {str(e)}"
                errors.append(error_msg)
                failed_count += 1
                print(f"[Delete] ✗ {error_msg}")

        print(f"[Delete] Complete: {success_count} succeeded, {failed_count} failed")

        # === Step 5: repair group_stats now that image_hashes rows are gone ===
        repair_summary = None
        if affected_capture:
            try:
                repair_summary = workflow.stats_repair_after_mutation(affected_capture, remove_from_groups=False)
                print(f"[Delete] Stats repair: {repair_summary}")
            except Exception as e:
                print(f"[Delete] WARNING: stats repair failed: {e}")
                import traceback
                traceback.print_exc()

        return {
            "success": success_count,
            "failed": failed_count,
            "errors": errors,
            "stats_repair": repair_summary,
        }


@ns.route("/settings")
class SettingsResource(Resource):
    def get(self):
        """Get current settings"""
        from multiprocessing import cpu_count
        settings = settings_manager.get_settings()
        # Add system CPU count info
        settings['system_cpu_count'] = cpu_count()
        return settings

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
        """Get all whitelisted groups"""
        try:
            cache = PHashCache()
            groups = cache.get_whitelist_groups()
            # Also get old-style individual whitelist for compatibility
            whitelist = cache.get_whitelist()
            return {
                "whitelist_groups": groups,
                "whitelist": whitelist  # Keep for backward compatibility
            }
        except Exception as e:
            return {"error": str(e)}, 500

    def post(self):
        """
        Add a duplicate group to whitelist

        Request body:
        {
            "image_ids": [123, 456, 789]
        }
        """
        data = request.json
        if not data or 'image_ids' not in data:
            return {"error": "Missing 'image_ids'"}, 400

        image_ids = data['image_ids']
        if not isinstance(image_ids, list) or len(image_ids) < 2:
            return {"error": "Group must have at least 2 images"}, 400

        try:
            workflow = get_workflow()
            affected = workflow.stats_collect_affected_before_mutation(image_ids)

            cache = PHashCache()
            cache.add_group_to_whitelist(image_ids)

            repair = workflow.stats_repair_after_mutation(affected, remove_from_groups=True)
            print(f"[Whitelist Add] image_ids={len(image_ids)}, repair={repair}")
            return {"message": "Added group to whitelist successfully", "stats_repair": repair}
        except Exception as e:
            print(f"[Whitelist Add] ERROR: {e}")
            import traceback
            traceback.print_exc()
            return {"error": str(e)}, 500

    def delete(self):
        """
        Remove a whitelist group

        Query params:
            group_id: Whitelist group ID
        """
        group_id = request.args.get('group_id')

        if not group_id:
            return {"error": "Missing 'group_id'"}, 400

        try:
            group_id = int(group_id)
            cache = PHashCache()
            cache.remove_whitelist_group(group_id)
            return {"message": "Removed from whitelist successfully"}
        except ValueError:
            return {"error": "Invalid group_id value"}, 400
        except Exception as e:
            return {"error": str(e)}, 500


@ns.route("/whitelist/bulk-add-groups")
class WhitelistBulkAddGroupsResource(Resource):
    def post(self):
        """
        Bulk-add multiple groups to whitelist in one shot (e.g. an entire
        Phase 3 page). Performs ONE stats repair at the end so the operation
        scales with the number of unique images, not the number of groups.

        Request body:
        {
            "groups": [[1, 2, 3], [4, 5], [6, 7, 8, 9]]
        }

        Response:
        {
            "added_groups": 3,
            "skipped_groups": 0,
            "image_count": 9,
            "stats_repair": {...}
        }
        """
        data = request.json or {}
        groups = data.get('groups')
        if not isinstance(groups, list) or not groups:
            return {"error": "Missing or invalid 'groups' (expected non-empty list)"}, 400

        # Validate + collect unique image_ids
        valid_groups = []
        for g in groups:
            if isinstance(g, list) and len(g) >= 2 and all(isinstance(x, int) for x in g):
                valid_groups.append(g)
        skipped = len(groups) - len(valid_groups)

        if not valid_groups:
            return {"error": "No valid groups (each group needs ≥ 2 integer image_ids)"}, 400

        all_image_ids = list({iid for g in valid_groups for iid in g})

        try:
            workflow = get_workflow()
            affected = workflow.stats_collect_affected_before_mutation(all_image_ids)

            cache = PHashCache()
            added = 0
            for g in valid_groups:
                try:
                    cache.add_group_to_whitelist(g)
                    added += 1
                except Exception as e:
                    print(f"[Whitelist Bulk] WARNING: failed to add group {g}: {e}")
                    skipped += 1

            repair = workflow.stats_repair_after_mutation(affected, remove_from_groups=True)
            print(f"[Whitelist Bulk] added={added}, skipped={skipped}, unique_images={len(all_image_ids)}, repair={repair}")
            return {
                "added_groups": added,
                "skipped_groups": skipped,
                "image_count": len(all_image_ids),
                "stats_repair": repair,
            }
        except Exception as e:
            print(f"[Whitelist Bulk] ERROR: {e}")
            import traceback
            traceback.print_exc()
            return {"error": str(e)}, 500


@ns.route("/whitelist/cleanup")
class WhitelistCleanupResource(Resource):
    def post(self):
        """
        Clean up invalid whitelist groups (with < 2 members)

        Response:
        {
            "removed_count": 5,
            "message": "Cleanup complete"
        }
        """
        try:
            cache = PHashCache()
            removed = cache.cleanup_whitelist_groups()
            return {
                "removed_count": removed,
                "message": f"Cleaned up {removed} invalid whitelist groups"
            }
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


# ========== NEW 3-PHASE WORKFLOW ENDPOINTS ==========

from .phash_new_workflow import DuplicateFinderWorkflow

# Global workflow instance - will be lazily initialized
_workflow = None

def get_workflow():
    """Get workflow instance with current settings

    IMPORTANT: Once created, the workflow instance is NEVER recreated to preserve
    the _stop_event across Phase 1/2/3 operations and stop signals.
    """
    global _workflow
    db_path = settings_manager.get_phash_db_path()

    # Create workflow only if it doesn't exist
    if _workflow is None:
        _workflow = DuplicateFinderWorkflow(db_path=db_path)
        print(f"[Workflow] Initialized with database: {db_path}")
    elif hasattr(_workflow, 'db_path') and str(_workflow.db_path) != str(db_path):
        # Log warning if db_path changed, but DON'T recreate (to preserve _stop_event)
        print(f"[Workflow] WARNING: DB path changed from {_workflow.db_path} to {db_path}, but keeping existing workflow instance to preserve stop_event")

    return _workflow


@ns.route("/phase1/refresh")
class Phase1RefreshResource(Resource):
    def post(self):
        """
        Phase 1: Refresh image table
        - Scan filesystem
        - Sync DB (remove missing, add new)
        - Compute phash for new files
        - Set status='pending'

        Request body:
        {
            "paths": ["/path/1", "/path/2"]
        }

        Response:
        {
            "added": 100,
            "removed": 10,
            "skipped": 500,
            "errors": [],
            "elapsed": 12.5
        }
        """
        try:
            data = request.json
            if not data or 'paths' not in data:
                return {"error": "Missing 'paths' in request"}, 400

            paths = data['paths']
            scan_id = data.get('scan_id') or f"phase1-{uuid.uuid4().hex[:8]}"  # Use provided scan_id or generate one

            print(f"[Phase 1 API] Received request to scan {len(paths)} paths: {paths[:3]}...")  # Show first 3
            print(f"[Phase 1 API] Using scan_id: {scan_id}")

            # Read exclude folders from settings — same source as legacy /scan
            exclude_paths = settings_manager.get_settings().get('exclude_folder_paths', []) or []
            exclude_paths_abs = [os.path.abspath(p) for p in exclude_paths if p]
            if exclude_paths_abs:
                print(f"[Phase 1 API] Excluding paths: {exclude_paths_abs}")

            def is_excluded(p: str) -> bool:
                # True if `p` is exactly an exclude root or is contained inside one.
                # Uses os.sep boundary so /foo doesn't accidentally exclude /foobar.
                p_abs = os.path.abspath(p)
                for ex in exclude_paths_abs:
                    if p_abs == ex or p_abs.startswith(ex + os.sep):
                        return True
                return False

            # Collect all image files
            image_files = []
            excluded_dirs_pruned = 0
            for root_path in paths:
                if not os.path.exists(root_path):
                    print(f"[Phase 1 API] WARNING: Path does not exist: {root_path}")
                    continue

                if os.path.isfile(root_path):
                    if root_path.lower().endswith(IMAGE_EXTS):
                        if is_excluded(root_path):
                            print(f"[Phase 1 API] Skipping excluded file: {root_path}")
                            continue
                        image_files.append(root_path)
                else:
                    print(f"[Phase 1 API] Scanning directory: {root_path}")
                    for root, dirs, files in os.walk(root_path):
                        # If current dir is excluded, skip its files and prune descent
                        if is_excluded(root):
                            print(f"[Phase 1 API]   Excluding directory subtree: {root}")
                            dirs[:] = []
                            excluded_dirs_pruned += 1
                            continue
                        # Prune dirs that are exactly excluded roots (saves a recurse)
                        pruned = [d for d in dirs if is_excluded(os.path.join(root, d))]
                        if pruned:
                            for d in pruned:
                                print(f"[Phase 1 API]   Pruning excluded subdir: {os.path.join(root, d)}")
                            excluded_dirs_pruned += len(pruned)
                            dirs[:] = [d for d in dirs if d not in pruned]

                        for file in files:
                            if file.lower().endswith(IMAGE_EXTS):
                                image_files.append(os.path.join(root, file))

            print(f"[Phase 1 API] Found {len(image_files)} image files to process "
                  f"(excluded {excluded_dirs_pruned} dir subtree(s) via exclude_folder_paths)")

            # Progress callback for WebSocket updates
            print(f"[Phase 1 API] Starting phase 1 with scan_id: {scan_id}")

            def progress_cb(current, total, message):
                print(f"[Phase 1 API] Progress: {current}/{total} - {message}")
                emit_progress(scan_id, current, total, message)

            # Run phase 1
            workflow = get_workflow()
            print(f"[Phase 1 API] 🚀 Starting Phase 1 with workflow instance id={id(workflow)}")
            print(f"[Phase 1 API] Initial _stop_event.is_set() = {workflow._stop_event.is_set()}")
            print(f"[Phase 1 API] Calling workflow.phase1_refresh_images...")
            result = workflow.phase1_refresh_images(image_files, progress_callback=progress_cb)
            result['scan_id'] = scan_id

            print(f"[Phase 1 API] COMPLETE: Added={result['added']}, Removed={result['removed']}, Skipped={result['skipped']}, Time={result['elapsed']:.1f}s, Stopped={result.get('stopped', False)}")
            return result

        except InterruptedError as e:
            print(f"[Phase 1 API] Interrupted: {e}")
            return {"error": "stopped", "message": str(e)}, 499
        except Exception as e:
            error_msg = str(e)
            print(f"[Phase 1 API] ERROR: {error_msg}")
            import traceback
            traceback.print_exc()
            return {"error": error_msg}, 500


@ns.route("/phase1/stop")
class Phase1StopResource(Resource):
    def post(self):
        """Stop phase 1 (refresh)"""
        print("=" * 80)
        print("[Phase 1 API] 🛑 STOP request received")
        workflow = get_workflow()
        print(f"[Phase 1 API] Workflow instance: {workflow}, id={id(workflow)}")
        print(f"[Phase 1 API] Before set_stop: _stop_event.is_set() = {workflow._stop_event.is_set()}")
        workflow.set_stop()
        print(f"[Phase 1 API] After set_stop: _stop_event.is_set() = {workflow._stop_event.is_set()}")
        print("[Phase 1 API] ✅ Stop signal sent to workflow")
        print("=" * 80)
        return {"message": "Phase 1 stop signal sent"}


@ns.route("/phase2/build")
class Phase2BuildResource(Resource):
    def post(self):
        """
        Phase 2: Build phash_similarities table
        - Get all status='pending' images
        - Compute distances (brute force + multiprocessing)
        - Save to phash_similarities if distance ≤ threshold
        - Mark as status='computed'

        Request body:
        {
            "threshold_distance": 12  // optional, default 12 (80%)
        }

        Response:
        {
            "processed": 100,
            "similarities_found": 250,
            "elapsed": 60.2
        }
        """
        try:
            data = request.json or {}
            threshold_distance = data.get('threshold_distance', 12)
            scan_id = data.get('scan_id')  # Get scan_id from client if provided

            # Generate scan_id if not provided by client
            if not scan_id:
                scan_id = f"phase2-{uuid.uuid4().hex[:8]}"

            def progress_cb(current, total, message):
                emit_progress(scan_id, current, total, message)

            workflow = get_workflow()
            print(f"[Phase 2 API] 🚀 Starting Phase 2 with workflow instance id={id(workflow)}")
            print(f"[Phase 2 API] Initial _stop_event.is_set() = {workflow._stop_event.is_set()}")
            result = workflow.phase2_build_similarities(threshold_distance, progress_callback=progress_cb)
            result['scan_id'] = scan_id

            print(f"[Phase 2 API] COMPLETE: Processed={result['processed']}, Similarities={result['similarities_found']}, Time={result['elapsed']:.1f}s, Stopped={result.get('stopped', False)}")
            return result

        except InterruptedError as e:
            return {"error": "stopped", "message": str(e)}, 499
        except Exception as e:
            error_msg = str(e)
            print(f"[Phase 2] Error: {error_msg}")
            return {"error": error_msg}, 500


@ns.route("/phase2/stop")
class Phase2StopResource(Resource):
    def post(self):
        """Stop phase 2 (build similarities)"""
        print("=" * 80)
        print("[Phase 2 API] 🛑 STOP request received")
        workflow = get_workflow()
        print(f"[Phase 2 API] Workflow instance: {workflow}, id={id(workflow)}")
        print(f"[Phase 2 API] Before set_stop: _stop_event.is_set() = {workflow._stop_event.is_set()}")
        workflow.set_stop()
        print(f"[Phase 2 API] After set_stop: _stop_event.is_set() = {workflow._stop_event.is_set()}")
        print("[Phase 2 API] ✅ Stop signal sent to workflow")
        print("=" * 80)
        return {"message": "Phase 2 stop signal sent"}


@ns.route("/phase2.5/materialize")
class Phase25MaterializeResource(Resource):
    def post(self):
        """
        Phase 2.5: Materialize duplicate groups + per-group stats.

        Manual trigger, runs between Phase 2 and Phase 3.

        Request body:
        {
            "threshold_percent": 80,            // optional, default 80
            "same_folder_filter": true          // optional, default true
        }

        Response:
        {
            "groups_count": int,
            "members_count": int,
            "whitelisted_dropped": int,
            "threshold_percent": int,
            "same_folder_filter": bool,
            "elapsed": float,
            "stopped": bool,
            "scan_id": "phase25-abc123"
        }
        """
        try:
            data = request.json or {}
            threshold_percent = int(data.get('threshold_percent', 80))
            same_folder_filter = bool(data.get('same_folder_filter', True))

            scan_id = f"phase25-{uuid.uuid4().hex[:8]}"

            def progress_cb(current, total, message):
                emit_progress(scan_id, current, total, message)

            print(f"[Phase 2.5 API] START: threshold={threshold_percent}%, same_folder_filter={same_folder_filter}")
            result = get_workflow().phase2_5_materialize_groups(
                threshold_percent=threshold_percent,
                same_folder_filter=same_folder_filter,
                progress_callback=progress_cb,
            )
            result['scan_id'] = scan_id
            print(f"[Phase 2.5 API] DONE: groups={result.get('groups_count', 0)}, elapsed={result.get('elapsed', 0):.1f}s, stopped={result.get('stopped', False)}")
            return result

        except InterruptedError as e:
            return {"error": "stopped", "message": str(e)}, 499
        except Exception as e:
            error_msg = str(e)
            print(f"[Phase 2.5 API] ERROR: {error_msg}")
            import traceback
            traceback.print_exc()
            return {"error": error_msg}, 500


@ns.route("/phase2.5/stop")
class Phase25StopResource(Resource):
    def post(self):
        """Stop phase 2.5 (materialize groups)"""
        print("[Phase 2.5 API] STOP request received")
        workflow = get_workflow()
        workflow.set_stop()
        print("[Phase 2.5 API] Stop signal sent")
        return {"message": "Phase 2.5 stop signal sent"}


@ns.route("/phase2.5/meta")
class Phase25MetaResource(Resource):
    def get(self):
        """Return current materialization metadata (which threshold, when, etc.)."""
        try:
            meta = get_workflow().get_materialization_meta()
            return {"meta": meta}
        except Exception as e:
            return {"error": str(e)}, 500


@ns.route("/phase3/get-duplicates")
class Phase3GetDuplicatesResource(Resource):
    def post(self):
        """
        Phase 3: Read materialized duplicate groups (strict mode).

        Requires Phase 2.5 to have run. If materialization is missing or its
        threshold doesn't match the request, returns HTTP 409 with an `error`
        marker so the frontend can prompt the user to (re-)run Phase 2.5.

        Request body:
        {
            "threshold_percent": 80,            // optional, default 80
            "page": 1,                          // 1-indexed, 0=all groups
            "page_size": 100,
            "sort_by": "folder_dup_count",      // optional; allowed: folder_dup_count,
                                                //   max_filesize, min_filesize,
                                                //   max_mtime, min_mtime, member_count
            "sort_order": "desc"                // optional, "asc" or "desc"
        }
        """
        try:
            data = request.json or {}
            threshold_percent = int(data.get('threshold_percent', 80))
            page = int(data.get('page', 1))
            page_size = int(data.get('page_size', 100))
            sort_by = data.get('sort_by', 'folder_dup_count')
            sort_order = data.get('sort_order', 'desc')

            print(f"[Phase 3 API] 🔍 Request: threshold={threshold_percent}%, page={page}, "
                  f"page_size={page_size}, sort_by={sort_by}, sort_order={sort_order}")

            folder_paths = settings_manager.get_settings().get('folder_paths', [])
            scan_id = f"phase3-{uuid.uuid4().hex[:8]}"

            def progress_cb(current, total, message):
                emit_progress(scan_id, current, total, message)

            result = get_workflow().phase3_get_duplicates(
                threshold_percent=threshold_percent,
                progress_callback=progress_cb,
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order,
                folder_paths=folder_paths,
            )
            result['scan_id'] = scan_id

            # Map materialization-related errors to HTTP 409 (Conflict)
            err = result.get('error')
            if err in ('no_materialization', 'threshold_mismatch'):
                print(f"[Phase 3 API] ⚠️ {err}: {result.get('message')}")
                return result, 409

            print(f"[Phase 3 API] ✅ Response: groups={len(result.get('groups', []))}, "
                  f"total_groups={result.get('total_groups', 0)}, "
                  f"page={result.get('current_page', 0)}/{result.get('total_pages', 0)}, "
                  f"elapsed={result.get('elapsed', 0) * 1000:.0f}ms")
            return result

        except InterruptedError as e:
            return {"error": "stopped", "message": str(e)}, 499
        except Exception as e:
            error_msg = str(e)
            print(f"[Phase 3] Error: {error_msg}")
            return {"error": error_msg}, 500


@ns.route("/phase3/stop")
class Phase3StopResource(Resource):
    def post(self):
        """Stop phase 3 (get duplicates)"""
        print("[Phase 3 API] Received STOP request")
        workflow = get_workflow()
        workflow.set_stop()
        print("[Phase 3 API] Stop signal sent to workflow")
        return {"message": "Phase 3 stop signal sent"}


@ns.route("/batch-delete-by-path")
class BatchDeleteByPathResource(Resource):
    def post(self):
        """
        Batch delete all duplicate files under a specific path across all groups

        Request body:
        {
            "deep_path": "/path/to/folder",  // Required: the path to scan
            "preview_only": true  // Optional: if true, only return matched files without deleting
        }

        Response (preview_only=true):
        {
            "matched_files": 100,
            "file_list": ["/path/to/file1.jpg", "/path/to/file2.jpg", ...],
            "preview": true
        }

        Response (preview_only=false):
        {
            "deleted": 100,
            "failed": 0,
            "preview": false
        }
        """
        try:
            data = request.json or {}
            deep_path = data.get('deep_path')
            preview_only = data.get('preview_only', True)

            if not deep_path:
                return {"error": "deep_path is required"}, 400

            # Normalize path - support both absolute and relative paths
            if os.path.isabs(deep_path):
                # Absolute path - use directly
                normalized_path = os.path.abspath(deep_path)
                print(f"[Batch Delete] Using absolute path: {normalized_path}")
            else:
                # Relative path - try to match against folder_paths
                print(f"[Batch Delete] Resolving relative path: {deep_path}")
                folder_paths = settings_manager.get_settings().get('folder_paths', [])

                matched_paths = []
                for folder in folder_paths:
                    folder_abs = os.path.abspath(folder)
                    # Check if this folder path ends with the relative path
                    if folder_abs.endswith(os.sep + deep_path) or folder_abs.endswith(deep_path):
                        matched_paths.append(folder_abs)
                        print(f"[Batch Delete] Found match: {folder_abs}")

                if not matched_paths:
                    # No match in folder_paths, try as relative to current working directory
                    normalized_path = os.path.abspath(deep_path)
                    print(f"[Batch Delete] No match in folder_paths, using cwd-relative: {normalized_path}")
                elif len(matched_paths) == 1:
                    # Exactly one match
                    normalized_path = matched_paths[0]
                    print(f"[Batch Delete] Resolved to: {normalized_path}")
                else:
                    # Multiple matches - return error
                    return {
                        "error": f"Ambiguous path '{deep_path}' matches multiple folders: {matched_paths}"
                    }, 400

            deep_path = normalized_path

            print(f"[Batch Delete] Scanning for files under: {deep_path}")
            print(f"[Batch Delete] Preview only: {preview_only}")

            # Get workflow and database connection
            workflow = get_workflow()
            conn = workflow._get_connection()
            cursor = conn.cursor()

            # Query all duplicate files under the specified path
            # A file is a duplicate if it appears in the similarities table
            # IMPORTANT: Use exact path match to avoid matching similar paths
            # e.g., /a/b/c should NOT match /a/b/c-1 or /a/b/c_backup
            cursor.execute('''
                SELECT DISTINCT i.file_path
                FROM image_hashes i
                WHERE (i.file_path = ? OR i.file_path LIKE ?)
                AND EXISTS (
                    SELECT 1 FROM phash_similarities s
                    WHERE s.image_id_a = i.id OR s.image_id_b = i.id
                )
            ''', (deep_path, f"{deep_path}{os.sep}%"))

            matched_files = [row[0] for row in cursor.fetchall()]

            print(f"[Batch Delete] Found {len(matched_files)} files under {deep_path}")

            if preview_only:
                # Preview mode: just return the list
                return {
                    "matched_files": len(matched_files),
                    "file_list": matched_files,
                    "preview": True
                }
            else:
                # Actual deletion mode
                delete_target_path = settings_manager.get_delete_target_path()

                if not delete_target_path:
                    return {"error": "delete_target_path not configured"}, 400

                # Get folder_paths (scan folders) - use them directly as root
                folder_paths = settings_manager.get_settings().get('folder_paths', [])

                # === Step 5: pre-capture state for incremental group_stats repair ===
                try:
                    ids_to_delete: list = []
                    BATCH = 900
                    for i in range(0, len(matched_files), BATCH):
                        chunk = [os.path.abspath(f) for f in matched_files[i:i + BATCH]]
                        ph = ','.join('?' * len(chunk))
                        cursor.execute(f"SELECT id FROM image_hashes WHERE file_path IN ({ph})", chunk)
                        ids_to_delete.extend(r[0] for r in cursor.fetchall())
                    affected_capture = workflow.stats_collect_affected_before_mutation(ids_to_delete)
                    print(f"[Batch Delete] Pre-captured stats repair state for {len(ids_to_delete)} image_ids")
                except Exception as e:
                    print(f"[Batch Delete] WARNING: stats pre-capture failed: {e}")
                    affected_capture = None

                deleted_count = 0
                failed_count = 0

                print(f"[Batch Delete] Delete target: {delete_target_path}")
                print(f"[Batch Delete] Scan folders configured: {len(folder_paths)} folders")

                for file_path in matched_files:
                    try:
                        if not os.path.exists(file_path):
                            print(f"[Batch Delete] File not found, skipping: {file_path}")
                            failed_count += 1
                            continue

                        abs_file_path = os.path.abspath(file_path)

                        # Find the scan folder that contains this file (use it as root)
                        scan_folder = None
                        for folder in folder_paths:
                            folder_abs = os.path.abspath(folder)
                            if abs_file_path.startswith(folder_abs + os.sep) or abs_file_path == folder_abs:
                                scan_folder = folder_abs
                                break

                        if not scan_folder:
                            # Fallback: if no scan folder found, use the file's parent directory
                            scan_folder = os.path.dirname(abs_file_path)
                            print(f"[Batch Delete] Warning: No scan folder found for {abs_file_path}, using parent directory")

                        # Calculate relative path from scan folder
                        try:
                            relative_path = os.path.relpath(abs_file_path, scan_folder)
                        except ValueError:
                            # Different drives on Windows, fallback to filename only
                            relative_path = os.path.basename(abs_file_path)
                            print(f"[Batch Delete] Warning: Cannot calculate relative path (different drives?), using filename only")

                        # Construct target path
                        target_file = os.path.join(delete_target_path, relative_path)
                        target_dir = os.path.dirname(target_file)

                        # Create target directory
                        os.makedirs(target_dir, exist_ok=True)

                        # Move file
                        shutil.move(file_path, target_file)
                        print(f"[Batch Delete] ✓ Moved: {file_path}")
                        print(f"[Batch Delete]   Scan folder: {scan_folder}")
                        print(f"[Batch Delete]   Relative: {relative_path}")
                        print(f"[Batch Delete]   Destination: {target_file}")

                        # Delete from database (image_hashes and phash_similarities)
                        try:
                            # Find the image ID
                            cursor.execute('SELECT id FROM image_hashes WHERE file_path = ?', (abs_file_path,))
                            row = cursor.fetchone()

                            if row:
                                image_id = row[0]
                                # Delete from phash_similarities (where this image is involved)
                                cursor.execute('DELETE FROM phash_similarities WHERE image_id_a = ? OR image_id_b = ?',
                                             (image_id, image_id))
                                similarity_count = cursor.rowcount

                                # Delete from image_hashes
                                cursor.execute('DELETE FROM image_hashes WHERE id = ?', (image_id,))
                                conn.commit()

                                print(f"[Batch Delete]   DB cleaned: removed image record (ID={image_id}) and {similarity_count} similarity records")
                            else:
                                print(f"[Batch Delete]   DB: image not found in database")

                        except Exception as db_error:
                            print(f"[Batch Delete] Warning: Failed to clean database for {file_path}: {db_error}")
                            # Don't fail the whole operation if DB cleanup fails

                        deleted_count += 1
                    except Exception as e:
                        print(f"[Batch Delete] ✗ Failed to delete {file_path}: {e}")
                        failed_count += 1

                print(f"[Batch Delete] Complete: {deleted_count} deleted, {failed_count} failed")

                # Clean up empty directories under deep_path
                if deleted_count > 0:
                    print(f"[Batch Delete] Cleaning up empty directories...")
                    try:
                        empty_dirs_removed = 0
                        # Walk through the deep_path directory tree from bottom to top
                        for root, dirs, files in os.walk(deep_path, topdown=False):
                            # Check if directory is empty (no files and no subdirectories)
                            try:
                                if not os.listdir(root):
                                    os.rmdir(root)
                                    empty_dirs_removed += 1
                                    print(f"[Batch Delete]   Removed empty directory: {root}")
                            except OSError as e:
                                # Directory might not be empty or no permission
                                print(f"[Batch Delete]   Could not remove directory {root}: {e}")
                                continue

                        # Try to remove the deep_path itself if it's now empty
                        try:
                            if os.path.exists(deep_path) and not os.listdir(deep_path):
                                os.rmdir(deep_path)
                                empty_dirs_removed += 1
                                print(f"[Batch Delete]   Removed empty root directory: {deep_path}")
                        except OSError as e:
                            print(f"[Batch Delete]   Could not remove root directory {deep_path}: {e}")

                        if empty_dirs_removed > 0:
                            print(f"[Batch Delete] Cleaned up {empty_dirs_removed} empty directories")
                        else:
                            print(f"[Batch Delete] No empty directories to clean up")

                    except Exception as cleanup_error:
                        print(f"[Batch Delete] Warning: Failed to clean up empty directories: {cleanup_error}")
                        # Don't fail the operation if cleanup fails

                return {
                    "deleted": deleted_count,
                    "failed": failed_count,
                    "preview": False,
                    "stats_repair": (
                        workflow.stats_repair_after_mutation(affected_capture, remove_from_groups=False)
                        if affected_capture else None
                    ),
                }

        except Exception as e:
            error_msg = str(e)
            print(f"[Batch Delete] Error: {error_msg}")
            import traceback
            traceback.print_exc()
            return {"error": error_msg}, 500


# ========== Cypress Test Support Endpoints ==========

@ns.route("/cypress/test-data/duplicate-groups")
class CypressGenerateDuplicateGroupsResource(Resource):
    def post(self):
        """
        Generate duplicate groups for testing

        Request body:
        {
            "base_path": "/path/to/test/dir",
            "group_count": 10,
            "files_per_group": 2
        }
        """
        from .cypress_test_support import TestImageGenerator
        import os

        data = request.json
        base_path = data.get('base_path')
        group_count = data.get('group_count', 1)
        files_per_group = data.get('files_per_group', 2)

        if not base_path:
            return {'error': 'base_path required'}, 400

        try:
            os.makedirs(base_path, exist_ok=True)
            gen = TestImageGenerator()
            total_created = 0

            for i in range(1, group_count + 1):
                # Create folders for each file in the group
                folder_paths = []
                for j in range(files_per_group):
                    folder = f'{base_path}/group{i}_folder{j + 1}'
                    os.makedirs(folder, exist_ok=True)
                    folder_paths.append(f'{folder}/img{i}.png')

                # Generate master image
                master_file = folder_paths[0]
                gen.generate_labeled_image(
                    master_file,
                    group_label=f'Group {i}',
                    file_label=f'img{i}.png',
                    width=300,
                    height=200
                )
                total_created += 1

                # Copy to other folders
                for j in range(1, files_per_group):
                    shutil.copy(master_file, folder_paths[j])
                    total_created += 1

            return {
                'success': True,
                'total_created': total_created,
                'group_count': group_count,
                'files_per_group': files_per_group
            }
        except Exception as e:
            import traceback
            print(f"[Cypress] Error generating duplicate groups: {e}")
            print(traceback.format_exc())
            return {'error': str(e)}, 500


@ns.route("/cypress/test-data/identical-images")
class CypressGenerateIdenticalImagesResource(Resource):
    def post(self):
        """
        Generate identical images at multiple paths

        Request body:
        {
            "paths": ["/path/1.png", "/path/2.png"],
            "label": "Test Group"
        }
        """
        from .cypress_test_support import TestImageGenerator
        import os

        data = request.json
        paths = data.get('paths', [])
        label = data.get('label', 'Test')

        if not paths or len(paths) < 2:
            return {'error': 'At least 2 paths required'}, 400

        try:
            gen = TestImageGenerator()

            # Generate master image
            master_file = paths[0]
            os.makedirs(os.path.dirname(master_file), exist_ok=True)
            gen.generate_labeled_image(
                master_file,
                group_label=label,
                file_label=os.path.basename(master_file),
                width=300,
                height=200
            )

            # Copy to other paths
            for path in paths[1:]:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                shutil.copy(master_file, path)

            return {
                'success': True,
                'created_count': len(paths),
                'paths': paths
            }
        except Exception as e:
            import traceback
            print(f"[Cypress] Error generating identical images: {e}")
            print(traceback.format_exc())
            return {'error': str(e)}, 500


@ns.route("/cypress/test-data/unique-image")
class CypressGenerateUniqueImageResource(Resource):
    def post(self):
        """
        Generate a unique random image

        Request body:
        {
            "file_path": "/path/to/image.png"
        }
        """
        from .cypress_test_support import TestImageGenerator
        import os
        import random

        data = request.json
        file_path = data.get('file_path')

        if not file_path:
            return {'error': 'file_path required'}, 400

        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            gen = TestImageGenerator()
            seed = random.randint(1, 1000000)
            gen.generate_random_image(file_path, width=300, height=200, seed=seed)

            return {
                'success': True,
                'file_path': file_path
            }
        except Exception as e:
            import traceback
            print(f"[Cypress] Error generating unique image: {e}")
            print(traceback.format_exc())
            return {'error': str(e)}, 500


@ns.route("/cypress/duplicate-finder/setup")
class CypressTestSetupResource(Resource):
    def post(self):
        """
        Setup test data for Cypress tests

        Request body:
        {
            "test_type": "minimal" | "performance",
            "base_dir": "/path/to/test/dir",
            "count": 50  // Optional, only for performance type
        }
        """
        data = request.json
        test_type = data.get('test_type', 'minimal')
        base_dir = data.get('base_dir')

        if not base_dir:
            return {'error': 'base_dir required'}, 400

        try:
            if test_type == 'minimal':
                result = TestDataSetup.create_minimal_test_set(base_dir)
            elif test_type == 'performance':
                count = data.get('count', 50)
                result = TestDataSetup.create_performance_test_set(base_dir, count)
            else:
                return {'error': f'Unknown test_type: {test_type}'}, 400

            return {
                'success': True,
                'test_dir': base_dir,
                'result': result
            }
        except Exception as e:
            import traceback
            print(f"[Cypress Setup] Error: {e}")
            print(traceback.format_exc())
            return {'error': str(e)}, 500


@ns.route("/cypress/clear-db")
class CypressClearDbResource(Resource):
    def post(self):
        """Clear all data from duplicate finder database (for testing only)"""
        try:
            # PHashCache will automatically use configured DB path from settings
            cache = PHashCache()
            conn = cache._get_connection()
            cursor = conn.cursor()

            # Clear all tables
            cursor.execute("DELETE FROM phash_similarities")
            cursor.execute("DELETE FROM whitelist")
            cursor.execute("DELETE FROM image_hashes")
            conn.commit()

            print(f"[Cypress] Cleared all data from duplicate finder database: {cache.db_path}")

            return {
                "success": True,
                "message": f"Database cleared: {cache.db_path}"
            }
        except Exception as e:
            print(f"[Cypress] Error clearing database: {str(e)}")
            return {"error": str(e)}, 500


@ns.route("/cypress/duplicate-finder/cleanup")
class CypressTestCleanupResource(Resource):
    def post(self):
        """
        Cleanup test data

        Request body:
        {
            "base_dir": "/path/to/test/dir"
        }
        """
        data = request.json
        base_dir = data.get('base_dir')

        if not base_dir:
            return {'error': 'base_dir required'}, 400

        try:
            TestDataSetup.cleanup_test_data(base_dir)
            return {'success': True}
        except Exception as e:
            import traceback
            print(f"[Cypress Cleanup] Error: {e}")
            print(traceback.format_exc())
            return {'error': str(e)}, 500


