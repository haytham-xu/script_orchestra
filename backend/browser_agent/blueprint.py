"""
Browser Agent Blueprint

Extensible browser-extension platform. First feature: batch tab download
(collect tab URLs from the extension, resolve download links, queue and
download in the background).
"""
from flask import Blueprint
from flask_restx import Api
from .controller import ns as browser_agent_ns

blueprint = Blueprint('browser_agent', __name__, url_prefix='/browser-agent')

api = Api(
    blueprint,
    title='Browser Agent API',
    version='1.0',
    description='Browser extension companion: tab collection and download queue'
)

api.add_namespace(browser_agent_ns, path='/')
