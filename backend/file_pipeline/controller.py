import json
import threading
import uuid
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
        steps = b.get('steps', '{}')
        if not isinstance(steps, str):
            steps = json.dumps(steps)
        repository.update_pipeline(pipeline_id, b['name'], steps)
        return {'ok': True}, 200

    def delete(self, pipeline_id):
        repository.delete_pipeline(pipeline_id)
        return {}, 204


# --- Run config ---

@ns.route('/pipelines/<int:pipeline_id>/config')
class PipelineConfig(Resource):
    def get(self, pipeline_id):
        return repository.get_run_config(pipeline_id), 200

    def put(self, pipeline_id):
        b = request.get_json()
        repository.save_run_config(pipeline_id, b)
        return {'ok': True}, 200


# --- Passwords ---

@ns.route('/passwords')
class PasswordList(Resource):
    def get(self):
        return {'passwords': [p.to_dict() for p in repository.get_passwords()]}, 200

    def post(self):
        b = request.get_json()
        pid = repository.add_password(b['value'], b.get('note', ''))
        return {'id': pid}, 201


@ns.route('/passwords/<int:pwd_id>')
class PasswordItem(Resource):
    def put(self, pwd_id):
        b = request.get_json()
        repository.update_password(pwd_id, b['value'], b.get('note', ''))
        return {'ok': True}, 200

    def delete(self, pwd_id):
        repository.delete_password(pwd_id)
        return {}, 204


@ns.route('/passwords/reorder')
class PasswordReorder(Resource):
    def post(self):
        b = request.get_json()
        repository.reorder_passwords(b['ids'])
        return {'ok': True}, 200


# --- Run ---

@ns.route('/run')
class RunPipeline(Resource):
    def post(self):
        b = request.get_json()
        pipeline_id = b['pipeline_id']
        folder_path = b['folder_path']
        run_vars = b.get('run_vars') or {}
        run_id = str(uuid.uuid4())

        def _run():
            try:
                from . import fp_websocket
                cb = fp_websocket.make_progress_callback(run_id, pipeline_id)
                get_service().run_pipeline(pipeline_id, folder_path, run_vars, cb)
            except Exception as e:
                from . import fp_websocket
                if fp_websocket._socketio:
                    fp_websocket._socketio.emit('fp_progress', {
                        'run_id': run_id,
                        'pipeline_id': pipeline_id,
                        'phase': 'error',
                        'error': str(e),
                    })

        threading.Thread(target=_run, daemon=True).start()
        return {'run_id': run_id}, 202
