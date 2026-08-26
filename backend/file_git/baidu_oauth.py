"""
File-Git — Baidu OAuth 2.0 flow.

Automates everything except the user's explicit "authorize" click:
- build_auth_url(): the URL the UI opens
- exchange_code(code): swap an auth code for tokens and persist them
- refresh_if_needed(): refresh the access_token before it expires
- get_valid_token(): return a currently-valid access_token (refreshing first)

Tokens are stored in the baidu_cloud settings block. app_key / secret_key
are read from settings (migrated from the user's existing app).
"""
import time
import json
import urllib.parse
import urllib.request

from .settings_manager import SettingsManager

AUTHORIZE_URL = "https://openapi.baidu.com/oauth/2.0/authorize"
TOKEN_URL = "https://openapi.baidu.com/oauth/2.0/token"
REDIRECT_URI = "http://localhost:50001/file-git/baidu/callback"
SCOPE = "basic,netdisk"

# Refresh this many seconds before actual expiry to avoid mid-request expiry.
REFRESH_BUFFER = 6 * 3600


def _http_get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "pan.baidu.com"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def build_auth_url() -> str:
    creds = SettingsManager.get_baidu_credentials()
    app_key = creds.get("app_key", "")
    if not app_key:
        raise ValueError("Baidu app_key is not configured")
    params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": app_key,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
    })
    return f"{AUTHORIZE_URL}?{params}"


def exchange_code(code: str) -> dict:
    """Swap an authorization code for tokens and persist them."""
    creds = SettingsManager.get_baidu_credentials()
    params = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "client_id": creds.get("app_key", ""),
        "client_secret": creds.get("secret_key", ""),
        "redirect_uri": REDIRECT_URI,
    })
    data = _http_get_json(f"{TOKEN_URL}?{params}")
    if "access_token" not in data:
        raise RuntimeError(f"Baidu token exchange failed: {data}")
    _persist_tokens(data)
    return data


def refresh_if_needed(force: bool = False) -> str:
    """Refresh the access_token if it is missing or near expiry. Returns the token."""
    creds = SettingsManager.get_baidu_credentials()
    access_token = creds.get("access_token", "")
    acquired_at = float(creds.get("token_acquired_at") or 0)
    expires_in = float(creds.get("expires_in") or 0)
    still_valid = (
        access_token
        and acquired_at
        and expires_in
        and time.time() < acquired_at + expires_in - REFRESH_BUFFER
    )
    if still_valid and not force:
        return access_token

    refresh_token = creds.get("refresh_token", "")
    if not refresh_token:
        raise RuntimeError("No refresh_token — connect Baidu first")
    params = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": creds.get("app_key", ""),
        "client_secret": creds.get("secret_key", ""),
    })
    data = _http_get_json(f"{TOKEN_URL}?{params}")
    if "access_token" not in data:
        raise RuntimeError(f"Baidu token refresh failed: {data}")
    _persist_tokens(data)
    return data["access_token"]


def get_valid_token() -> str:
    """Return a currently-valid access_token, refreshing first if needed."""
    return refresh_if_needed(force=False)


def get_status() -> dict:
    """Report connection status for the UI (no secrets)."""
    creds = SettingsManager.get_baidu_credentials()
    access_token = creds.get("access_token", "")
    if not access_token:
        return {"connected": False}
    acquired_at = float(creds.get("token_acquired_at") or 0)
    expires_in = float(creds.get("expires_in") or 0)
    expires_at = acquired_at + expires_in if acquired_at and expires_in else 0
    result = {"connected": True, "expires_at": expires_at}
    # Best-effort account name (won't fail the status call if the API is down).
    try:
        info = _http_get_json(
            "https://pan.baidu.com/rest/2.0/xpan/nas?" + urllib.parse.urlencode(
                {"method": "uinfo", "access_token": access_token}))
        if info.get("errno") == 0:
            result["baidu_name"] = info.get("baidu_name", "")
    except Exception:
        pass
    return result


def _persist_tokens(data: dict) -> None:
    SettingsManager.update_baidu_credentials({
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", ""),
        "expires_in": data.get("expires_in", ""),
        "token_acquired_at": time.time(),
    })
