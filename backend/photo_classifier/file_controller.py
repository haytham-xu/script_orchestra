from flask_restx import Namespace, Resource
from flask import send_file, request
from . import config
import os

ns = Namespace("")

@ns.route("/file/<path:filepath>")
class FileResource(Resource):

    def get(self, filepath):
        # Support dynamic root path from query parameter
        root_path = request.args.get('rootPath') or config.get_root_path()

        if not root_path:
            return {"error": "Root path not configured"}, 400

        # Prevent path traversal attacks
        # Normalize the path and ensure it doesn't escape the root directory
        filepath = os.path.normpath(filepath)
        if filepath.startswith('..') or os.path.isabs(filepath):
            return {"error": "Invalid file path"}, 400

        file_path = os.path.join(root_path, filepath)

        # Double check the resolved path is within the root directory
        real_root = os.path.realpath(root_path)
        real_path = os.path.realpath(file_path)
        if not real_path.startswith(real_root):
            return {"error": "Access denied"}, 403

        if not os.path.exists(file_path):
            return {"error": "File not found"}, 404

        if not os.path.isfile(file_path):
            return {"error": "Not a file"}, 400

        # send_file already returns a Response object, no need to wrap it
        return send_file(file_path)
