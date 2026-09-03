"""Relay Proxy blueprint."""
from flask import Blueprint
from flask_restx import Api

from .controller import ns as relay_proxy_ns

blueprint = Blueprint('relay_proxy', __name__, url_prefix='/relay-proxy')

api = Api(
    blueprint,
    title='Relay Proxy API',
    version='1.0',
    description='LAN relay proxy with HTTP CONNECT and SOCKS5 support',
)

api.add_namespace(relay_proxy_ns, path='/')
