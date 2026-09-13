"""Apprentice — service layer (thin orchestration)."""
from typing import Optional

from . import repository, runner, memory_service
from .entity import Task


_instance = None


class ApprenticeService:

    def create_task(self, title: str, description: str, repo_path: str) -> Task:
        return repository.create_task(title, description, repo_path)

    def start_task(self, task_id: int) -> Task:
        task = repository.get_task(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        if task.status == "running":
            raise RuntimeError("Task is already running")
        runner.start(task_id)
        return repository.get_task(task_id)

    def stop_task(self, task_id: int) -> None:
        runner.stop(task_id)

    def get_task(self, task_id: int) -> Optional[Task]:
        return repository.get_task(task_id)

    def list_tasks(self) -> list:
        return repository.list_tasks()

    def get_long_memory(self) -> str:
        return memory_service.get_long_memory_text()

    def list_short_memory(self) -> list:
        return repository.list_short_memory()

    def distill(self) -> str:
        return memory_service.trigger_distillation()

    def update_short_feedback(self, entry_id: int, score: Optional[int], note: Optional[str]) -> None:
        repository.update_short_memory_feedback(entry_id, score, note)

    def running_task_id(self) -> Optional[int]:
        return runner.running_task_id()


def get_service() -> ApprenticeService:
    global _instance
    if _instance is None:
        _instance = ApprenticeService()
    return _instance
