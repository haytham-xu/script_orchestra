"""REST API controller for Relay Proxy."""
from __future__ import annotations

from flask import request
from flask_restx import Namespace, Resource

from .service import get_service
from .settings_manager import SettingsError

ns = Namespace('')


@ns.route('/status')
class StatusResource(Resource):
    def get(self):
        """Return relay runtime status."""
        try:
            return get_service().get_status(), 200
        except SettingsError as exc:
            return {'error': str(exc)}, 400


@ns.route('/start')
class StartResource(Resource):
    def post(self):
        """Start relay listeners using saved settings."""
        try:
            return get_service().start(), 200
        except (SettingsError, RuntimeError) as exc:
            return {'error': str(exc)}, 409


@ns.route('/stop')
class StopResource(Resource):
    def post(self):
        """Stop relay listeners."""
        try:
            return get_service().stop(), 200
        except SettingsError as exc:
            return {'error': str(exc)}, 400


@ns.route('/settings')
class SettingsResource(Resource):
    def get(self):
        """Get current relay settings."""
        try:
            return get_service().get_settings(), 200
        except SettingsError as exc:
            return {'error': str(exc)}, 400

    def put(self):
        """Update relay settings using partial patch semantics."""
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return {'error': 'Request body must be a JSON object'}, 400
        try:
            return get_service().update_settings(payload), 200
        except SettingsError as exc:
            return {'error': str(exc)}, 400


@ns.route('/history')
class HistoryResource(Resource):
    def get(self):
        """Get relay history entries."""
        limit = request.args.get('limit', default=200, type=int)
        if limit < 1 or limit > 2000:
            return {'error': 'limit must be between 1 and 2000'}, 400
        try:
            return get_service().get_history(limit=limit), 200
        except SettingsError as exc:
            return {'error': str(exc)}, 400

    def delete(self):
        """Clear relay history entries."""
        try:
            cleared = get_service().clear_history()
            return {'cleared': cleared, 'message': 'History cleared'}, 200
        except SettingsError as exc:
            return {'error': str(exc)}, 400


@ns.route('/diagnostics/probe')
class DiagnosticsProbeResource(Resource):
    def post(self):
        """Run read-only diagnostics against effective settings.

        Optional JSON body is treated as a partial settings patch for this probe
        only and is not persisted.
        """
        payload = request.get_json(silent=True)
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            return {'error': 'Request body must be a JSON object'}, 400

        try:
            return get_service().run_diagnostics_probe(payload), 200
        except SettingsError as exc:
            return {'error': str(exc)}, 400
