"""
Photo Classifier API

Independent Flask-RESTX API instance for photo classifier module.
Uses Blueprint for true independence.
"""
from flask import Blueprint
from flask_restx import Api

# Create Blueprint
blueprint = Blueprint('photo_classifier', __name__, url_prefix='/photo-classifier')

# Create API instance attached to blueprint
api = Api(
    blueprint,
    version="1.0",
    title="Photo Classifier API",
    description="Standalone API for photo classification and organization",
    doc=False,  # Disable Swagger UI
)

# Register namespaces
from .file_controller import ns as file_ns
from .folder_controller import ns as folder_ns
from .settings_controller import ns as settings_ns
from .working_state_controller import ns as working_state_ns

api.add_namespace(file_ns)
api.add_namespace(folder_ns)
api.add_namespace(settings_ns)
api.add_namespace(working_state_ns)
