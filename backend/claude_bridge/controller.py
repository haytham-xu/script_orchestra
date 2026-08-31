"""Claude Bridge — REST controller (blueprint prefix /claude-bridge).

Session lifecycle over HTTP; the actual conversation streams over WebSocket.
"""
from flask_restx import Namespace, Resource
from flask import request

from . import config
from .auth import require_token, auth_enabled
from .session_manager import get_manager

ns = Namespace("")


@ns.route("/auth/check")
class AuthCheckResource(Resource):
    """Public: tells the client whether a token is required (no token needed)."""
    def get(self):
        return {"auth_required": auth_enabled()}, 200


@ns.route("/config")
class ConfigResource(Resource):
    @require_token
    def get(self):
        return {
            "models": config.MODEL_ALIASES,
            "default_model": config.DEFAULT_MODEL,
            "cwd_roots": config.CWD_ROOTS,
            "default_cwd": config.DEFAULT_CWD,
        }, 200


@ns.route("/sessions")
class SessionsResource(Resource):
    @require_token
    def get(self):
        return {"sessions": get_manager().list_sessions()}, 200

    @require_token
    def post(self):
        data = request.json or {}
        try:
            session = get_manager().create_session(
                cwd=(data.get("cwd") or "").strip() or None,
                model=(data.get("model") or "").strip() or None,
            )
        except ValueError as e:
            return {"error": str(e)}, 400
        return session.to_dict(), 201


@ns.route("/sessions/<string:session_id>")
class SessionResource(Resource):
    @require_token
    def delete(self, session_id):
        if not get_manager().close_session(session_id):
            return {"error": "session not found"}, 404
        return {"message": "closed"}, 200


@ns.route("/pty/sessions")
class PtySessionsResource(Resource):
    @require_token
    def get(self):
        return {"ptys": get_manager().list_ptys()}, 200

    @require_token
    def post(self):
        data = request.json or {}
        try:
            pty = get_manager().create_pty(cwd=(data.get("cwd") or "").strip() or None)
        except ValueError as e:
            return {"error": str(e)}, 400
        return pty.to_dict(), 201


@ns.route("/pty/sessions/<string:pty_id>")
class PtySessionResource(Resource):
    @require_token
    def delete(self, pty_id):
        if not get_manager().close_pty(pty_id):
            return {"error": "pty not found"}, 404
        return {"message": "closed"}, 200
