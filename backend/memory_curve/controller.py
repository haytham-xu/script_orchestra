"""Memory Curve — REST controller (blueprint prefix /memory-curve)."""
from flask_restx import Namespace, Resource
from flask import request

from . import repository, settings_manager
from .entity import Card
from .scheduler import apply_review

ns = Namespace("")


@ns.route("/cards")
class CardsResource(Resource):
    def get(self):
        return {"cards": [c.to_dict() for c in repository.get_all()]}, 200

    def post(self):
        data = request.json or {}
        front = (data.get("front") or "").strip()
        if not front:
            return {"error": "front is required"}, 400
        card = Card.new_instance(front, (data.get("back") or "").strip(),
                                 (data.get("deck") or "").strip())
        repository.insert(card)
        return {"card": card.to_dict()}, 201


@ns.route("/cards/<int:card_id>")
class CardResource(Resource):
    def put(self, card_id):
        card = repository.get_by_id(card_id)
        if card is None:
            return {"error": "card not found"}, 404
        data = request.json or {}
        if "front" in data:
            card.front = (data["front"] or "").strip()
        if "back" in data:
            card.back = (data["back"] or "").strip()
        if "deck" in data:
            card.deck = (data["deck"] or "").strip()
        if "suspended" in data:
            card.suspended = 1 if data["suspended"] else 0
        repository.update(card)
        return {"card": card.to_dict()}, 200

    def delete(self, card_id):
        if repository.get_by_id(card_id) is None:
            return {"error": "card not found"}, 404
        repository.delete(card_id)
        return {"message": "deleted"}, 200


@ns.route("/due")
class DueResource(Resource):
    def get(self):
        return {"cards": [c.to_dict() for c in repository.get_due()]}, 200


@ns.route("/cards/<int:card_id>/review")
class ReviewResource(Resource):
    def post(self, card_id):
        card = repository.get_by_id(card_id)
        if card is None:
            return {"error": "card not found"}, 404
        rating = (request.json or {}).get("rating", "")
        try:
            apply_review(card, rating)
        except ValueError as e:
            return {"error": str(e)}, 400
        repository.update(card)
        return {"card": card.to_dict()}, 200


@ns.route("/settings")
class SettingsResource(Resource):
    def get(self):
        return {"settings": settings_manager.load_settings()}, 200

    def put(self):
        data = request.json or {}
        if not isinstance(data, dict):
            return {"error": "Body must be a JSON object"}, 400
        try:
            updated = settings_manager.validate_and_normalize(
                data, settings_manager.load_settings())
            settings_manager.save_settings(updated)
            return {"settings": updated, "message": "Settings updated"}, 200
        except ValueError as e:
            return {"error": str(e)}, 400
