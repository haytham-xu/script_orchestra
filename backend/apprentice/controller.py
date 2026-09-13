"""Apprentice — REST controller."""
import json
import time
from flask import Response, request, stream_with_context
from flask_restx import Namespace, Resource

from . import repository, settings_manager, runner
from .service import get_service

ns = Namespace('apprentice', description='Apprentice autonomous developer agent')


# ── Tasks ────────────────────────────────────────────────────

@ns.route('/tasks')
class TaskList(Resource):
    def get(self):
        svc = get_service()
        return {"tasks": [t.to_dict() for t in svc.list_tasks()]}

    def post(self):
        data = request.get_json(force=True) or {}
        title = (data.get("title") or "").strip()
        description = (data.get("description") or "").strip()
        repo_path = (data.get("repo_path") or "").strip()
        if not title or not description or not repo_path:
            return {"error": "title, description and repo_path are required"}, 400
        task = get_service().create_task(title, description, repo_path)
        return task.to_dict(), 201


@ns.route('/tasks/<int:task_id>')
class TaskDetail(Resource):
    def get(self, task_id: int):
        task = get_service().get_task(task_id)
        if task is None:
            return {"error": "not found"}, 404
        return task.to_dict()


@ns.route('/tasks/<int:task_id>/start')
class TaskStart(Resource):
    def post(self, task_id: int):
        try:
            task = get_service().start_task(task_id)
            return task.to_dict()
        except (ValueError, RuntimeError) as e:
            return {"error": str(e)}, 400


@ns.route('/tasks/<int:task_id>/stop')
class TaskStop(Resource):
    def post(self, task_id: int):
        get_service().stop_task(task_id)
        return {"status": "stopped"}


@ns.route('/tasks/<int:task_id>/events')
class TaskEvents(Resource):
    def get(self, task_id: int):
        sub_id, q = runner.subscribe()

        def generate():
            try:
                while True:
                    try:
                        event = q.get(timeout=30)
                        if event.get("task_id") == task_id or "task_id" not in event:
                            yield f"data: {json.dumps(event)}\n\n"
                        if event.get("event") in ("done", "run_finished"):
                            break
                    except Exception:
                        yield "data: {\"event\":\"heartbeat\"}\n\n"
            finally:
                runner.unsubscribe(sub_id)

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )


# ── Human channel ─────────────────────────────────────────────

@ns.route('/tasks/<int:task_id>/messages')
class HumanMessages(Resource):
    def get(self, task_id: int):
        msgs = repository.list_human_messages(task_id)
        return {"messages": [m.to_dict() for m in msgs]}

    def post(self, task_id: int):
        data = request.get_json(force=True) or {}
        content = (data.get("content") or "").strip()
        if not content:
            return {"error": "content is required"}, 400
        msg = repository.post_human_message(task_id, "user_to_cmd", content)
        return msg.to_dict(), 201


# ── Memory ────────────────────────────────────────────────────

@ns.route('/memory/short')
class MemoryShortList(Resource):
    def get(self):
        entries = get_service().list_short_memory()
        return {"entries": [e.to_dict() for e in entries]}


@ns.route('/memory/short/<int:entry_id>/feedback')
class MemoryShortFeedback(Resource):
    def post(self, entry_id: int):
        data = request.get_json(force=True) or {}
        score = data.get("score")
        note = data.get("note")
        if score is not None:
            try:
                score = int(score)
                if not 1 <= score <= 5:
                    raise ValueError()
            except (TypeError, ValueError):
                return {"error": "score must be 1-5"}, 400
        get_service().update_short_feedback(entry_id, score, note)
        return {"status": "updated"}


@ns.route('/memory/long')
class MemoryLong(Resource):
    def get(self):
        content = get_service().get_long_memory()
        return {"content": content}


@ns.route('/memory/distill')
class MemoryDistill(Resource):
    def post(self):
        try:
            new_text = get_service().distill()
            return {"content": new_text}
        except Exception as e:
            return {"error": str(e)}, 500


# ── Red lines ─────────────────────────────────────────────────

@ns.route('/red-lines')
class RedLineList(Resource):
    def get(self):
        lines = repository.list_red_lines()
        return {"red_lines": [r.to_dict() for r in lines]}

    def post(self):
        data = request.get_json(force=True) or {}
        rule = (data.get("rule") or "").strip()
        if not rule:
            return {"error": "rule is required"}, 400
        line = repository.add_red_line(rule)
        return line.to_dict(), 201


@ns.route('/red-lines/<int:red_line_id>')
class RedLineDetail(Resource):
    def delete(self, red_line_id: int):
        deleted = repository.delete_red_line(red_line_id)
        if not deleted:
            return {"error": "not found"}, 404
        return {"status": "deleted"}


# ── Settings ──────────────────────────────────────────────────

@ns.route('/settings')
class Settings(Resource):
    def get(self):
        return settings_manager.load_settings()

    def put(self):
        data = request.get_json(force=True) or {}
        current = settings_manager.load_settings()
        try:
            updated = settings_manager.validate_and_normalize(data, current)
        except ValueError as e:
            return {"error": str(e)}, 400
        settings_manager.save_settings(updated)
        return updated
