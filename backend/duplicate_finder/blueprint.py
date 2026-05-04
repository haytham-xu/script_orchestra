"""
Duplicate Finder Blueprint

Independent module for finding and managing duplicate images.
"""
from flask import Blueprint
from flask_restx import Api
from .duplicate_finder_controller import ns as duplicate_finder_ns

# Create Blueprint
blueprint = Blueprint('duplicate_finder', __name__, url_prefix='/duplicate-finder')

# Create API instance
api = Api(
    blueprint,
    title='Duplicate Finder API',
    version='1.0',
    description='Find and manage duplicate images using perceptual hashing'
)

# Register namespace
api.add_namespace(duplicate_finder_ns, path='/')
