"""File Duplicate Blueprint"""
from flask import Blueprint
from flask_restx import Api
from .controller import ns as file_duplicate_ns

blueprint = Blueprint('file_duplicate', __name__, url_prefix='/file-duplicate')

api = Api(
    blueprint,
    title='File Duplicate API',
    version='1.0',
    description='Exact-match duplicate file finder across multiple backup roots'
)

api.add_namespace(file_duplicate_ns, path='/')
