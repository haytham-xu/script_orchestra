from flask_restx import Namespace, Resource, fields
from flask import request
from . import service

ns = Namespace('', description='Clean Keyword operations')

_kw_model = ns.model('Keyword', {
    'keyword': fields.String(required=True),
})

_import_model = ns.model('ImportText', {
    'text': fields.String(required=True),
})

_apply_model = ns.model('ApplyBody', {
    'root_path': fields.String(required=True),
})


@ns.route('/keywords')
class KeywordsResource(Resource):
    def get(self):
        return {'keywords': service.get_keywords()}, 200

    @ns.expect(_kw_model)
    def post(self):
        kw = (request.json or {}).get('keyword', '').strip()
        if not kw:
            return {'error': 'keyword required'}, 400
        ok = service.add_keyword(kw)
        if not ok:
            return {'error': 'duplicate'}, 409
        return {'keywords': service.get_keywords()}, 201


@ns.route('/keywords/<string:kw>')
class KeywordResource(Resource):
    def delete(self, kw):
        service.delete_keyword(kw)
        return '', 204


@ns.route('/keywords/import')
class KeywordsImportResource(Resource):
    @ns.expect(_import_model)
    def post(self):
        text = (request.json or {}).get('text', '')
        added = service.import_keywords(text)
        return {'added': added, 'keywords': service.get_keywords()}, 200


@ns.route('/preview')
class PreviewResource(Resource):
    def get(self):
        root_path = request.args.get('root_path', '').strip()
        if not root_path:
            return {'error': 'root_path required'}, 400
        items = service.preview_clean(root_path)
        return {'items': items, 'total': len(items)}, 200


@ns.route('/apply')
class ApplyResource(Resource):
    @ns.expect(_apply_model)
    def post(self):
        root_path = (request.json or {}).get('root_path', '').strip()
        if not root_path:
            return {'error': 'root_path required'}, 400
        result = service.apply_clean(root_path)
        return result, 200
