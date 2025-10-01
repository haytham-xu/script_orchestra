import os
import shutil
from pathlib import Path
from flask_restx import Namespace, Resource
from flask import request, jsonify
from extensions import restx_api
from photo_classifier import config

ns = Namespace("")

@ns.route("/photo-classifier/folder")
class FolderResource(Resource):
    def get(self):
        """List all files."""
        folder_abs_path = os.path.join(config.ROOT_PATH)
        files = []

        if not os.path.exists(folder_abs_path):
            return jsonify({"files": files})

        def collect_files_in_dir(base_path, relative_path=""):
            collected = []
            for fname in sorted(os.listdir(base_path)):
                full_path = os.path.join(base_path, fname)
                if os.path.isfile(full_path):
                    lower_name = fname.lower()
                    file_url = f"{config.HOST_URL}/photo-classifier/file/{'/' + relative_path if relative_path else ''}/{fname}"
                    if lower_name.endswith(config.IMAGE_EXTS):
                        collected.append({
                            "filePath": fname,
                            "fileUrl": file_url, 
                            "fileType": "image",
                            "fileStatus": "pending",
                            "categoryTag": None,
                            "groupId": None,
                        })
                    elif lower_name.endswith(config.VIDEO_EXTS):
                        collected.append({
                            "filePath": fname,
                            "fileUrl": file_url, 
                            "fileType": "video",
                            "fileStatus": "pending",
                            "categoryTag": None,
                            "groupId": None,
                        })
            return collected

        files.extend(collect_files_in_dir(folder_abs_path))
        return jsonify({"files": files})
    
    def post(self):
        """Move folder."""
        data = request.json
        source_folder_path = os.path.join(config.ROOT_PATH, data["sourceFolderPath"].lstrip("/"))
        target_folder_path = os.path.join(config.ROOT_PATH, data["targetFolderPath"].lstrip("/"))
        if not os.path.exists(source_folder_path):
            return "source folder not exist.", 404
        if not os.path.exists(target_folder_path):
            os.makedirs(target_folder_path)
        shutil.move(source_folder_path, target_folder_path)
        return {"message": "Accepted, processing started"}, 202
    
restx_api.add_namespace(ns)
