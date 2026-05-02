from flask_restx import Namespace, Resource
from flask import send_file
from extensions import restx_api
import config
import os

api = Namespace("")

@api.route("/photo-classifier/file/<path:filepath>")
class FileResource(Resource):

    def get(self, filepath):
        # Prevent path traversal attacks
        # Normalize the path and ensure it doesn't escape the root directory
        filepath = os.path.normpath(filepath)
        if filepath.startswith('..') or os.path.isabs(filepath):
            return {"error": "Invalid file path"}, 400

        file_path = os.path.join(config.PHOTO_CLASSIFIER_ROOT_PATH, filepath)

        # Double check the resolved path is within the root directory
        real_root = os.path.realpath(config.PHOTO_CLASSIFIER_ROOT_PATH)
        real_path = os.path.realpath(file_path)
        if not real_path.startswith(real_root):
            return {"error": "Access denied"}, 403

        if not os.path.exists(file_path):
            return {"error": "File not found"}, 404

        if not os.path.isfile(file_path):
            return {"error": "Not a file"}, 400

        # send_file already returns a Response object, no need to wrap it
        return send_file(file_path)

restx_api.add_namespace(api)
