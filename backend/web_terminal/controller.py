"""Web Terminal — REST controller (Flask-RESTX namespace)."""
import os
from flask import request
from flask_restx import Namespace, Resource, fields

from . import repository as repo
from . import scrollback_store
from .pty_manager import get_manager

ns = Namespace('', description='Web Terminal')

_window_model = ns.model('TerminalWindow', {
    'window_id': fields.String,
    'title': fields.String,
    'cwd': fields.String,
    'created_at': fields.Float,
    'last_active': fields.Float,
})


@ns.route('/windows')
class WindowList(Resource):
    def get(self):
        mgr = get_manager()
        wins = repo.list_windows()
        return {
            'windows': [
                {**w.to_dict(), 'pty_alive': mgr.is_alive(w.window_id)}
                for w in wins
            ]
        }

    def post(self):
        data = request.get_json(force=True) or {}
        title = data.get('title', '').strip() or 'Terminal'
        cwd = data.get('cwd', '').strip() or os.path.expanduser('~')
        if not os.path.isdir(cwd):
            return {'error': f'Directory does not exist: {cwd}'}, 400
        win = repo.create_window(title, cwd)
        return win.to_dict(), 201


@ns.route('/windows/<string:window_id>')
class WindowDetail(Resource):
    def delete(self, window_id):
        win = repo.get_window(window_id)
        if not win:
            return {'error': 'not found'}, 404
        get_manager().detach(window_id)
        repo.delete_window(window_id)
        scrollback_store.delete(window_id)
        return {'ok': True}


@ns.route('/windows/<string:window_id>/scrollback')
class Scrollback(Resource):
    def get(self, window_id):
        if not repo.get_window(window_id):
            return {'error': 'not found'}, 404
        return {'data': scrollback_store.read(window_id)}


@ns.route('/windows/<string:window_id>/pty')
class PtyAttach(Resource):
    def post(self, window_id):
        win = repo.get_window(window_id)
        if not win:
            return {'error': 'not found'}, 404
        mgr = get_manager()
        if mgr.is_alive(window_id):
            return {'ok': True, 'already_running': True}
        mgr.attach(window_id, win.cwd)
        repo.touch_window(window_id)
        return {'ok': True, 'already_running': False}, 201

    def delete(self, window_id):
        get_manager().detach(window_id)
        return {'ok': True}
