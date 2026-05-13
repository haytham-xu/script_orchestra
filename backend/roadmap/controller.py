"""
Roadmap Kanban API Controller
"""
import uuid
from datetime import datetime, timedelta
from flask import request
from flask_restx import Namespace, Resource
from .models import Task, TaskStatus, TaskPriority
from .storage import task_storage

ns = Namespace("")


@ns.route("/tasks")
class TaskListResource(Resource):
    def get(self):
        """
        Get all tasks (auto-delete done tasks older than 7 days)

        Returns:
            List of all tasks
        """
        try:
            tasks = task_storage.get_all_tasks()

            # Auto-delete done tasks older than 7 days
            cutoff_date = datetime.now() - timedelta(days=7)
            tasks_to_delete = []

            for task in tasks:
                if task.status == TaskStatus.DONE and task.created_at < cutoff_date:
                    tasks_to_delete.append(task.id)

            # Delete old tasks
            for task_id in tasks_to_delete:
                task_storage.delete_task(task_id)

            # Reload tasks after deletion
            if tasks_to_delete:
                tasks = task_storage.get_all_tasks()

            return {"tasks": [task.to_dict() for task in tasks]}, 200
        except Exception as e:
            return {"error": str(e)}, 500

    def post(self):
        """
        Create new task

        Body:
            {
                "content": "Task content",
                "priority": "medium",
                "status": "todo"
            }

        Returns:
            Created task
        """
        try:
            data = request.json
            if not data or "content" not in data:
                return {"error": "Missing required field: content"}, 400

            # Generate UUID
            task_id = str(uuid.uuid4())

            # Get max order for the status
            tasks = task_storage.get_all_tasks()
            status = data.get("status", TaskStatus.TODO)
            status_tasks = [t for t in tasks if t.status == status]
            max_order = max([t.order for t in status_tasks], default=-1)

            # Create task
            task = Task(
                id=task_id,
                content=data["content"],
                priority=data.get("priority", TaskPriority.MEDIUM),
                status=status,
                order=max_order + 1
            )

            created_task = task_storage.create_task(task)
            return created_task.to_dict(), 201
        except Exception as e:
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
