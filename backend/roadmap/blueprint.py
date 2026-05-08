"""
Roadmap Blueprint

Simple Kanban board for personal task tracking.
"""
from flask import Blueprint
from flask_restx import Api
from .controller import ns as roadmap_ns

# Create Blueprint
blueprint = Blueprint('roadmap', __name__, url_prefix='/roadmap')

# Create API instance
api = Api(
    blueprint,
    title='Roadmap Kanban API',
    version='1.0',
    description='Simple Kanban board for personal task tracking'
)

# Register namespace
api.add_namespace(roadmap_ns, path='/')
