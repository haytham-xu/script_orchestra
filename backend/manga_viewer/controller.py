from flask_restx import Namespace, Resource
from flask import request, jsonify, send_file, make_response
import os
import shutil
import random
from extensions import restx_api
from manga_viewer.repository import Repository
from manga_viewer.settings_manager import settings_manager
from urllib.parse import unquote
from natsort import natsorted
import uuid

api = Namespace("")

@api.route("/manga-viewer/index")
class MangaIndexResource(Resource):
    def get(self):
        Repository.load_index()
        index_dict = Repository.manga_index.to_dict()
        for folder_id, folder_data in index_dict.get("folders", {}).items():
            folder_data["file_list"] = []
        return index_dict


@api.route("/manga-viewer/files-url-list")
class FolderScanResource(Resource):
    def get(self):
        folder_id = request.args.get("folderId", "").strip()
        if folder_id not in Repository.manga_index.folders:
            return []

        file_url_list = Repository.manga_index.folders[folder_id].file_list
        return file_url_list


@api.route("/manga-viewer/file/<path:filepath>")
class FileResource(Resource):
    def get(self, filepath):
        root_abs = os.path.abspath(Repository.get_root_path())
        rel_url_path = unquote(filepath).lstrip("/\\")
        first_seg = rel_url_path.split("/")[0]
        if os.path.isabs(rel_url_path) or (":" in first_seg):
            return "Forbidden", 403
        safe_path = os.path.normpath(os.path.join(root_abs, rel_url_path.replace("/", os.sep)))
        root_with_sep = root_abs + os.sep
        if not (safe_path == root_abs or safe_path.startswith(root_with_sep)):
            return "Forbidden", 403
        if not os.path.isfile(safe_path):
            return "Not Found", 404
        return make_response(send_file(safe_path))

@api.route("/manga-viewer/index/random")
class MangaIndexRandomResource(Resource):
    def get(self):
        """Get random folders from manga index."""
        # Get count from settings, allow query param to override
        default_count = settings_manager.get_setting('random.count', 10)
        count = request.args.get('count', default=default_count, type=int)

        Repository.load_index()
        all_folders = list(Repository.manga_index.folders.values())

        # Limit count to available folders
        count = min(count, len(all_folders))

        # Randomly select folders
        random_folders = random.sample(all_folders, count) if count > 0 else []

        # Convert to dict
        folders_dict = {f.id: f.to_dict() for f in random_folders}
        for folder_data in folders_dict.values():
            folder_data["file_list"] = []

        result = {
            "folders": folders_dict,
            "metadata": Repository.manga_index.metadata.to_dict() if Repository.manga_index.metadata else {}
        }
        return result


