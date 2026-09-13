"""File Tracker — Blueprint."""
from flask import Blueprint
from flask_restx import Api
from .controller import ns

blueprint = Blueprint('file_tracker', __name__, url_prefix='/file-tracker')

api = Api(blueprint, title='File Tracker API', version='1.0', doc=False)
api.add_namespace(ns, path='/')
