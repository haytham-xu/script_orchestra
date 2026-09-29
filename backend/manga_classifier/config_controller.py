import os
import json
from flask_restx import Namespace, Resource
from flask import jsonify, request
from extensions import restx_api
from . import settings_manager

ns = Namespace("")

MANGA_VIEWER_SETTINGS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "manga_viewer", "settings.json"
)

def _load_manga_viewer_index():
    """Load the manga_viewer JSON index. Returns (folders_dict, error_str)."""
    try:
        with open(MANGA_VIEWER_SETTINGS_FILE, "r", encoding="utf-8") as f:
            mv_settings = json.load(f)
        root_path = mv_settings.get("paths", {}).get("root_path", "")
        if not root_path:
            return None, "manga_viewer root_path is not configured"
        index_file = os.path.join(root_path, ".manga_index", "manga_index.json")
        if not os.path.exists(index_file):
            return None, f"index file not found: {index_file}"
        with open(index_file, "r", encoding="utf-8") as f:
            idx = json.load(f)
        return idx.get("folders", {}), None
    except Exception as e:
        return None, str(e)


@ns.route("/manga-classifier/config")
class ConfigResource(Resource):

    def get(self):
        s = settings_manager.load_settings()
        config = dict(s.get("categoty", {}))
        config["epic"] = s.get("epicCategory", {"name": "Epic", "mainButtons": [], "subButtons": []})
        return jsonify(config)


@ns.route("/manga-classifier/scan-subfolders")
class ScanSubfoldersResource(Resource):

    def post(self):
        body = request.get_json(silent=True) or {}
        scan_path = (body.get("path") or "").strip()
        if not scan_path:
            return {"error": "path is required"}, 400
        if not os.path.isdir(scan_path):
            return {"error": f"path does not exist or is not a directory: {scan_path}"}, 400

        main_key = os.path.basename(scan_path.rstrip("/\\"))

        # Collect immediate subdirs
        try:
            subdirs = sorted([
                d for d in os.listdir(scan_path)
                if os.path.isdir(os.path.join(scan_path, d))
            ])
        except Exception as e:
            return {"error": f"cannot list directory: {e}"}, 500

        folders, err = _load_manga_viewer_index()
        if err:
            return {"error": err}, 500

        # Count index entries per (category_main, category_sub)
        counts: dict = {}
        for fdata in folders.values():
            tags = fdata.get("tags", {})
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except Exception:
                    tags = {}
            cm = tags.get("category_main", "")
            cs = tags.get("category_sub", "")
            if cm == main_key:
                counts[cs] = counts.get(cs, 0) + 1

        items = []
        for sub in subdirs:
            items.append({
                "name": sub,
                "folderPath": f"{main_key}/{sub}",
                "count": counts.get(sub, 0),
            })

        # Sort by count desc, then name asc
        items.sort(key=lambda x: (-x["count"], x["name"]))

        return jsonify({"items": items})


restx_api.add_namespace(ns)
