from flask_restx import Namespace, Resource, fields
from flask import request
from . import service as svc

ns = Namespace('', description='Dedup Folder')

# --- Cross-Dir ---
_cross_preview_req = ns.model('CrossPreviewReq', {
    'source_path': fields.String(required=True),
    'duplicate_path': fields.String(required=True),
})
_cross_apply_req = ns.model('CrossApplyReq', {
    'source_path': fields.String(required=True),
    'duplicate_path': fields.String(required=True),
    'trash_path': fields.String(required=True),
})

@ns.route('/cross-dir/preview')
class CrossDirPreview(Resource):
    @ns.expect(_cross_preview_req)
    def post(self):
        b = request.get_json()
        return svc.cross_dir_preview(b['source_path'], b['duplicate_path']), 200

@ns.route('/cross-dir/apply')
class CrossDirApply(Resource):
    @ns.expect(_cross_apply_req)
    def post(self):
        b = request.get_json()
        return svc.cross_dir_apply(b['source_path'], b['duplicate_path'], b['trash_path']), 200


# --- Name Pattern ---
_name_preview_req = ns.model('NamePreviewReq', {
    'source_path': fields.String(required=True),
})
_name_apply_req = ns.model('NameApplyReq', {
    'source_path': fields.String(required=True),
    'trash_path': fields.String(required=True),
})

@ns.route('/name-pattern/preview')
class NamePatternPreview(Resource):
    @ns.expect(_name_preview_req)
    def post(self):
        b = request.get_json()
        return svc.name_pattern_preview(b['source_path']), 200

@ns.route('/name-pattern/apply')
class NamePatternApply(Resource):
    @ns.expect(_name_apply_req)
    def post(self):
        b = request.get_json()
        return svc.name_pattern_apply(b['source_path'], b['trash_path']), 200


# --- macOS File Dedup ---
_macos_preview_req = ns.model('MacosPreviewReq', {
    'source_path': fields.String(required=True),
})
_macos_apply_req = ns.model('MacosApplyReq', {
    'source_path': fields.String(required=True),
    'trash_path': fields.String(required=False),
    'delete_directly': fields.Boolean(required=False, default=False),
})

@ns.route('/macos-file/preview')
class MacosFilePreview(Resource):
    @ns.expect(_macos_preview_req)
    def post(self):
        b = request.get_json()
        return svc.macos_file_preview(b['source_path']), 200

@ns.route('/macos-file/apply')
class MacosFileApply(Resource):
    @ns.expect(_macos_apply_req)
    def post(self):
        b = request.get_json()
        return svc.macos_file_apply(
            source_path=b['source_path'],
            trash_path=b.get('trash_path') or None,
            delete_directly=bool(b.get('delete_directly', False)),
        ), 200
