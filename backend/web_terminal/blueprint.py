"""Web Terminal — Blueprint."""
from flask import Blueprint
from flask_restx import Api
from .controller import ns as web_terminal_ns

blueprint = Blueprint('web_terminal', __name__, url_prefix='/web-terminal')

api = Api(
    blueprint,
    title='Web Terminal API',
    version='1.0',
    description='Browser-based terminal',
    doc=False,
)

api.add_namespace(web_terminal_ns, path='/')
