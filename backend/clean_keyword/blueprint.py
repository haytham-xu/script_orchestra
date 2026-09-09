from flask import Blueprint
from flask_restx import Api
from .controller import ns

blueprint = Blueprint('clean_keyword', __name__, url_prefix='/clean-keyword')

api = Api(blueprint, title='Clean Keyword API', version='1.0', doc=False,
          description='Strip noise keywords from folder names')

api.add_namespace(ns, path='/')
