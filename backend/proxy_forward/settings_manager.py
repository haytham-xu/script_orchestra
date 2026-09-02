"""Settings manager for proxy forward runtime configuration."""
from __future__ import annotations

import json
import os
from typing import Any, Dict

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), 'settings.json')


def _normalize_port(value: Any, field: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{field} must be an integer') from exc
    if parsed < 1 or parsed > 65535:
        raise ValueError(f'{field} must be between 1 and 65535')
    return parsed


def _normalize_host(value: Any, field: str) -> str:
    host = str(value or '').strip()
    if not host:
        raise ValueError(f'{field} is required')
    return host


def validate_and_normalize(settings: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'listen_host': _normalize_host(settings.get('listen_host'), 'listen_host'),
        'listen_port': _normalize_port(settings.get('listen_port'), 'listen_port'),
        'target_host': _normalize_host(settings.get('target_host'), 'target_host'),
        'target_port': _normalize_port(settings.get('target_port'), 'target_port'),
    }


def load_settings() -> Dict[str, Any]:
    if not os.path.exists(SETTINGS_FILE):
        raise ValueError('proxy_forward settings.json not found')
    with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f) or {}
    normalized = validate_and_normalize(data)
    if normalized != data:
        save_settings(normalized)
    return normalized


def save_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    normalized = validate_and_normalize(settings)
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(normalized, f, ensure_ascii=True, indent=2)
        f.write('\n')
    return normalized
