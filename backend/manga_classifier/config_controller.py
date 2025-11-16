from flask_restx import Namespace, Resource
from flask import jsonify
import config
from extensions import restx_api

ns = Namespace("")

@ns.route("/manga-classifier/config")
class ConfigResource(Resource):

    def get(self):
        return jsonify(config.MANGA_CLASSIFIER_CATEGOTY)

restx_api.add_namespace(ns)
