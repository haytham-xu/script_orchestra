"""
Knowledge Vault Blueprint

AI-organized knowledge fragment store. Raw fragments are append-only; the AI
builds a derived, rebuildable knowledge network (relations, dedup, lifecycle).
"""
from flask import Blueprint
from flask_restx import Api
from .controller import ns as knowledge_vault_ns

blueprint = Blueprint('knowledge_vault', __name__, url_prefix='/knowledge-vault')

api = Api(
    blueprint,
    title='Knowledge Vault API',
    version='1.0',
    description='AI-organized knowledge fragment store'
)

api.add_namespace(knowledge_vault_ns, path='/')
