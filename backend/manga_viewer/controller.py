from flask_restx import Namespace, Resource
from flask import request, jsonify, send_file, make_response
import os
import config
import shutil
from extensions import restx_api
from manga_viewer.repository import Repository
from urllib.parse import unquote

api = Namespace("")

@api.route("/manga-viewer/index")
class MangaIndexResource(Resource):
    def get(self):
        Repository.load_index()
        index_dict = Repository.manga_index.to_dict()
        for folder_id, folder_data in index_dict.get("folders", {}).items():
            folder_data["file_list"] = []
        return jsonify(index_dict)


@api.route("/manga-viewer/files-url-list")
class FolderScanResource(Resource):
    def get(self):
        folder_id = request.args.get("folderId", "").strip()
        if folder_id not in Repository.manga_index.folders:
            return jsonify([])

        file_url_list = Repository.manga_index.folders[folder_id].file_list
        return jsonify(file_url_list)


@api.route("/manga-viewer/file/<path:filepath>")
class FileResource(Resource):
    def get(self, filepath):
        root_abs = os.path.abspath(config.MANGA_VIEWER_ROOT_PATH)
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

@api.route("/manga-viewer/folders/<path:classifier_mode>")
class FolderUpdateResource(Resource):
    def put(self, classifier_mode: bool=True):
        folder_models = request.json or {}
        if not isinstance(folder_models, dict):
            return jsonify({"error": "invalid payload"}), 400

        main_map = {"bou": "boutique", "arch": "archive"}
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
                    delete_root = config.MANGA_VIEWER_DELETE_PATHS
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
                    base_root = config.MANGA_VIEWER_CATEGORY_PATHS
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
                    if classifier_mode:
                        del Repository.manga_index.folders[folder_id]

        rebuildMeta()
        Repository.save_index()
        return '', 204


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


restx_api.add_namespace(api)
