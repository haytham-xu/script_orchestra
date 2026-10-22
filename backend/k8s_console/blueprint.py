"""K8s Console — Blueprint."""
from flask import Blueprint
from flask_restx import Api
from .controller import ns as k8s_console_ns

blueprint = Blueprint('k8s_console', __name__, url_prefix='/k8s-console')

api = Api(
    blueprint,
    title='K8s Console API',
    version='1.0',
    description='Kubernetes cluster management console',
    doc=False,
)

api.add_namespace(k8s_console_ns, path='/')
