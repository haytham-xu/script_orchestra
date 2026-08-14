"""
Roadmap Kanban API Controller
"""
import uuid
from datetime import datetime, timedelta
from flask import request
from flask_restx import Namespace, Resource
from .models import Task, TaskStatus, TaskPriority
from .storage import task_storage
from .settings_db import settings_db
from .settings_models import RoadmapSettings

ns = Namespace("")


@ns.route("/tasks")
class TaskListResource(Resource):
    def get(self):
        """
        Get all tasks

        Returns:
            List of all tasks
        """
        try:
            tasks = task_storage.get_all_tasks()
            return {"tasks": [task.to_dict() for task in tasks]}, 200
        except Exception as e:
            return {"error": str(e)}, 500

    def post(self):
        """
        Create new task

        Body:
            {
                "header": "Short title",
                "content": "Detailed content",
                "priority": "medium",
                "status": "todo",
                "size": "M",
                "eta": "2026-07-05T00:00:00",
                "category": "日常工作"
            }

        Returns:
            Created task
        """
        try:
            print("[Controller] POST /tasks - Start")
            data = request.json
            print(f"[Controller] Request data: {data}")

            if not data or "header" not in data:
                print("[Controller] Error: Missing header")
                return {"error": "Missing required field: header"}, 400

            # Generate UUID
            task_id = str(uuid.uuid4())
            print(f"[Controller] Generated task ID: {task_id}")

            # Parse ETA if provided
            eta = None
            if data.get("eta"):
                try:
                    eta = datetime.fromisoformat(data["eta"].replace('Z', '+00:00'))
                    print(f"[Controller] Parsed ETA: {eta}")
                except Exception as e:
                    print(f"[Controller] Failed to parse ETA: {e}")
                    pass

            # Create task (order will be auto-calculated by storage)
            from .models import TaskSize, TaskCategory
            print(f"[Controller] Creating task with priority={data.get('priority')}, eta={eta}")
            task = Task(
                id=task_id,
                header=data["header"],
                content=data.get("content", ""),
                priority=data.get("priority", TaskPriority.MEDIUM),
                status=data.get("status", TaskStatus.TODO),
                size=data.get("size", TaskSize.MEDIUM),
                eta=eta,
                category=data.get("category", TaskCategory.A),
                order=0  # Will be recalculated by storage.create_task()
            )

            print(f"[Controller] Calling storage.create_task()")
            created_task = task_storage.create_task(task)
            print(f"[Controller] Task created successfully with order={created_task.order}")
            return created_task.to_dict(), 201
        except Exception as e:
            print(f"[Controller] Error creating task: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            return {"error": str(e)}, 500


@ns.route("/tasks/<string:task_id>")
class TaskResource(Resource):
    def get(self, task_id):
        """
        Get task by ID

        Returns:
            Task details
        """
        try:
            task = task_storage.get_task_by_id(task_id)
            if not task:
                return {"error": "Task not found"}, 404
            return task.to_dict(), 200
        except Exception as e:
            return {"error": str(e)}, 500

    def put(self, task_id):
        """
        Update task

        Body:
            {
                "header": "Updated header",
                "content": "Updated content",
                "priority": "high",
                "status": "in_progress"
            }

        Returns:
            Updated task
        """
        try:
            data = request.json
            if not data:
                return {"error": "Missing request body"}, 400

            updated_task = task_storage.update_task(task_id, data)
            if not updated_task:
                return {"error": "Task not found"}, 404

            return updated_task.to_dict(), 200
        except Exception as e:
            return {"error": str(e)}, 500

    def delete(self, task_id):
        """
        Delete task

        Returns:
            Success message
        """
        try:
            success = task_storage.delete_task(task_id)
            if not success:
                return {"error": "Task not found"}, 404

            return {"message": "Task deleted successfully"}, 200
        except Exception as e:
            return {"error": str(e)}, 500


@ns.route("/tasks/reorder")
class TaskReorderResource(Resource):
    def put(self):
        """
        Batch update task orders and statuses (for drag & drop)

        Body:
            {
                "updates": [
                    {"id": "task-id-1", "status": "todo", "order": 0},
                    {"id": "task-id-2", "status": "in_progress", "order": 1}
                ]
            }

        Returns:
            Updated tasks
        """
        try:
            data = request.json
            if not data or "updates" not in data:
                return {"error": "Missing required field: updates"}, 400

            updated_tasks = task_storage.reorder_tasks(data["updates"])
            return {"tasks": [task.to_dict() for task in updated_tasks]}, 200
        except Exception as e:
            return {"error": str(e)}, 500


@ns.route("/settings")
class SettingsResource(Resource):
    def get(self):
        """
        Get roadmap settings

        Returns:
            Settings object
        """
        try:
            settings = settings_db.get_settings()
            return settings.to_dict(), 200
        except Exception as e:
            return {"error": str(e)}, 500

    def put(self):
        """
        Update roadmap settings

        Body:
            {
                "inProgressTimeoutHours": 4.0,
                "doneAutoRemoveDays": 7
            }

        Returns:
            Updated settings
        """
        try:
            data = request.json
            if not data:
                return {"error": "Missing request body"}, 400

            settings = RoadmapSettings.from_dict(data)
            updated_settings = settings_db.update_settings(settings)
            return updated_settings.to_dict(), 200
        except Exception as e:
            return {"error": str(e)}, 500

