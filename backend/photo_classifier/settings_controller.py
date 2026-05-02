import os
from flask_restx import Namespace, Resource
from flask import request
from . import settings_manager

ns = Namespace("")


@ns.route("/settings")
class SettingsResource(Resource):
    def get(self):
        """Get current settings"""
        settings = settings_manager.load_settings()
        return {"settings": settings}, 200

    def put(self):
        """Update settings"""
        data = request.json
        if not data:
            return {"error": "No data provided"}, 400

        try:
            # Update root path if provided
            if 'rootPath' in data:
                root_path = data['rootPath'].strip()

                # Validate path exists
                if root_path and not os.path.exists(root_path):
                    return {"error": f"Path does not exist: {root_path}"}, 400

                settings_manager.set_root_path(root_path)

            return {
                "message": "Settings updated successfully",
                "settings": settings_manager.load_settings()
            }, 200

        except Exception as e:
            return {"error": f"Failed to update settings: {str(e)}"}, 500
