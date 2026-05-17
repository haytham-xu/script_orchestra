from flask_restx import Namespace, Resource
from flask import request, jsonify
from . import config
import os
import json
from pathlib import Path

ns = Namespace("")

WORKING_STATE_FILENAME = '.photo_classifier_working_state.json'

def get_working_state_path(root_path: str) -> Path:
    """Get the working state file path for a given root path"""
    return Path(root_path) / WORKING_STATE_FILENAME

@ns.route("/working-state")
class WorkingStateResource(Resource):

    def get(self):
        """Load working state for the current root path"""
        root_path = request.args.get('rootPath') or config.get_root_path()

        if not root_path:
            return {"error": "Root path not configured"}, 400

        if not os.path.exists(root_path):
            return {"error": "Root path does not exist"}, 404

        state_file = get_working_state_path(root_path)

        if not state_file.exists():
            return None, 200

        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state_data = json.load(f)
            return state_data, 200
        except Exception as e:
            return {"error": f"Failed to load working state: {str(e)}"}, 500

    def post(self):
        """Save working state for the current root path"""
        data = request.get_json()

        if not data:
            return {"error": "No data provided"}, 400

        root_path = data.get('rootPath') or config.get_root_path()

        if not root_path:
            return {"error": "Root path not configured"}, 400

        if not os.path.exists(root_path):
            return {"error": "Root path does not exist"}, 404

        state_file = get_working_state_path(root_path)

        # Prepare state data
        state_data = {
            "rootPath": root_path,
            "timestamp": data.get('timestamp'),
            "defaultGroup": data.get('defaultGroup'),
            "groupList": data.get('groupList')
        }

        try:
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(state_data, f, ensure_ascii=False, indent=2)
            return {"message": "Working state saved successfully"}, 200
        except Exception as e:
            return {"error": f"Failed to save working state: {str(e)}"}, 500

    def delete(self):
        """Delete working state for the current root path"""
        root_path = request.args.get('rootPath') or config.get_root_path()

        if not root_path:
            return {"error": "Root path not configured"}, 400

        state_file = get_working_state_path(root_path)

        if not state_file.exists():
            return {"message": "No working state to delete"}, 200

        try:
            state_file.unlink()
            return {"message": "Working state deleted successfully"}, 200
        except Exception as e:
            return {"error": f"Failed to delete working state: {str(e)}"}, 500
