from flask_restx import Namespace, Resource
from flask import request, jsonify
from extensions import restx_api
from manga_viewer.settings_manager import settings_manager

api = Namespace("")

@api.route("/manga-viewer/settings")
class SettingsResource(Resource):
    def get(self):
        """Get all settings."""
        return jsonify(settings_manager.get_settings())

    def put(self):
        """Update settings."""
        updates = request.json or {}
        if not isinstance(updates, dict):
            return jsonify({"error": "invalid payload"}), 400

        settings_manager.update_settings(updates)
        return jsonify(settings_manager.get_settings())

restx_api.add_namespace(api)
