from flask_restx import Namespace, Resource
from flask import send_file, make_response
from extensions import restx_api
from . import settings_manager
import os

api = Namespace("")

@api.route("/manga-classifier/file/<path:filepath>")
class FileResource(Resource):

    def get(self, filepath):
        root_path = settings_manager.load_settings().get("rootPath", "")
        file_path = os.path.join(root_path, filepath)
        if not os.path.exists(file_path):
            return "Not Found", 404
        response = make_response(send_file(file_path))
        return response

restx_api.add_namespace(api)