@api.route("/manga-viewer/folders/<path:classifier_mode>")
class FolderUpdateResource(Resource):
    def put(self, classifier_mode: bool=True):
        folder_models = request.json or {}
        if not isinstance(folder_models, dict):
            return {"error": "invalid payload"}, 400

        # Get category folder mapping from settings
        main_map = settings_manager.get_setting('category_folder_mapping', {})
        invalid_chars = set('<>:"/\\|?*')

        for folder_id, incoming in folder_models.items():
            old_folder = Repository.manga_index.folders.get(folder_id)
            if not old_folder:
                continue

            new_tags = (incoming.get("tags") or {})
            new_name = (incoming.get("name") or old_folder.name or "").strip()

            if any(ch in invalid_chars for ch in new_name):
                new_name = old_folder.name

            if new_name and os.path.normcase(new_name) != os.path.normcase(old_folder.name):
                old_path = old_folder.path
                parent_dir = os.path.dirname(old_path)
                target_path = os.path.join(parent_dir, new_name)
                if not (target_path and os.path.exists(target_path)):
                    try:
                        os.rename(old_path, target_path)
                        old_folder.name = new_name
                        old_folder.path = target_path
                        old_folder.file_list = Repository.get_files_url_list(old_folder.path)
                        old_folder.initialized = True
                    except OSError:
                        pass

            def non_empty(v):
                if v is None: return False
                if isinstance(v, (list, tuple, set, dict)): return len(v) > 0
                if isinstance(v, str): return v.strip() != ""
                return True

            changed_other = False
            for k in ["auth", "name", "custom", "others", "mosaic"]:
                if k in new_tags and non_empty(new_tags[k]):
                    setattr(old_folder.tags, k, new_tags[k])
                    changed_other = True
            if changed_other:
                old_folder.initialized = True

            cat_main_new = new_tags.get("category_main", old_folder.tags.category_main)
            cat_sub_new = new_tags.get("category_sub", old_folder.tags.category_sub)

            cat_main_changed = cat_main_new and cat_main_new != old_folder.tags.category_main
            cat_sub_changed = cat_sub_new and cat_sub_new != old_folder.tags.category_sub

            if cat_main_changed or cat_sub_changed:
                if cat_main_new == "del":
                    delete_root = settings_manager.get_setting('paths.delete_paths', '')
                    if delete_root:
                        delete_root_abs = os.path.abspath(delete_root)
                        os.makedirs(delete_root_abs, exist_ok=True)
                        try:
                            dst = os.path.join(delete_root_abs, os.path.basename(old_folder.path))
                            if not os.path.exists(dst):
                                shutil.move(old_folder.path, dst)
                        except OSError:
                            pass
                    if folder_id in Repository.manga_index.folders:
                        del Repository.manga_index.folders[folder_id]
                    continue
                else:
                    base_root = settings_manager.get_setting('paths.category_paths', '')
                    if base_root:
                        base_root_abs = os.path.abspath(base_root)
                        main_folder_name = main_map.get(cat_main_new, cat_main_new)
                        main_folder_path = os.path.join(base_root_abs, main_folder_name)
                        sub_folder_name = f"{cat_main_new}_{cat_sub_new}" if cat_sub_new else cat_main_new
                        target_sub_path = os.path.join(main_folder_path, sub_folder_name)
                        os.makedirs(target_sub_path, exist_ok=True)
                        new_abs_path = os.path.join(target_sub_path, os.path.basename(old_folder.path))
                        if os.path.normcase(os.path.abspath(old_folder.path)) != os.path.normcase(os.path.abspath(new_abs_path)):
                            try:
                                if not os.path.exists(new_abs_path):
                                    shutil.move(old_folder.path, new_abs_path)
                                    old_folder.path = new_abs_path
                                    old_folder.file_list = Repository.get_files_url_list(old_folder.path)
                                    old_folder.initialized = True
                            except OSError:
                                pass
                    old_folder.tags.category_main = cat_main_new
                    old_folder.tags.category_sub = cat_sub_new
                    # Don't delete from index - just update the path and tags
                    # The folder should remain in the index with the same ID

        rebuildMeta()
        Repository.save_index()
        return '', 204


