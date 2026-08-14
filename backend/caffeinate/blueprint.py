"""
Caffeinate Blueprint
"""
from flask import Blueprint
from flask_restx import Api

from .controller import ns as caffeinate_ns

blueprint = Blueprint('caffeinate', __name__, url_prefix='/caffeinate')

api = Api(
    blueprint,
    title='Caffeinate API',
    version='1.0',
    description='Keep macOS awake and stream heartbeat log lines to the UI',
)

api.add_namespace(caffeinate_ns, path='/caffeinate')
