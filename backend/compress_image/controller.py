from flask_restx import Namespace, Resource, fields
from flask import request
from . import service as svc

ns = Namespace('', description='Image Compression')

_preview_req = ns.model('PreviewReq', {
    'root_path': fields.String(required=True),
    'target_kb': fields.Float(required=True),
})

_apply_req = ns.model('ApplyReq', {
    'root_path': fields.String(required=True),
    'target_kb': fields.Float(required=True),
    'overwrite': fields.Boolean(required=False, default=False),
    'output_dir': fields.String(required=False),
})


@ns.route('/preview')
class Preview(Resource):
    @ns.expect(_preview_req)
    def post(self):
        body = request.get_json()
        result = svc.preview(body['root_path'], float(body['target_kb']))
        return result, 200


@ns.route('/apply')
class Apply(Resource):
    @ns.expect(_apply_req)
    def post(self):
        body = request.get_json()
        result = svc.apply_compress(
            root_path=body['root_path'],
            target_kb=float(body['target_kb']),
            overwrite=bool(body.get('overwrite', False)),
            output_dir=body.get('output_dir') or None,
        )
        return result, 200