@api.route("/manga-viewer/delete")
class FolderDeleteResource(Resource):
    def post(self):
        """Move folders to delete_paths (soft delete)"""
        data = request.json or {}
        folder_ids = data.get('folderIds', [])

        if not isinstance(folder_ids, list):
            return {"error": "folderIds must be a list"}, 400

        # Get delete path from settings
        delete_root = settings_manager.get_setting('paths.delete_paths', '')
        if not delete_root:
            return {"error": "delete_paths not configured in settings"}, 400

        delete_root_abs = os.path.abspath(delete_root)
        os.makedirs(delete_root_abs, exist_ok=True)

        moved_count = 0
        errors = []

        for folder_id in folder_ids:
            folder = Repository.manga_index.folders.get(folder_id)
            if not folder:
                errors.append(f"Folder {folder_id} not found")
                continue

            folder_path = folder.path

            # Move to delete_paths (soft delete)
            if os.path.exists(folder_path):
                try:
                    dst = os.path.join(delete_root_abs, os.path.basename(folder_path))

                    # Handle name collision - add suffix
                    if os.path.exists(dst):
                        base_name = os.path.basename(folder_path)
                        counter = 1
                        while os.path.exists(dst):
                            name_parts = os.path.splitext(base_name)
                            if name_parts[1]:  # has extension
                                new_name = f"{name_parts[0]}_deleted_{counter}{name_parts[1]}"
                            else:
                                new_name = f"{base_name}_deleted_{counter}"
                            dst = os.path.join(delete_root_abs, new_name)
                            counter += 1

                    shutil.move(folder_path, dst)
                    moved_count += 1
                except Exception as e:
                    errors.append(f"Failed to move {folder_path}: {str(e)}")
                    continue

            # Remove from index
            if folder_id in Repository.manga_index.folders:
                del Repository.manga_index.folders[folder_id]

        # Rebuild metadata and save
        if moved_count > 0:
            rebuildMeta()
            Repository.save_index()

        if errors:
            return {
                "moved": moved_count,
                "errors": errors
            }, 207  # Multi-status

        return {
            "moved": moved_count,
            "message": f"Successfully moved {moved_count} folder(s) to delete_paths"
        }, 200


def rebuildMeta():
    auth_set, cat_main_set, cat_sub_set = set(), set(), set()
    for f in Repository.manga_index.folders.values():
        for a_auth in f.tags.auth:
            auth_set.add(a_auth)
        if f.tags.category_main:
            cat_main_set.add(f.tags.category_main)
        if f.tags.category_sub:
            cat_sub_set.add(f.tags.category_sub)
    Repository.manga_index.metadata.auth = sorted(auth_set)
    Repository.manga_index.metadata.category_main = sorted(cat_main_set)
    Repository.manga_index.metadata.category_sub = sorted(cat_sub_set)


@api.route("/manga-viewer/open-folder")
class OpenFolderResource(Resource):
    def post(self):
        """Open folder in system file manager"""
        import subprocess
        import platform

        data = request.json or {}
        folder_id = data.get('folderId', '')
        folder_path = data.get('folderPath', '')

        # Support both folderId (from index) and direct folderPath
        if folder_id:
            folder = Repository.manga_index.folders.get(folder_id)
            if not folder:
                return {"error": f"Folder {folder_id} not found"}, 404
            folder_path = folder.path
        elif not folder_path:
            return {"error": "Either folderId or folderPath is required"}, 400

        if not os.path.exists(folder_path):
            return {"error": f"Folder path does not exist: {folder_path}"}, 404

        try:
            system = platform.system()
            if system == 'Darwin':
                subprocess.Popen(['open', folder_path])
            elif system == 'Windows':
                # Windows: use os.startfile for better path handling, or explorer with proper quoting
                try:
                    os.startfile(folder_path)
                except AttributeError:
                    # os.startfile only exists on Windows, fallback to subprocess
                    subprocess.Popen(['explorer', os.path.normpath(folder_path)])
            elif system == 'Linux':
                subprocess.Popen(['xdg-open', folder_path])
            else:
                return {"error": f"Unsupported operating system: {system}"}, 400

            return {"message": "Folder opened successfully"}, 200
        except Exception as e:
            return {"error": f"Failed to open folder: {str(e)}"}, 500


@api.route("/manga-viewer/refresh-index")
class RefreshIndexResource(Resource):
    def post(self):
        """Refresh manga index by scanning folders"""
        try:
            Repository.refresh_index()
            return {"message": "Index refreshed successfully"}, 200
        except Exception as e:
            return {"error": f"Failed to refresh index: {str(e)}"}, 500


