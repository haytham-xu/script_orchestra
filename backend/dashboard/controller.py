"""Dashboard — REST controller (blueprint prefix /dashboard)."""
from flask_restx import Namespace, Resource
from flask import request

from . import layout_store
from . import tool_meta_store

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


@ns.route("/tool-meta")
class ToolMetaResource(Resource):
    def get(self):
        return {"meta": tool_meta_store.load_meta()}, 200

    def put(self):
        data = request.json or {}
        if not isinstance(data, dict):
            return {"error": "body must be a dict keyed by tool key"}, 400
        saved = tool_meta_store.save_meta(data)
        return {"meta": saved}, 200


@ns.route("/tool-meta/<string:tool_key>")
class ToolMetaItemResource(Resource):
    def patch(self, tool_key):
        patch = request.json or {}
        if not isinstance(patch, dict):
            return {"error": "body must be a dict"}, 400
        status = patch.get("status")
        if status and status not in tool_meta_store.VALID_STATUSES:
            return {"error": f"status must be one of: {', '.join(sorted(tool_meta_store.VALID_STATUSES))}"}, 400
        saved = tool_meta_store.patch_tool(tool_key, patch)
        return {"meta": saved}, 200
