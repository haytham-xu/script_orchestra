from flask_restx import Namespace, Resource
from flask import jsonify
from manga_classifier import config
from extensions import restx_api

ns = Namespace("")

@ns.route("/manga-classifier/config")
class ConfigResource(Resource):

    def get(self):
        return jsonify(config.CATEGOTY)

restx_api.add_namespace(ns)
