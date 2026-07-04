"""
Video Duplicate Finder — Flask Blueprint registration.

Mounts the controller's Namespace under URL prefix `/video-duplicate-finder`.
The actual route handlers live in `video_duplicate_finder_controller`.

DECOUPLED: this module must not import from duplicate_finder.
"""
from flask import Blueprint
from flask_restx import Api

from .video_duplicate_finder_controller import ns as video_duplicate_finder_ns

# Flask Blueprint — `name` must be globally unique across the Flask app, so
# we use the package name verbatim. URL prefix mirrors duplicate_finder's
# pattern (kebab-case for the path, snake-case for the package name).
blueprint = Blueprint('video_duplicate_finder', __name__,
                      url_prefix='/video-duplicate-finder')

api = Api(
    blueprint,
    title='Video Duplicate Finder API',
    version='1.0',
    description='Find and manage duplicate videos using N-frame perceptual hashing.',
)

api.add_namespace(video_duplicate_finder_ns, path='/')
