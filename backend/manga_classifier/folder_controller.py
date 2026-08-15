import os
import shutil
from basic.flex_sort import flex_natsort
from pathlib import Path
from flask_restx import Namespace, Resource
from flask import request, jsonify
from extensions import restx_api
import config
from . import settings_manager

ns = Namespace("")

# Session-scoped stack of undoable move/delete operations.
# Each entry: {"source_original": str, "moved_to": str}
# Not persisted — dies with the process.
_operation_stack: list = []


def _record_operation(source_original: str, moved_to: str) -> None:
    _operation_stack.append({
        "source_original": source_original,
        "moved_to": moved_to,
    })


def _pop_operation_for_source(source_original: str) -> dict | None:
    """Find and remove the newest operation matching the given source path."""
    for i in range(len(_operation_stack) - 1, -1, -1):
        if _operation_stack[i]["source_original"] == source_original:
            return _operation_stack.pop(i)
    return None


@ns.route("/manga-classifier/folder")
class FolderResource(Resource):
    def get(self):
        """List all folders."""
        settings = settings_manager.load_settings()
        root_path = settings.get("rootPath", "")
        if not root_path or not os.path.isdir(root_path):
            return jsonify({"folderList": []})
        folderList = sorted([f.name for f in Path(root_path).iterdir() if f.is_dir()])
        folderObjectsList = [
            {"folderName": folderName, "status": "pending"}
            for folderName in folderList
        ]
        return jsonify({"folderList": folderObjectsList})

    def post(self):
        """Move folder."""
        settings = settings_manager.load_settings()
        root_path = settings.get("rootPath", "")
        target_root = settings.get("targetPath", "")
        data = request.json
        source_folder_path = os.path.join(root_path, data["sourceFolderPath"].lstrip("/\\"))
        target_folder_path = os.path.join(target_root, data["targetFolderPath"].lstrip("/\\"))
        if not os.path.exists(source_folder_path):
            return "source folder not exist.", 404
        if not os.path.exists(target_folder_path):
            os.makedirs(target_folder_path)
        source_basename = os.path.basename(source_folder_path.rstrip("/\\"))
        final_path = os.path.join(target_folder_path, source_basename)
        shutil.move(source_folder_path, target_folder_path)
        _record_operation(source_folder_path, final_path)
        return {"message": "Accepted, processing started"}, 202


@ns.route("/manga-classifier/folder/delete")
class DeleteFolderResource(Resource):
    def post(self):
        """Move folder to the configured delete path."""
        settings = settings_manager.load_settings()
        root_path = settings.get("rootPath", "")
        delete_root = settings.get("deletePath", "")
        if not delete_root:
            return {"error": "deletePath is not configured"}, 400
        data = request.json or {}
        source_name = data.get("sourceFolderPath", "").lstrip("/\\")
        if not source_name:
            return {"error": "sourceFolderPath is required"}, 400
        source_folder_path = os.path.join(root_path, source_name)
        if not os.path.exists(source_folder_path):
            return {"error": "source folder not exist"}, 404
        if not os.path.exists(delete_root):
            os.makedirs(delete_root)
        source_basename = os.path.basename(source_folder_path.rstrip("/\\"))
        final_path = os.path.join(delete_root, source_basename)
        shutil.move(source_folder_path, delete_root)
        _record_operation(source_folder_path, final_path)
        return {"message": "Accepted, processing started"}, 202


@ns.route("/manga-classifier/folder/undo")
class UndoResource(Resource):
    def post(self):
        """Reverse a specific operation from the undo stack.

        Body: {"sourceFolderPath": <name>}  # required — undo only that folder.
        """
        settings = settings_manager.load_settings()
        root_path = settings.get("rootPath", "")
        data = request.json or {}
        source_name = (data.get("sourceFolderPath") or "").lstrip("/\\")
        if not source_name:
            return {"error": "sourceFolderPath is required"}, 400
        source_original = os.path.join(root_path, source_name)
        entry = _pop_operation_for_source(source_original)
        if entry is None:
            return {"error": "Nothing to undo for this folder"}, 404
        moved_to = entry["moved_to"]
        if not os.path.exists(moved_to):
            return {"error": f"Moved folder is missing: {moved_to}"}, 404
        original_parent = os.path.dirname(source_original)
        if os.path.exists(source_original):
            return {"error": f"Original path already occupied: {source_original}"}, 409
        if not os.path.exists(original_parent):
            os.makedirs(original_parent)
        shutil.move(moved_to, source_original)
        restored_name = os.path.basename(source_original)
        return {"message": "Undone", "restoredName": restored_name}, 200


@ns.route("/manga-classifier/folder/undoable")
class UndoableResource(Resource):
    def get(self):
        """Return the list of source paths currently undoable in this session."""
        return {
            "sources": [os.path.basename(e["source_original"].rstrip("/\\"))
                        for e in _operation_stack]
        }, 200


@ns.route("/manga-classifier/folder/<folder_name>")
class FilesResource(Resource):
    def get(self, folder_name):
        """Get file list for a folder (including one level of subfolders)."""
        settings = settings_manager.load_settings()
        root_path = settings.get("rootPath", "")
        image_exts = tuple(settings.get("imageExts", []))
        video_exts = tuple(settings.get("videoExts", []))

        folder_abs_path = os.path.join(root_path, folder_name)
        files = []

        if not os.path.exists(folder_abs_path):
            return jsonify({"files": files})

        def collect_files_in_dir(base_path, relative_path=""):
            collected = []
            for fname in flex_natsort(os.listdir(base_path)):
                full_path = os.path.join(base_path, fname)
                if os.path.isfile(full_path):
                    lower_name = fname.lower()
                    file_url = f"{config.HOST_URL}/manga-classifier/file/{folder_name}{'/' + relative_path if relative_path else ''}/{fname}"
                    if image_exts and lower_name.endswith(image_exts):
                        collected.append({"fileUrl": file_url, "fileType": "image"})
                    elif video_exts and lower_name.endswith(video_exts):
                        collected.append({"fileUrl": file_url, "fileType": "video"})
            return collected

        files.extend(collect_files_in_dir(folder_abs_path))

        for dname in flex_natsort(os.listdir(folder_abs_path)):
            sub_dir_path = os.path.join(folder_abs_path, dname)
            if os.path.isdir(sub_dir_path):
                files.extend(collect_files_in_dir(sub_dir_path, relative_path=dname))

        return jsonify({"files": files})


restx_api.add_namespace(ns)
