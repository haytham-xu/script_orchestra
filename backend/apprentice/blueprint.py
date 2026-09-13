"""Apprentice Blueprint."""
from flask import Blueprint
from flask_restx import Api
from .controller import ns as apprentice_ns

blueprint = Blueprint('apprentice', __name__, url_prefix='/apprentice')

api = Api(
    blueprint,
    title='Apprentice API',
    version='1.0',
    description='Autonomous developer agent',
    doc=False,
)

api.add_namespace(apprentice_ns, path='/')
