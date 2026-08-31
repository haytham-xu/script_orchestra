"""Claude Bridge Blueprint.

Remote Claude Code agent (Agent SDK driven). Sessions over HTTP; conversation
streams over the /claude-bridge WebSocket namespace.
"""
from flask import Blueprint
from flask_restx import Api
from .controller import ns as claude_bridge_ns

blueprint = Blueprint('claude_bridge', __name__, url_prefix='/claude-bridge')

api = Api(
    blueprint,
    title='Claude Bridge API',
    version='1.0',
    description='Remote Claude Code agent'
)

api.add_namespace(claude_bridge_ns, path='/')
