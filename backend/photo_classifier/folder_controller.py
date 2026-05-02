import os
import shutil
from pathlib import Path
from flask_restx import Namespace, Resource
from flask import request
from . import config

ns = Namespace("")

@ns.route("/folder")
class FolderResource(Resource):
    def get(self):
        """List all files."""
        # Support dynamic root path from query parameter
        root_path = request.args.get('rootPath') or config.get_root_path()

        if not root_path:
            return {"error": "Root path not configured"}, 400

        folder_abs_path = os.path.abspath(root_path)
        files = []

        if not os.path.exists(folder_abs_path):
            return {"files": files}

        def collect_files_in_dir(base_path):
            collected = []
            for fname in sorted(os.listdir(base_path)):
                full_path = os.path.join(base_path, fname)
                if os.path.isfile(full_path):
                    lower_name = fname.lower()
                    # Include rootPath in file URL for dynamic path support
                    file_url = f"{config.HOST_URL}/photo-classifier/file/{fname}?rootPath={root_path}"
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
        return {"files": files}
    
    def post(self):
        """Move file to target folder."""
        data = request.json
        if not data:
            return {"error": "No data provided"}, 400

        if "sourceFolderPath" not in data or "targetFolderPath" not in data:
            return {"error": "Missing required fields"}, 400

        # Support dynamic root path
        root_path = data.get('rootPath') or config.get_root_path()

        if not root_path:
            return {"error": "Root path not configured"}, 400

        # sourceFolderPath is the filename, targetFolderPath is the category folder name
        source_file_path = os.path.join(root_path, data["sourceFolderPath"].lstrip("/"))
        target_folder_name = data["targetFolderPath"].lstrip("/")
        target_folder_path = os.path.join(root_path, target_folder_name)

        # Validate source file exists
        if not os.path.exists(source_file_path):
            return {"error": f"Source file does not exist: {data['sourceFolderPath']}"}, 404

        if not os.path.isfile(source_file_path):
            return {"error": f"Source is not a file: {data['sourceFolderPath']}"}, 400

        try:
            # Create target folder if it doesn't exist
            if not os.path.exists(target_folder_path):
                os.makedirs(target_folder_path)

            # Move file to target folder
            filename = os.path.basename(source_file_path)
            destination_path = os.path.join(target_folder_path, filename)

            # Check if destination already exists
            if os.path.exists(destination_path):
                return {"error": f"File already exists at destination: {destination_path}"}, 409

            shutil.move(source_file_path, destination_path)
            return {"message": f"File moved successfully to {target_folder_name}/{filename}"}, 202
        except Exception as e:
            return {"error": f"Failed to move file: {str(e)}"}, 500