@api.route("/manga-viewer/import/scan")
class ImportScanResource(Resource):
    def post(self):
        """Scan a path for manga folders to import"""
        data = request.json or {}
        scan_path = data.get('path', '')

        if not scan_path:
            return {"error": "path is required"}, 400

        scan_path_abs = os.path.abspath(scan_path)

        if not os.path.exists(scan_path_abs):
            return {"error": f"Path does not exist: {scan_path}"}, 404

        if not os.path.isdir(scan_path_abs):
            return {"error": f"Path is not a directory: {scan_path}"}, 400

        try:
            # Load cache
            cache_file = os.path.join(scan_path_abs, 'import_cache.json')
            cache = {}
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cache = json.load(f)
                except Exception as e:
                    print(f"Failed to load cache: {e}")
                    cache = {}

            # Get all subdirectories (one level only)
            entries = os.listdir(scan_path_abs)
            folders = []
            updated_cache = {}

            for entry in entries:
                entry_path = os.path.join(scan_path_abs, entry)
                if os.path.isdir(entry_path):
                    # Calculate folder size first
                    folder_size = 0
                    for root, _, files in os.walk(entry_path):
                        for file in files:
                            try:
                                folder_size += os.path.getsize(os.path.join(root, file))
                            except:
                                pass

                    # Create cache key: folder_name + size
                    cache_key = f"{entry}_{folder_size}"

                    # Check if cache exists and is valid
                    cached_data = cache.get(cache_key)

                    # Get all image files recursively
                    image_files = []
                    for root, _, files in os.walk(entry_path):
                        for file in files:
                            ext = os.path.splitext(file)[1].lower()
                            if ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.pdf']:
                                file_path = os.path.join(root, file)
                                # Convert to relative URL path
                                rel_path = os.path.relpath(file_path, Repository.get_root_path())
                                url_path = '/' + rel_path.replace(os.sep, '/')
                                image_files.append(url_path)

                    # Natural sort the files
                    image_files = natsorted(image_files)

                    folder_data = {
                        'id': str(uuid.uuid4()),
                        'name': entry,
                        'path': entry_path,
                        'files': image_files,
                        'size': folder_size,
                        'number': len(image_files)
                    }

                    # If cache exists, use cached tags
                    if cached_data:
                        folder_data['auth'] = cached_data.get('auth', [])
                        folder_data['name_tags'] = cached_data.get('name_tags', [])
                        folder_data['custom'] = cached_data.get('custom', [])
                        folder_data['others'] = cached_data.get('others', [])
                        folder_data['category_main'] = cached_data.get('category_main', '')
                        folder_data['category_sub'] = cached_data.get('category_sub', '')
                        folder_data['mosaic'] = cached_data.get('mosaic', '')
                    else:
                        folder_data['auth'] = []
                        folder_data['name_tags'] = []
                        folder_data['custom'] = []
                        folder_data['others'] = []
                        folder_data['category_main'] = ''
                        folder_data['category_sub'] = ''
                        folder_data['mosaic'] = ''

                    folders.append(folder_data)

                    # Update cache (keep tags data)
                    updated_cache[cache_key] = {
                        'auth': folder_data.get('auth', []),
                        'name_tags': folder_data.get('name_tags', []),
                        'custom': folder_data.get('custom', []),
                        'others': folder_data.get('others', []),
                        'category_main': folder_data.get('category_main', ''),
                        'category_sub': folder_data.get('category_sub', ''),
                        'mosaic': folder_data.get('mosaic', '')
                    }

            # Sort folders by name
            folders = natsorted(folders, key=lambda x: x['name'])

            # Save updated cache
            try:
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(updated_cache, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"Failed to save cache: {e}")

            return {
                'folders': folders,
                'count': len(folders)
            }, 200

        except Exception as e:
            return {"error": f"Failed to scan path: {str(e)}"}, 500


