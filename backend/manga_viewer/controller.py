from flask_restx import Namespace, Resource
from flask import request, jsonify, send_file, make_response
import os
import config
from extensions import restx_api
from manga_viewer.repository import Repository
from urllib.parse import quote, unquote

api = Namespace("")


@api.route("/manga-viewer/hot-tags")
class HotTagsResource(Resource):
    def get(self):
        return jsonify(config.MANGA_VIEWER_HOT_TAGS)


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
        print(file_url_list)
        return jsonify(file_url_list)

@api.route("/manga-viewer/file/<path:filepath>")
class FileResource(Resource):
    def get(self, filepath):
        root_abs = os.path.abspath(config.MANGA_VIEWER_ROOT_PATH)
        rel_url_path = unquote(filepath).lstrip("/")
        if os.path.isabs(rel_url_path) or ":" in rel_url_path.split("/")[0]:
            return "Forbidden", 403
        safe_path = os.path.normpath(os.path.join(root_abs, rel_url_path.replace("/", os.sep)))
        if not safe_path.startswith(root_abs + os.sep) and safe_path != root_abs:
            return "Forbidden", 403
        if not os.path.isfile(safe_path):
            return "Not Found", 404
        return make_response(send_file(safe_path))

@api.route("/manga-viewer/folder/<folder_id>")
class FolderUpdateResource(Resource):
    def put(self, folder_id):
        folder = Repository.manga_index.folders.get(folder_id)
        if not folder:
            return jsonify({"error": "folder not found"}), 404

        data = request.json or {}
        new_name = (data.get("name") or "").strip()
        tags_dict = data.get("tags") or {}

        # update name, path, url list
        if new_name and new_name != folder.name:
            old_path = folder.path
            parent_dir = os.path.dirname(old_path)
            new_path = os.path.join(parent_dir, new_name)
            if os.path.exists(new_path):
                return jsonify({"error": "target name path already exists"}), 400
            try:
                os.rename(old_path, new_path)
            except OSError:
                return jsonify({"error": "rename failed"}), 500
            folder.name = new_name
            folder.path = new_path
            folder.file_list = Repository.get_files_url_list(folder.path)
            folder.initialized = True

        # update tags
        if tags_dict:
            folder.initialized = True
            def non_empty(v):
                if v is None:
                    return False
                if isinstance(v, (list, tuple, set, dict)):
                    return len(v) > 0
                if isinstance(v, str):
                    return v.strip() != ""
                return True  # bool / number

            for k in [
                "auth",
                "name",
                "category_main",
                "category_sub",
                "custom",
                "mosaic",
                "others",
            ]:
                if k in tags_dict:
                    v = tags_dict[k]
                    if non_empty(v):
                        setattr(folder.tags, k, v)

        # rebuild metadata
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

        Repository.save_index()

        # return clone value
        folder_dict = (
            folder.to_dict()
            if hasattr(folder, "to_dict")
            else {
                "id": folder.id,
                "name": folder.name,
                "path": folder.path,
                "size": folder.size,
                "number": folder.number,
                "file_list": folder.file_list,
                "tags": vars(folder.tags),
            }
        )
        return jsonify(folder_dict)

    def delete(self, folder_id):
        # Repository.load_index()
        folder = Repository.manga_index.folders.get(folder_id)
        if not folder:
            return jsonify({"error": "folder not found"}), 404
        folder_path = folder.path
        # 物理删除
        try:
            if os.path.isdir(folder_path):
                import shutil
                shutil.move(folder_path, config.MANGA_CLASSIFIER_DELETE_PATHS)
        except OSError:
            return jsonify({"error": "delete folder failed"}), 500
        # 从索引删除
        del Repository.manga_index.folders[folder_id]
        # 重建 metadata
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
        Repository.save_index()
        return jsonify({"deleted": folder_id})

restx_api.add_namespace(api)
