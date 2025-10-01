import os
import shutil
from natsort import natsorted
from pathlib import Path
from flask_restx import Namespace, Resource
from flask import request, jsonify
from extensions import restx_api
from manga_classifier import config

ns = Namespace("")

@ns.route("/manga-classifier/folder")
class FolderResource(Resource):
    def get(self):
        """List all folders."""
        folderList = sorted([f.name for f in Path(config.ROOT_PATH).iterdir() if f.is_dir()])
        folderObjectsList = [
            {
                "folderName": folderName,
                "status": "pending"
            }
            for folderName in folderList
        ]
        return jsonify({"folderList": folderObjectsList})
    
    def post(self):
        """Move folder."""
        data = request.json
        source_folder_path= os.path.join(config.ROOT_PATH, data["sourceFolderPath"].lstrip("/"))
        target_folder_path = os.path.join(config.TARGET_PATHS, data["targetFolderPath"].lstrip("/"))
        if not os.path.exists(source_folder_path):
            return "source folder not exist.", 404
        if not os.path.exists(target_folder_path):
            os.makedirs(target_folder_path)
        shutil.move(source_folder_path, target_folder_path)
        # print(f"Moving {source_folder_path} to {target_folder_path}")
        return {"message": "Accepted, processing started"}, 202
    
@ns.route("/manga-classifier/folder/<folder_name>")
class FilesResource(Resource):
    def get(self, folder_name):
        """Get file list for a folder (including one level of subfolders)."""
        folder_abs_path = os.path.join(config.ROOT_PATH, folder_name)
        files = []

        if not os.path.exists(folder_abs_path):
            return jsonify({"files": files})

        def collect_files_in_dir(base_path, relative_path=""):
            collected = []
            for fname in natsorted(os.listdir(base_path)):
                full_path = os.path.join(base_path, fname)
                if os.path.isfile(full_path):
                    lower_name = fname.lower()
                    file_url = f"{config.HOST_URL}/manga-classifier/file/{folder_name}{'/' + relative_path if relative_path else ''}/{fname}"
                    if lower_name.endswith(config.IMAGE_EXTS):
                        collected.append({"fileUrl": file_url, "fileType": "image"})
                    elif lower_name.endswith(config.VIDEO_EXTS):
                        collected.append({"fileUrl": file_url, "fileType": "video"})
            return collected

        files.extend(collect_files_in_dir(folder_abs_path))

        for dname in natsorted(os.listdir(folder_abs_path)):
            sub_dir_path = os.path.join(folder_abs_path, dname)
            if os.path.isdir(sub_dir_path):
                files.extend(collect_files_in_dir(sub_dir_path, relative_path=dname))
                
        return jsonify({"files": files})
    
restx_api.add_namespace(ns)
