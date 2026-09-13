"""File Tracker — REST controller.

Route ordering: literal-path sub-routes (bulk-status, bulk-delete, prune)
must be defined before the parametric route /files/<int:fid> so Flask does
not try to parse "bulk-status" etc. as integer IDs.
"""
import traceback

from flask import request
from flask_restx import Namespace, Resource

from .service import get_service
from . import repository, settings_manager

ns = Namespace('')


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------

@ns.route('/scan')
class ScanResource(Resource):
    def post(self):
        started = get_service().start_scan()
        if not started:
            return {'message': 'Scan already running'}, 409
        return {'message': 'Scan started'}, 202


@ns.route('/scan/status')
class ScanStatusResource(Resource):
    def get(self):
        return get_service().get_status(), 200


# ---------------------------------------------------------------------------
# Files — bulk operations first (must precede /<int:fid>)
# ---------------------------------------------------------------------------

@ns.route('/files/bulk-status')
class BulkStatusResource(Resource):
    def post(self):
        data = request.get_json(force=True) or {}
        ids = [int(i) for i in (data.get('ids') or [])]
        status = (data.get('status') or '').strip()
        if not ids or not status:
            return {'error': 'ids and status are required'}, 400
        repository.bulk_update_status(ids, status)
        return {'updated': len(ids)}, 200


@ns.route('/files/bulk-delete')
class BulkDeleteResource(Resource):
    def post(self):
        data = request.get_json(force=True) or {}
        ids = [int(i) for i in (data.get('ids') or [])]
        errors = []
        deleted = 0
        for fid in ids:
            try:
                get_service().trash_file(fid)
                deleted += 1
            except Exception as e:
                errors.append({'id': fid, 'error': str(e)})
        return {'deleted': deleted, 'errors': errors}, 200


@ns.route('/files/prune')
class PruneResource(Resource):
    def post(self):
        try:
            removed = repository.prune_missing()
            return {'removed': removed}, 200
        except Exception as e:
            traceback.print_exc()
            return {'error': str(e)}, 500


# ---------------------------------------------------------------------------
# Files — collection + single item
# ---------------------------------------------------------------------------

@ns.route('/files')
class FilesResource(Resource):
    def get(self):
        args = request.args
        try:
            files, total = repository.get_files(
                status=args.get('status', 'all'),
                min_age_days=float(args['min_age_days']) if 'min_age_days' in args else None,
                max_age_days=float(args['max_age_days']) if 'max_age_days' in args else None,
                sort=args.get('sort', 'last_active'),
                order=args.get('order', 'asc'),
                page=int(args.get('page', 1)),
                per_page=int(args.get('per_page', 200)),
                q=args.get('q') or None,
            )
            return {'files': [f.to_dict() for f in files], 'total': total}, 200
        except Exception as e:
            traceback.print_exc()
            return {'error': str(e)}, 500


@ns.route('/files/stats')
class StatsResource(Resource):
    def get(self):
        return repository.get_stats(), 200


@ns.route('/files/<int:fid>')
class FileResource(Resource):
    def patch(self, fid):
        data = request.get_json(force=True) or {}
        repository.update_file_status(
            fid,
            status=data.get('status'),
            note=data.get('note'),
        )
        f = repository.get_file(fid)
        return {'file': f.to_dict() if f else None}, 200

    def delete(self, fid):
        try:
            get_service().trash_file(fid)
            return {'message': 'Moved to Trash'}, 200
        except (ValueError, FileNotFoundError) as e:
            return {'error': str(e)}, 404
        except Exception as e:
            traceback.print_exc()
            return {'error': str(e)}, 500


@ns.route('/files/<int:fid>/reveal')
class FileRevealResource(Resource):
    def post(self, fid):
        try:
            get_service().reveal_file(fid)
            return {'message': 'Opened in Finder'}, 200
        except ValueError as e:
            return {'error': str(e)}, 404
        except Exception as e:
            traceback.print_exc()
            return {'error': str(e)}, 500


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@ns.route('/settings')
class SettingsResource(Resource):
    def get(self):
        return {'settings': settings_manager.load_settings()}, 200

    def put(self):
        data = request.get_json(force=True) or {}
        s = settings_manager.load_settings()
        s.update(data)
        settings_manager.save_settings(s)
        return {'settings': s}, 200
