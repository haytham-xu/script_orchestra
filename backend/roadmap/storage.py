"""
Task storage using JSON file
"""
import os
import json
from typing import List, Optional
from pathlib import Path
from .models import Task, TaskStatus

# Storage file path
STORAGE_DIR = Path(__file__).parent
STORAGE_FILE = STORAGE_DIR / "tasks.json"


class TaskStorage:
    """Task storage manager"""

    def __init__(self):
        self._ensure_storage_file()

    def _ensure_storage_file(self):
        """Ensure storage file exists"""
        if not STORAGE_FILE.exists():
            with open(STORAGE_FILE, 'w', encoding='utf-8') as f:
                json.dump({"tasks": []}, f, ensure_ascii=False, indent=2)

    def load_tasks(self) -> List[Task]:
        """Load all tasks"""
        try:
            with open(STORAGE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return [Task.from_dict(task_data) for task_data in data.get("tasks", [])]
        except Exception as e:
            print(f"[TaskStorage] Error loading tasks: {e}")
            return []

    def save_tasks(self, tasks: List[Task]):
        """Save all tasks"""
        try:
            data = {"tasks": [task.to_dict() for task in tasks]}
            with open(STORAGE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[TaskStorage] Error saving tasks: {e}")
            raise

    def get_all_tasks(self) -> List[Task]:
        """Get all tasks"""
        return self.load_tasks()

    def get_task_by_id(self, task_id: str) -> Optional[Task]:
        """Get task by ID"""
        tasks = self.load_tasks()
        for task in tasks:
            if task.id == task_id:
                return task
        return None

    def create_task(self, task: Task) -> Task:
        """Create new task"""
        tasks = self.load_tasks()
        tasks.append(task)
        self.save_tasks(tasks)
        return task

    def update_task(self, task_id: str, updates: dict) -> Optional[Task]:
        """Update task"""
        tasks = self.load_tasks()
        for i, task in enumerate(tasks):
            if task.id == task_id:
                # Update fields
                if "title" in updates:
                    task.title = updates["title"]
                if "description" in updates:
                    task.description = updates["description"]
                if "status" in updates:
                    task.status = updates["status"]
                if "priority" in updates:
                    task.priority = updates["priority"]
                if "order" in updates:
                    task.order = updates["order"]

                tasks[i] = task
                self.save_tasks(tasks)
                return task
        return None

    def delete_task(self, task_id: str) -> bool:
        """Delete task"""
        tasks = self.load_tasks()
        original_len = len(tasks)
        tasks = [task for task in tasks if task.id != task_id]
        if len(tasks) < original_len:
            self.save_tasks(tasks)
            return True
        return False

    def reorder_tasks(self, task_updates: List[dict]) -> List[Task]:
        """
        Batch update task orders and statuses
        task_updates: [{"id": "xxx", "status": "todo", "order": 0}, ...]
        """
        tasks = self.load_tasks()
        task_map = {task.id: task for task in tasks}

        for update in task_updates:
            task_id = update.get("id")
            if task_id in task_map:
                if "status" in update:
                    task_map[task_id].status = update["status"]
                if "order" in update:
                    task_map[task_id].order = update["order"]

        updated_tasks = list(task_map.values())
        self.save_tasks(updated_tasks)
        return updated_tasks


# Global storage instance
task_storage = TaskStorage()
