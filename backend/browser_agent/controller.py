"""Browser Agent — REST controller.

Endpoints (relative to the blueprint prefix /browser-agent):
  POST   /tabs               ingest tab URLs from the extension
  GET    /tasks              list the download queue
  POST   /tasks/<id>/retry   reset a task to TODO
  DELETE /tasks/<id>         remove a task
  GET    /settings           read settings
  PUT    /settings           update settings
"""
from flask_restx import Namespace, Resource
from flask import request

from . import repository, settings_manager
from .entity import Status
from .service import get_service

ns = Namespace("")


@ns.route("/tabs")
class TabsResource(Resource):
    def post(self):
        data = request.json or {}
        tabs = data.get("tabs", [])
        if not isinstance(tabs, list):
            return {"error": "tabs must be a list of URLs"}, 400
        result = get_service().store_tabs(tabs)
        return {"message": "Tabs received", **result}, 202


@ns.route("/tasks")
class TasksResource(Resource):
    def get(self):
        return {"tasks": [t.to_dict() for t in repository.get_all()]}, 200


@ns.route("/tasks/<int:task_id>/retry")
class TaskRetryResource(Resource):
    def post(self, task_id):
        tab = repository.get_by_id(task_id)
        if tab is None:
            return {"error": "task not found"}, 404
        tab.status = Status.TODO.value
        tab.retry_times = 0
        repository.update_browser_tab(tab)
        return {"message": "task reset to TODO"}, 200


@ns.route("/tasks/<int:task_id>")
class TaskResource(Resource):
    def delete(self, task_id):
        if repository.get_by_id(task_id) is None:
            return {"error": "task not found"}, 404
        repository.delete_by_id(task_id)
        return {"message": "task deleted"}, 200


@ns.route("/settings")
class SettingsResource(Resource):
    def get(self):
        return {"settings": settings_manager.load_settings()}, 200

    def put(self):
        data = request.json or {}
        if not isinstance(data, dict):
            return {"error": "Body must be a JSON object"}, 400
        try:
            current = settings_manager.load_settings()
            updated = settings_manager.validate_and_normalize(data, current)
            settings_manager.save_settings(updated)
            return {"message": "Settings updated", "settings": updated}, 200
        except ValueError as e:
            return {"error": str(e)}, 400
        except Exception as e:
            return {"error": f"Failed to update settings: {e}"}, 500
