"""Proxy Forward Blueprint."""
from flask import Blueprint
from flask_restx import Api

from .controller import ns as proxy_forward_ns

blueprint = Blueprint('proxy_forward', __name__, url_prefix='/proxy-forward')

api = Api(
    blueprint,
    title='Proxy Forward API',
    version='1.0',
    description='LAN-accessible TCP port forwarder',
)

api.add_namespace(proxy_forward_ns, path='/')
