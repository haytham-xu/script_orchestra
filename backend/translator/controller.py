"""Translator — REST controller (blueprint prefix /translator).

Two decoupled scenes (zh2en, en2zh) each with their own endpoint, plus shared
history / cleanup / models / settings endpoints. Copilot auth or runtime
failures surface as 502 with a readable hint.
"""
from flask_restx import Namespace, Resource
from flask import request

from . import zh2en, en2zh, repository, settings_manager, copilot_client
from .copilot_client import CopilotAuthError, CopilotUnavailableError

ns = Namespace("")


def _copilot_error_response(e: Exception):
    """Map a copilot_client error onto (body, status)."""
    if isinstance(e, CopilotAuthError):
        return {"error": str(e), "kind": "auth"}, 502
    if isinstance(e, CopilotUnavailableError):
        return {"error": str(e), "kind": "unavailable"}, 502
    return {"error": f"Copilot call failed: {e}", "kind": "error"}, 502


@ns.route("/zh2en")
class Zh2EnResource(Resource):
    def post(self):
        data = request.json or {}
        text = (data.get("text") or "").strip()
        if not text:
            return {"error": "text is required"}, 400
        model = (data.get("model") or "").strip() or None
        job_id = (data.get("job_id") or "").strip() or None
        extra_prompt = (data.get("extra_prompt") or "").strip() or None
        try:
            return zh2en.translate(text, model=model, job_id=job_id, extra_prompt=extra_prompt), 200
        except ValueError as e:
            return {"error": str(e)}, 400
        except Exception as e:  # noqa: BLE001
            return _copilot_error_response(e)


@ns.route("/en2zh")
class En2ZhResource(Resource):
    def post(self):
        data = request.json or {}
        text = (data.get("text") or "").strip()
        if not text:
            return {"error": "text is required"}, 400
        model = (data.get("model") or "").strip() or None
        job_id = (data.get("job_id") or "").strip() or None
        extra_prompt = (data.get("extra_prompt") or "").strip() or None
        try:
            return en2zh.translate(text, model=model, job_id=job_id, extra_prompt=extra_prompt), 200
        except ValueError as e:
            return {"error": str(e)}, 400
        except Exception as e:  # noqa: BLE001
            return _copilot_error_response(e)


@ns.route("/history")
class HistoryResource(Resource):
    def get(self):
        """List translation history, newest first. Optional ?scene=zh2en|en2zh."""
        scene = request.args.get("scene") or None
        if scene and scene not in ("zh2en", "en2zh"):
            return {"error": "scene must be zh2en or en2zh"}, 400
        try:
            limit = int(request.args.get("limit", 100))
        except (TypeError, ValueError):
            limit = 100
        hist = repository.get_history(scene=scene, limit=limit)
        return {"history": [h.to_dict() for h in hist]}, 200

    def delete(self):
        """One-click cleanup: delete ALL history (both scenes) older than N days.
        ?days=N; falls back to settings.cleanup_days when omitted."""
        days_arg = request.args.get("days")
        if days_arg is not None:
            try:
                days = int(days_arg)
            except (TypeError, ValueError):
                return {"error": "days must be an integer"}, 400
        else:
            days = settings_manager.load_settings().get("cleanup_days", 30)
        if days < 0:
            return {"error": "days must be >= 0"}, 400
        deleted = repository.cleanup_older_than(days)
        return {"deleted": deleted, "days": days}, 200


@ns.route("/models")
class ModelsResource(Resource):
    def get(self):
        """List models the Copilot runtime exposes. [] on soft failure."""
        return {"models": copilot_client.list_models()}, 200


@ns.route("/usage/summary")
class UsageSummaryResource(Resource):
    def get(self):
        """Cumulative usage across history. Optional ?scene=zh2en|en2zh."""
        scene = request.args.get("scene") or None
        if scene and scene not in ("zh2en", "en2zh"):
            return {"error": "scene must be zh2en or en2zh"}, 400
        return repository.usage_summary(scene=scene), 200


@ns.route("/settings")
class SettingsResource(Resource):
    def get(self):
        return settings_manager.load_settings(), 200

    def put(self):
        patch = request.json or {}
        current = settings_manager.load_settings()
        try:
            merged = settings_manager.validate_and_normalize(patch, current)
        except ValueError as e:
            return {"error": str(e)}, 400
        settings_manager.save_settings(merged)
        return merged, 200
