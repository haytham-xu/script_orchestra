from flask_restx import Namespace, Resource
from flask import request
from . import repository
from .service import get_service

ns = Namespace('', description='File Pipeline')

# --- Tools ---

@ns.route('/tools')
class ToolList(Resource):
    def get(self):
        return {'tools': [t.to_dict() for t in repository.get_tools()]}, 200

    def post(self):
        b = request.get_json()
        tid = repository.add_tool(b['name'], b['exe_path'], b['args_template'])
        return {'id': tid}, 201


@ns.route('/tools/<int:tool_id>')
class ToolItem(Resource):
    def put(self, tool_id):
        b = request.get_json()
        repository.update_tool(tool_id, b['name'], b['exe_path'], b['args_template'])
        return {'ok': True}, 200

    def delete(self, tool_id):
        repository.delete_tool(tool_id)
        return {}, 204


# --- Pipelines ---

@ns.route('/pipelines')
class PipelineList(Resource):
    def get(self):
        return {'pipelines': [p.to_dict(include_steps=False) for p in repository.get_pipelines()]}, 200

    def post(self):
        b = request.get_json()
        import json
        steps = b.get('steps', '{}')
        if not isinstance(steps, str):
            steps = json.dumps(steps)
        pid = repository.add_pipeline(b['name'], steps)
        return {'id': pid}, 201


@ns.route('/pipelines/<int:pipeline_id>')
class PipelineItem(Resource):
    def get(self, pipeline_id):
        p = repository.get_pipeline(pipeline_id)
        if not p:
            return {'error': 'Not found'}, 404
        return p.to_dict(), 200

    def put(self, pipeline_id):
        b = request.get_json()
        import json
        steps = b.get('steps', '{}')
        if not isinstance(steps, str):
            steps = json.dumps(steps)
        repository.update_pipeline(pipeline_id, b['name'], steps)
        return {'ok': True}, 200

    def delete(self, pipeline_id):
        repository.delete_pipeline(pipeline_id)
        return {}, 204


# --- Run ---

@ns.route('/run')
class RunPipeline(Resource):
    def post(self):
        b = request.get_json()
        try:
            results = get_service().run_pipeline(b['pipeline_id'], b['folder_path'])
            return {'results': results}, 200
        except ValueError as e:
            return {'error': str(e)}, 400
        except Exception as e:
            return {'error': str(e)}, 500
