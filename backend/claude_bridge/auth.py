"""Claude Bridge — bearer-token auth.

A single shared token gates every HTTP endpoint and the WebSocket handshake. The
token comes from config.BRIDGE_TOKEN (env CLAUDE_BRIDGE_TOKEN). When it is empty
(the default), auth is DISABLED — convenient for LAN development, but the token
MUST be set before exposing the bridge to the internet (Phase 5).

This is intentionally simple (one token, self-use). It is a second factor behind
Cloudflare Access, not the only line of defense.
"""
import hmac
from functools import wraps

from flask import request

from . import config


def auth_enabled() -> bool:
    return bool(config.BRIDGE_TOKEN)


def _token_ok(provided: str) -> bool:
    if not auth_enabled():
        return True  # LAN dev: no token configured => allow
    if not provided:
        return False
    return hmac.compare_digest(provided, config.BRIDGE_TOKEN)


def _bearer_from_headers() -> str:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[len("Bearer "):].strip()
    return ""


def require_token(fn):
    """Flask/RESTX method decorator: 401 unless a valid bearer token is present."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not _token_ok(_bearer_from_headers()):
            return {"error": "unauthorized"}, 401
        return fn(*args, **kwargs)
    return wrapper


def check_ws_auth(auth) -> bool:
    """Validate a Socket.IO handshake. `auth` is the client's io(..., {auth}) dict.
    Returns False to reject the connection."""
    if not auth_enabled():
        return True
    token = ""
    if isinstance(auth, dict):
        token = (auth.get("token") or "").strip()
    return _token_ok(token)
