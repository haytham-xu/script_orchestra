"""
Assistant Blueprint
"""
from flask import Blueprint
from flask_restx import Api

from .controller import ns as assistant_ns

blueprint = Blueprint('assistant', __name__, url_prefix='/assistant')

api = Api(
    blueprint,
    title='Assistant API',
    version='1.0',
    description='ChatGPT-style Claude assistant with adaptive model routing',
)

api.add_namespace(assistant_ns, path='/assistant')
