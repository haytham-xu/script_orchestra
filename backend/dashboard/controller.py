"""Dashboard — REST controller (blueprint prefix /dashboard)."""
from flask_restx import Namespace, Resource
from flask import request

from . import layout_store

ns = Namespace("")


@ns.route("/layout")
class LayoutResource(Resource):
    def get(self):
        return {"layout": layout_store.load_layout()}, 200

    def put(self):
        data = request.json or {}
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            return {"error": "body must be {items: [...]}"}, 400
        saved = layout_store.save_layout(data)
        return {"layout": saved}, 200
