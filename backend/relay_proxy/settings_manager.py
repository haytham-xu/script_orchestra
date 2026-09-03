"""Settings manager for relay proxy runtime configuration."""
from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict, List

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), 'settings.json')

DEFAULT_SETTINGS: Dict[str, Any] = {
    'mode': 'direct',
    'listeners': {
        'http': {
            'enabled': False,
            'bind_host': '',
            'bind_port': None,
        },
        'socks5': {
            'enabled': False,
            'bind_host': '',
            'bind_port': None,
        },
    },
    'upstream': {
        'protocol': 'http',
        'host': '',
        'port': None,
    },
    'access': {
        'allowed_client_cidrs': [],
    },
    'limits': {
        'max_connections': 256,
        'connect_timeout_seconds': 15,
        'idle_timeout_seconds': 300,
        'max_header_bytes': 65536,
        'history_limit': 2000,
    },
}


class SettingsError(ValueError):
    """Raised when settings are invalid."""


def _ensure_dict(value: Any, field: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise SettingsError(f'{field} must be an object')
    return value


def _to_bool(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    raise SettingsError(f'{field} must be a boolean')


def _normalize_host(value: Any, field: str, required: bool) -> str:
    host = str(value or '').strip()
    if required and not host:
        raise SettingsError(f'{field} is required')
    return host


def _normalize_port(value: Any, field: str, required: bool) -> int | None:
    if value is None or value == '':
        if required:
            raise SettingsError(f'{field} is required')
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise SettingsError(f'{field} must be an integer') from exc
    if parsed < 1 or parsed > 65535:
        raise SettingsError(f'{field} must be between 1 and 65535')
    return parsed


def _normalize_positive_int(value: Any, field: str, minimum: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise SettingsError(f'{field} must be an integer') from exc
    if parsed < minimum:
        raise SettingsError(f'{field} must be >= {minimum}')
    return parsed


def _deep_merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _normalize_allowed_cidrs(value: Any) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise SettingsError('access.allowed_client_cidrs must be an array')
    result: List[str] = []
    for item in value:
        cidr = str(item or '').strip()
        if not cidr:
            continue
        result.append(cidr)
    return result


def validate_and_normalize(patch: Dict[str, Any], current: Dict[str, Any] | None = None) -> Dict[str, Any]:
    base = copy.deepcopy(DEFAULT_SETTINGS if current is None else current)
    merged = _deep_merge(base, patch or {})

    mode = str(merged.get('mode') or '').strip()
    if mode not in ('upstream_proxy', 'direct'):
        raise SettingsError('mode must be one of: upstream_proxy, direct')

    listeners = _ensure_dict(merged.get('listeners'), 'listeners')
    http_listener = _ensure_dict(listeners.get('http'), 'listeners.http')
    socks_listener = _ensure_dict(listeners.get('socks5'), 'listeners.socks5')

    http_enabled = _to_bool(http_listener.get('enabled'), 'listeners.http.enabled')
    socks_enabled = _to_bool(socks_listener.get('enabled'), 'listeners.socks5.enabled')

    if not http_enabled and not socks_enabled:
        # Saving disabled listeners is allowed; start() decides whether runtime can start.
        pass

    normalized_http = {
        'enabled': http_enabled,
        'bind_host': _normalize_host(http_listener.get('bind_host'), 'listeners.http.bind_host', required=http_enabled),
        'bind_port': _normalize_port(http_listener.get('bind_port'), 'listeners.http.bind_port', required=http_enabled),
    }
    normalized_socks = {
        'enabled': socks_enabled,
        'bind_host': _normalize_host(socks_listener.get('bind_host'), 'listeners.socks5.bind_host', required=socks_enabled),
        'bind_port': _normalize_port(socks_listener.get('bind_port'), 'listeners.socks5.bind_port', required=socks_enabled),
    }

    upstream = _ensure_dict(merged.get('upstream'), 'upstream')
    upstream_protocol = str(upstream.get('protocol') or '').strip()
    if upstream_protocol not in ('http', 'socks5'):
        raise SettingsError('upstream.protocol must be one of: http, socks5')

    upstream_required = mode == 'upstream_proxy' and (http_enabled or socks_enabled)
    normalized_upstream = {
        'protocol': upstream_protocol,
        'host': _normalize_host(upstream.get('host'), 'upstream.host', required=upstream_required),
        'port': _normalize_port(upstream.get('port'), 'upstream.port', required=upstream_required),
    }

    access = _ensure_dict(merged.get('access'), 'access')
    normalized_access = {
        'allowed_client_cidrs': _normalize_allowed_cidrs(access.get('allowed_client_cidrs')),
    }

    limits = _ensure_dict(merged.get('limits'), 'limits')
    normalized_limits = {
        'max_connections': _normalize_positive_int(limits.get('max_connections'), 'limits.max_connections', minimum=1),
        'connect_timeout_seconds': _normalize_positive_int(
            limits.get('connect_timeout_seconds'),
            'limits.connect_timeout_seconds',
            minimum=1,
        ),
        'idle_timeout_seconds': _normalize_positive_int(
            limits.get('idle_timeout_seconds'),
            'limits.idle_timeout_seconds',
            minimum=1,
        ),
        'max_header_bytes': _normalize_positive_int(limits.get('max_header_bytes'), 'limits.max_header_bytes', minimum=1024),
        'history_limit': _normalize_positive_int(limits.get('history_limit'), 'limits.history_limit', minimum=100),
    }

    return {
        'mode': mode,
        'listeners': {
            'http': normalized_http,
            'socks5': normalized_socks,
        },
        'upstream': normalized_upstream,
        'access': normalized_access,
        'limits': normalized_limits,
    }


def save_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    normalized = validate_and_normalize(settings)
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(normalized, f, ensure_ascii=True, indent=2)
        f.write('\n')
    return normalized


def ensure_settings_file() -> None:
    if os.path.exists(SETTINGS_FILE):
        return
    save_settings(DEFAULT_SETTINGS)


def load_settings() -> Dict[str, Any]:
    ensure_settings_file()
    with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f) or {}
    normalized = validate_and_normalize(data)
    if normalized != data:
        save_settings(normalized)
    return normalized
