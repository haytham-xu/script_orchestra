"""
Manga Classifier Settings Controller

REST endpoints for reading and updating persistent settings.
"""
import os
from flask_restx import Namespace, Resource
from flask import request
from extensions import restx_api
from . import settings_manager

ns = Namespace("")


def _validate_and_normalize(patch: dict, current: dict) -> dict:
    merged = dict(current)

    for path_key in ("rootPath", "targetPath", "deletePath"):
        if path_key in patch:
            value = patch[path_key]
            if not isinstance(value, str):
                raise ValueError(f"{path_key} must be a string")
            value = value.strip()
            # Only rootPath must exist — it's the read source and cannot be auto-created.
            # targetPath / deletePath are auto-created by folder move operations, so
            # allowing not-yet-existent values here lets users configure ahead of time.
            if path_key == "rootPath" and value and not os.path.exists(value):
                raise FileNotFoundError(f"Path does not exist: {value}")
            merged[path_key] = value

    for ext_key in ("imageExts", "videoExts"):
        if ext_key in patch:
            merged[ext_key] = settings_manager.normalize_ext_list(patch[ext_key])

    if "categoty" in patch:
        merged["categoty"] = settings_manager.validate_button_config(patch["categoty"])

    if "imageWidthPx" in patch:
        try:
            width = int(patch["imageWidthPx"])
        except (TypeError, ValueError):
            raise ValueError("imageWidthPx must be an integer")
        merged["imageWidthPx"] = max(200, min(width, 2000))

    if "scrollPageRatio" in patch:
        try:
            ratio = float(patch["scrollPageRatio"])
        except (TypeError, ValueError):
            raise ValueError("scrollPageRatio must be a number")
        merged["scrollPageRatio"] = max(0.1, min(ratio, 1.0))

    if "pinSidebars" in patch:
        merged["pinSidebars"] = bool(patch["pinSidebars"])

    return merged


@ns.route("/manga-classifier/settings")
class MangaClassifierSettingsResource(Resource):
    def get(self):
        return {"settings": settings_manager.load_settings()}, 200

    def put(self):
        data = request.json or {}
        if not isinstance(data, dict):
            return {"error": "Body must be a JSON object"}, 400
        try:
            current = settings_manager.load_settings()
            updated = _validate_and_normalize(data, current)
            settings_manager.save_settings(updated)
            return {"message": "Settings updated successfully", "settings": updated}, 200
        except FileNotFoundError as e:
            return {"error": str(e)}, 400
        except ValueError as e:
            return {"error": str(e)}, 400
        except Exception as e:
            return {"error": f"Failed to update settings: {e}"}, 500


restx_api.add_namespace(ns)
