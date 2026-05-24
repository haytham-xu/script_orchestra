"""
Clipboard Share Blueprint

Independent module for LAN clipboard sharing.
"""
from flask import Blueprint
from flask_restx import Api
from .controller import ns as clipboard_ns

# Create Blueprint
blueprint = Blueprint('clipboard_share', __name__, url_prefix='/clipboard-share')

# Create API instance
api = Api(
    blueprint,
    title='Clipboard Share API',
    version='1.0',
    description='LAN clipboard sharing for cross-platform development (Mac <-> Windows)'
)

# Register namespace
api.add_namespace(clipboard_ns, path='/')
