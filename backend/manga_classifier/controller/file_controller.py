from flask_restx import Namespace, Resource
from flask import send_file, make_response
from extensions import restx_api
from manga_classifier import config
import os

api = Namespace("")

@api.route("/manga-classifier/file/<path:filepath>")
class FileResource(Resource):

    def get(self, filepath):
        file_path = os.path.join(config.ROOT_PATH,filepath)
        if not os.path.exists(file_path):
            return "Not Found", 404
        response = make_response(send_file(file_path))
        # response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        # response.headers["Pragma"] = "no-cache"
        # response.headers["Expires"] = "0"
        return response
    
restx_api.add_namespace(api)