@api.route("/manga-viewer/import/move")
class ImportMoveResource(Resource):
    def post(self):
        """Move/import a folder to manga viewer managed directory"""
        data = request.json or {}
        source_path = data.get('sourcePath', '')
        folder_data = data.get('folderData', {})

        if not source_path:
            return {"error": "sourcePath is required"}, 400

        if not os.path.exists(source_path):
            return {"error": f"Source path does not exist: {source_path}"}, 404

        # Get target path from settings
        category_paths = settings_manager.get_setting('paths.category_paths', '')
        if not category_paths:
            # Fallback to root_path
            category_paths = settings_manager.get_setting('paths.root_path', '')

        if not category_paths:
            return {"error": "category_paths not configured in settings"}, 400

        category_paths_abs = os.path.abspath(category_paths)

        # Get category info
        category_main = folder_data.get('category_main', '')
        category_sub = folder_data.get('category_sub', '')
        new_name = folder_data.get('name', os.path.basename(source_path))

        if not category_main or not category_sub:
            return {"error": "category_main and category_sub are required"}, 400

        # Build target path - get category folder mapping from settings
        main_map = settings_manager.get_setting('category_folder_mapping', {})
        main_folder_name = main_map.get(category_main, category_main)
        main_folder_path = os.path.join(category_paths_abs, main_folder_name)
        sub_folder_name = f"{category_main}_{category_sub}"
        target_sub_path = os.path.join(main_folder_path, sub_folder_name)
        os.makedirs(target_sub_path, exist_ok=True)

        target_path = os.path.join(target_sub_path, new_name)

        # Handle name collision
        original_target = target_path
        if os.path.exists(target_path):
            base_name = new_name
            counter = 1
            while os.path.exists(target_path):
                new_name_with_suffix = f"{base_name}_{counter}"
                target_path = os.path.join(target_sub_path, new_name_with_suffix)
                counter += 1
            new_name = new_name_with_suffix

        try:
            # Log import operation (backend)
            print(f"\n{'='*80}")
            print(f"📦 [Import] Starting import operation")
            print(f"{'='*80}")
            print(f"  Folder Name: {os.path.basename(source_path)}")
            print(f"  From Path:   {source_path}")
            print(f"  To Path:     {target_path}")
            print(f"  Category:    {category_main}_{category_sub}")
            print(f"  Size:        {folder_data.get('size', 0) / 1024 / 1024:.2f} MB")
            print(f"  Files:       {folder_data.get('number', 0)}")
            print(f"  Tags:")
            print(f"    - Auth:    {folder_data.get('auth', [])}")
            print(f"    - Name:    {folder_data.get('name_tags', [])}")
            print(f"    - Custom:  {folder_data.get('custom', [])}")
            print(f"    - Mosaic:  {folder_data.get('mosaic', '')}")
            if original_target != target_path:
                print(f"  ⚠️  Name collision detected, renamed to: {new_name}")

            # Update cache before moving (so we can find import_cache.json in source dir)
            import_path = os.path.dirname(source_path)
            cache_file = os.path.join(import_path, 'import_cache.json')

            # Calculate folder size for cache key
            folder_size = folder_data.get('size', 0)
            folder_name = os.path.basename(source_path)
            cache_key = f"{folder_name}_{folder_size}"

            # Update cache with user's tags
            try:
                cache = {}
                if os.path.exists(cache_file):
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cache = json.load(f)

                cache[cache_key] = {
                    'auth': folder_data.get('auth', []),
                    'name_tags': folder_data.get('name_tags', []),
                    'custom': folder_data.get('custom', []),
                    'others': folder_data.get('others', []),
                    'category_main': category_main,
                    'category_sub': category_sub,
                    'mosaic': folder_data.get('mosaic', '')
                }

                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(cache, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"  ⚠️  Failed to update cache: {e}")

            # Move folder
            shutil.move(source_path, target_path)
            print(f"  ✅ Folder moved successfully")

            # Create folder entry in index
            folder_id = str(uuid.uuid4())
            from manga_viewer.model.folder import Folder
            from manga_viewer.model.tag import Tag

            # Get file list for the newly moved folder
            file_list = Repository.get_files_url_list(target_path)

            new_folder = Folder(
                id_=folder_id,
                name=new_name,
                path=target_path,
                size=folder_data.get('size', 0),
                number=folder_data.get('number', 0),
                initialized=True,
                tags=Tag(
                    auth=folder_data.get('auth', []),
                    name=folder_data.get('name_tags', []),
                    custom=folder_data.get('custom', []),
                    others=folder_data.get('others', []),
                    category_main=category_main,
                    category_sub=category_sub,
                    mosaic=folder_data.get('mosaic', '')
                ),
                file_list=file_list
            )

            Repository.manga_index.folders[folder_id] = new_folder

            # Rebuild metadata and save
            rebuildMeta()
            Repository.save_index()

            print(f"  ✅ Index updated, folder ID: {folder_id}")
            print(f"{'='*80}\n")

            return {
                "message": "Folder imported successfully",
                "folderId": folder_id,
                "targetPath": target_path
            }, 200

        except Exception as e:
            print(f"  ❌ Import failed: {str(e)}")
            print(f"{'='*80}\n")
            return {"error": f"Failed to import folder: {str(e)}"}, 500


