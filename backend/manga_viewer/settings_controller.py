from flask_restx import Namespace, Resource
from flask import request, jsonify
from extensions import restx_api
from manga_viewer.settings_manager import settings_manager
import os

api = Namespace("")


def _validate_categories(updates: dict):
    """Validate category config on PUT:
      - Every category must have a non-empty key AND a non-empty path
        (path drives the on-disk folder; an empty path corrupts moves).
      - If root_path is known, each path must exist on disk:
          main: <root>/<main.path> ; sub: <root>/<some main.path>/<sub.path>
    Returns an error string, or None if valid.
    """
    if "categories" not in updates:
        return None
    merged = dict(settings_manager.get_settings())
    settings_manager._deep_merge(merged, updates)

    cats = merged.get("categories", {})
    mains = [settings_manager.normalize_category(c) for c in cats.get("main", [])]
    subs = [settings_manager.normalize_category(c) for c in cats.get("sub", [])]

    # Required fields (structural — checked regardless of root_path).
    for label, items in (("main", mains), ("sub", subs)):
        for c in items:
            if not c["key"].strip():
                return f"{label} category: key is required"
            if not c["path"].strip():
                return f"{label} category '{c['key']}': path is required"

    root = merged.get("paths", {}).get("root_path", "")
    if not root:
        return None  # can't validate existence without a root

    main_paths = [m["path"] for m in mains if m["path"]]
    for m in mains:
        if not os.path.isdir(os.path.join(root, m["path"])):
            return f"main category '{m['key']}': directory not found at {os.path.join(root, m['path'])}"
    for s in subs:
        exists_under_any = any(
            os.path.isdir(os.path.join(root, mp, s["path"])) for mp in main_paths
        )
        if not exists_under_any:
            return (f"sub category '{s['key']}': directory '{s['path']}' not found "
                    f"under any main category folder")
    return None


@api.route("/manga-viewer/settings")
class SettingsResource(Resource):
    def get(self):
        """Get all settings."""
        return jsonify(settings_manager.get_settings())

    def put(self):
        """Update settings."""
        updates = request.json or {}
        if not isinstance(updates, dict):
            return {"error": "invalid payload"}, 400

        err = _validate_categories(updates)
        if err:
            return {"error": err}, 400

        settings_manager.update_settings(updates)
        return jsonify(settings_manager.get_settings())

restx_api.add_namespace(api)
