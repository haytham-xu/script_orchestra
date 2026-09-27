"""
File Duplicate — REST controller
"""
import threading

from flask_restx import Namespace, Resource
from flask import request, jsonify

from . import repository as repo
from . import settings_manager as sm
from .service import get_service

ns = Namespace('file-duplicate', description='Exact-match duplicate file finder')


def _svc():
    return get_service()


# ── Settings ──────────────────────────────────────────────────────────────────

@ns.route('/settings')
class Settings(Resource):
    def get(self):
        return sm.load()

    def post(self):
        data = request.get_json(force=True) or {}
        current = sm.load()
        current.update(data)
        sm.save(current)
        return {'ok': True}


# ── Status ────────────────────────────────────────────────────────────────────

@ns.route('/status')
class Status(Resource):
    def get(self):
        svc = _svc()
        status = svc.get_status()
        status['counts'] = repo.count_pending()
        status['total_files'] = repo.get_total_file_count()
        return status


# ── Phase 1: Index ────────────────────────────────────────────────────────────

@ns.route('/phase1/index')
class Phase1Index(Resource):
    def post(self):
        svc = _svc()
        try:
            op_id = svc._claim_op('phase1')
        except RuntimeError as e:
            return {'error': str(e)}, 409
        t = threading.Thread(target=svc.run_phase1_index, args=(op_id,), daemon=True)
        t.start()
        return {'ok': True, 'message': 'Phase 1 index started'}


@ns.route('/phase1/stop')
class Phase1Stop(Resource):
    def post(self):
        _svc().stop()
        return {'ok': True}


# ── Phase 2: Hash ─────────────────────────────────────────────────────────────

@ns.route('/phase2/hash')
class Phase2Hash(Resource):
    def post(self):
        svc = _svc()
        try:
            op_id = svc._claim_op('phase2')
        except RuntimeError as e:
            return {'error': str(e)}, 409
        t = threading.Thread(target=svc.run_phase2_hash, args=(op_id,), daemon=True)
        t.start()
        return {'ok': True, 'message': 'Phase 2 hash started'}


@ns.route('/phase2/stop')
class Phase2Stop(Resource):
    def post(self):
        _svc().stop()
        return {'ok': True}


# ── Phase 3: Group ────────────────────────────────────────────────────────────

@ns.route('/phase3/group')
class Phase3Group(Resource):
    def post(self):
        svc = _svc()
        try:
            op_id = svc._claim_op('phase3')
        except RuntimeError as e:
            return {'error': str(e)}, 409
        t = threading.Thread(target=svc.run_phase3_group, args=(op_id,), daemon=True)
        t.start()
        return {'ok': True, 'message': 'Phase 3 group started'}


# ── Results ───────────────────────────────────────────────────────────────────

@ns.route('/groups')
class Groups(Resource):
    def get(self):
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', sm.get_page_size()))
        sort_by = request.args.get('sort_by', 'filesize')
        sort_order = request.args.get('sort_order', 'desc')
        root_filter = request.args.get('root_id')
        if root_filter is not None:
            root_filter = int(root_filter)
        groups, total = repo.get_groups_page(page, page_size, sort_by, sort_order, root_filter)
        stats = repo.get_group_stats()
        return {
            'groups': groups,
            'total_groups': total,
            'page': page,
            'page_size': page_size,
            'total_pages': max(1, (total + page_size - 1) // page_size),
            **stats,
        }


@ns.route('/stats')
class Stats(Resource):
    def get(self):
        return {
            'group_stats': repo.get_group_stats(),
            'root_stats': repo.get_root_stats(),
            'root_dup_stats': repo.get_root_duplicate_stats(),
            'counts': repo.count_pending(),
            'total_files': repo.get_total_file_count(),
        }


# ── File operations ───────────────────────────────────────────────────────────

@ns.route('/move-to-trash')
class MoveToTrash(Resource):
    def post(self):
        data = request.get_json(force=True) or {}
        file_ids = data.get('file_ids', [])
        if not file_ids:
            return {'error': 'file_ids required'}, 400
        try:
            result = _svc().move_to_trash(file_ids)
            return result
        except ValueError as e:
            return {'error': str(e)}, 400


@ns.route('/resolve-group')
class ResolveGroup(Resource):
    """Keep specified file_ids, trash the rest in a group."""
    def post(self):
        data = request.get_json(force=True) or {}
        trash_ids = data.get('trash_ids', [])
        if not trash_ids:
            return {'error': 'trash_ids required'}, 400
        try:
            result = _svc().move_to_trash(trash_ids)
            return result
        except ValueError as e:
            return {'error': str(e)}, 400
