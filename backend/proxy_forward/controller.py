"""REST API for Proxy Forward."""
from flask import request
from flask_restx import Namespace, Resource, fields

from .service import (
    get_service,
)
from . import settings_manager

ns = Namespace('')

start_input_model = ns.model('ProxyForwardStartInput', {
    'listen_host': fields.String(required=False),
    'listen_port': fields.Integer(required=False),
    'target_host': fields.String(required=False),
    'target_port': fields.Integer(required=False),
})

status_model = ns.model('ProxyForwardStatus', {
    'running': fields.Boolean(),
    'listen_host': fields.String(),
    'listen_port': fields.Integer(),
    'target_host': fields.String(),
    'target_port': fields.Integer(),
    'started_at': fields.String(),
    'active_connections': fields.Integer(),
    'total_connections': fields.Integer(),
    'lan_ip': fields.String(),
    'lan_ips': fields.List(fields.String()),
    'last_error': fields.String(),
    'history_count': fields.Integer(),
})

history_entry_model = ns.model('ProxyForwardHistoryEntry', {
    'id': fields.Integer(),
    'timestamp': fields.String(),
    'level': fields.String(),
    'event': fields.String(),
    'message': fields.String(),
})

settings_model = ns.model('ProxyForwardSettings', {
    'listen_host': fields.String(required=True),
    'listen_port': fields.Integer(required=True),
    'target_host': fields.String(required=True),
    'target_port': fields.Integer(required=True),
})


@ns.route('/status')
class StatusResource(Resource):
    @ns.marshal_with(status_model)
    def get(self):
        """Get runtime status and current LAN IPs."""
        return get_service().get_status()


@ns.route('/network')
class NetworkResource(Resource):
    @ns.marshal_with(status_model)
    def get(self):
        """Alias of status for polling network info from UI."""
        return get_service().get_status()


@ns.route('/start')
class StartResource(Resource):
    @ns.expect(start_input_model)
    @ns.marshal_with(status_model)
    def post(self):
        """Start forwarding traffic from listen endpoint to target endpoint."""
        data = request.get_json(silent=True) or {}
        try:
            return get_service().start(
                listen_host=data.get('listen_host'),
                listen_port=data.get('listen_port'),
                target_host=data.get('target_host'),
                target_port=data.get('target_port'),
            )
        except ValueError as exc:
            ns.abort(400, str(exc))
        except RuntimeError as exc:
            ns.abort(409, str(exc))


@ns.route('/stop')
class StopResource(Resource):
    @ns.marshal_with(status_model)
    def post(self):
        """Stop the running forward server."""
        return get_service().stop()


@ns.route('/history')
class HistoryResource(Resource):
    @ns.marshal_list_with(history_entry_model)
    def get(self):
        """Get forward history entries, newest order preserved."""
        limit = request.args.get('limit', default=200, type=int)
        if limit < 1 or limit > 2000:
            ns.abort(400, 'limit must be between 1 and 2000')
        return get_service().get_history(limit=limit)

    def delete(self):
        """Clear forward history entries."""
        cleared = get_service().clear_history()
        return {'cleared': cleared, 'message': 'History cleared'}, 200


@ns.route('/settings')
class SettingsResource(Resource):
    @ns.marshal_with(settings_model)
    def get(self):
        """Get persisted proxy forward configuration."""
        return settings_manager.load_settings()

    @ns.expect(settings_model)
    @ns.marshal_with(settings_model)
    def put(self):
        """Update persisted proxy forward configuration."""
        data = request.get_json(silent=True) or {}
        current = settings_manager.load_settings()
        merged = {
            'listen_host': data.get('listen_host', current.get('listen_host')),
            'listen_port': data.get('listen_port', current.get('listen_port')),
            'target_host': data.get('target_host', current.get('target_host')),
            'target_port': data.get('target_port', current.get('target_port')),
        }
        try:
            return settings_manager.save_settings(merged)
        except ValueError as exc:
            ns.abort(400, str(exc))
