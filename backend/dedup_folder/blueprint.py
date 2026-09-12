from flask import Blueprint
from flask_restx import Api
from .controller import ns

blueprint = Blueprint('dedup_folder', __name__, url_prefix='/dedup-folder')
api = Api(blueprint, title='Dedup Folder API', version='1.0', doc=False)
api.add_namespace(ns, path='/')
