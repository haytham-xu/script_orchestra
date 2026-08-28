"""
Memory Curve Blueprint

Spaced-repetition flashcards (Ebbinghaus / SM-2). Cards are user-editable;
the tool schedules reviews at expanding intervals.
"""
from flask import Blueprint
from flask_restx import Api
from .controller import ns as memory_curve_ns

blueprint = Blueprint('memory_curve', __name__, url_prefix='/memory-curve')

api = Api(
    blueprint,
    title='Memory Curve API',
    version='1.0',
    description='Spaced-repetition flashcards'
)

api.add_namespace(memory_curve_ns, path='/')
