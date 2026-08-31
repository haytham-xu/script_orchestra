"""
Translator Blueprint

Text-processing tool backed by GitHub Copilot. Two decoupled scenes:
zh→en (Slack-style + back-translation + English learning points) and
en→zh (faithful objective translation). History and learning points persist.
"""
from flask import Blueprint
from flask_restx import Api
from .controller import ns as translator_ns

blueprint = Blueprint('translator', __name__, url_prefix='/translator')

api = Api(
    blueprint,
    title='Translator API',
    version='1.0',
    description='Copilot-backed translator (zh↔en) with English learning points'
)

api.add_namespace(translator_ns, path='/')

# Package init also needs an empty __init__.py; created separately.
