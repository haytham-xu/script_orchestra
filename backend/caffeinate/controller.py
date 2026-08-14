"""
Caffeinate Controller

REST API endpoints for the caffeinate tool.
"""
from flask import request
from flask_restx import Namespace, Resource, fields

from .service import get_service

ns = Namespace("caffeinate", description="Caffeinate control operations")

start_input_model = ns.model('CaffeinateStartInput', {
    'interval_seconds': fields.Integer(
        required=False,
        description='Heartbeat log interval in seconds',
        default=300,
    ),
})

status_model = ns.model('CaffeinateStatus', {
    'running': fields.Boolean(description='Whether caffeinate is currently running'),
    'interval_seconds': fields.Integer(description='Configured heartbeat interval'),
    'started_at': fields.String(description='ISO timestamp when it started'),
    'pid': fields.Integer(description='OS pid of the caffeinate process'),
    'log_count': fields.Integer(description='Number of buffered log entries'),
})

log_entry_model = ns.model('CaffeinateLogEntry', {
    'id': fields.Integer(description='Log id'),
    'timestamp': fields.String(description='ISO timestamp'),
    'message': fields.String(description='Log message'),
})


@ns.route('/status')
class CaffeinateStatusResource(Resource):
    @ns.marshal_with(status_model)
    def get(self):
        """Return current caffeinate process status."""
        return get_service().get_status()


@ns.route('/start')
class CaffeinateStartResource(Resource):
    @ns.expect(start_input_model)
    @ns.marshal_with(status_model)
    def post(self):
        """Start caffeinate with an optional heartbeat interval."""
        data = request.get_json(silent=True) or {}
        interval = int(data.get('interval_seconds', 300))
        service = get_service()
        try:
            service.start(interval_seconds=interval)
        except ValueError as exc:
            ns.abort(400, str(exc))
        except RuntimeError as exc:
            ns.abort(409, str(exc))
        except FileNotFoundError:
            ns.abort(500, "`caffeinate` command not found (macOS only)")
        return service.get_status()


@ns.route('/stop')
class CaffeinateStopResource(Resource):
    @ns.marshal_with(status_model)
    def post(self):
        """Stop the running caffeinate process."""
        service = get_service()
        try:
            service.stop()
        except RuntimeError as exc:
            ns.abort(409, str(exc))
        return service.get_status()


@ns.route('/logs')
class CaffeinateLogsResource(Resource):
    @ns.marshal_list_with(log_entry_model)
    def get(self):
        """Return the buffered heartbeat log entries."""
        limit = request.args.get('limit', default=500, type=int)
        if limit < 1 or limit > 500:
            ns.abort(400, "limit must be between 1 and 500")
        return get_service().get_logs(limit)

    def delete(self):
        """Clear buffered log entries."""
        count = get_service().clear_logs()
        return {"message": f"Cleared {count} log entries", "count": count}, 200