@api.route("/manga-viewer/import/delete")
class ImportDeleteResource(Resource):
    def post(self):
        """Move a folder to delete_paths (soft delete)"""
        data = request.json or {}
        source_path = data.get('sourcePath', '')

        if not source_path:
            return {"error": "sourcePath is required"}, 400

        if not os.path.exists(source_path):
            return {"error": f"Source path does not exist: {source_path}"}, 404

        if not os.path.isdir(source_path):
            return {"error": f"Source path is not a directory: {source_path}"}, 400

        # Get delete path from settings
        delete_root = settings_manager.get_setting('paths.delete_paths', '')
        if not delete_root:
            return {"error": "delete_paths not configured in settings"}, 400

        delete_root_abs = os.path.abspath(delete_root)
        os.makedirs(delete_root_abs, exist_ok=True)

        try:
            # Log delete operation (backend)
            print(f"\n{'='*80}")
            print(f"🗑️  [Delete] Starting soft delete operation")
            print(f"{'='*80}")
            print(f"  Folder Name: {os.path.basename(source_path)}")
            print(f"  From Path:   {source_path}")

            # Calculate folder info for logging
            folder_size = 0
            file_count = 0
            for root, _, files in os.walk(source_path):
                for file in files:
                    try:
                        folder_size += os.path.getsize(os.path.join(root, file))
                        file_count += 1
                    except:
                        pass

            print(f"  Size:        {folder_size / 1024 / 1024:.2f} MB")
            print(f"  Files:       {file_count}")

            # Move to delete_paths (handle name collision)
            dst = os.path.join(delete_root_abs, os.path.basename(source_path))

            if os.path.exists(dst):
                base_name = os.path.basename(source_path)
                counter = 1
                while os.path.exists(dst):
                    new_name = f"{base_name}_deleted_{counter}"
                    dst = os.path.join(delete_root_abs, new_name)
                    counter += 1
                print(f"  ⚠️  Name collision, renamed to: {os.path.basename(dst)}")

            # Move the folder
            shutil.move(source_path, dst)

            print(f"  To Path:     {dst}")
            print(f"  ✅ Folder moved to delete_paths successfully")
            print(f"{'='*80}\n")

            return {
                "message": "Folder moved to delete_paths successfully",
                "deletePath": dst
            }, 200

        except Exception as e:
            print(f"  ❌ Delete failed: {str(e)}")
            print(f"{'='*80}\n")
            return {"error": f"Failed to delete folder: {str(e)}"}, 500

        except Exception as e:
            return {"error": f"Failed to import folder: {str(e)}"}, 500


restx_api.add_namespace(api)
