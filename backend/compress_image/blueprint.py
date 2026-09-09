from flask import Blueprint
from flask_restx import Api
from .controller import ns

blueprint = Blueprint('compress_image', __name__, url_prefix='/compress-image')
api = Api(blueprint, title='Compress Image API', version='1.0', doc=False)
api.add_namespace(ns, path='/')
