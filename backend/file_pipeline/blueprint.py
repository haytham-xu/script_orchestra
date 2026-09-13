from flask import Blueprint
from flask_restx import Api
from .controller import ns

blueprint = Blueprint('file_pipeline', __name__, url_prefix='/file-pipeline')
api = Api(blueprint, title='File Pipeline API', version='1.0', doc=False)
api.add_namespace(ns, path='/')
