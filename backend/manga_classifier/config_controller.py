from flask_restx import Namespace, Resource
from flask import jsonify
from extensions import restx_api
from . import settings_manager

ns = Namespace("")

@ns.route("/manga-classifier/config")
class ConfigResource(Resource):

    def get(self):
        return jsonify(settings_manager.load_settings().get("categoty", {}))

restx_api.add_namespace(ns)
