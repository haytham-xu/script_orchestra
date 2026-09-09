from flask import Blueprint
from flask_restx import Api
from .controller import ns

blueprint = Blueprint('loans_calc', __name__, url_prefix='/loans-calc')
api = Api(blueprint, title='Loans Calculator API', version='1.0', doc=False)
api.add_namespace(ns, path='/')
