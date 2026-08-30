"""
Dashboard Blueprint

Persists the user's Launchpad-style dashboard layout (tool order + folders).
Pure storage — reconciliation against the code-defined tool list happens in the
frontend.
"""
from flask import Blueprint
from flask_restx import Api
from .controller import ns as dashboard_ns

blueprint = Blueprint('dashboard', __name__, url_prefix='/dashboard')

api = Api(
    blueprint,
    title='Dashboard API',
    version='1.0',
    description='Launchpad-style dashboard layout persistence'
)

api.add_namespace(dashboard_ns, path='/')
