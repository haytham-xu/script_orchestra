"""
Data models for Roadmap Kanban
"""
from typing import List, Optional
from datetime import datetime
from enum import Enum


class TaskStatus(str, Enum):
    """Task status (column)"""
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    BLOCK = "block"
    DONE = "done"


class TaskPriority(str, Enum):
    """Task priority"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Task:
    """Task model"""
    def __init__(
        self,
        id: str,
        content: str,
        status: TaskStatus = TaskStatus.TODO,
        priority: TaskPriority = TaskPriority.MEDIUM,
        created_at: Optional[datetime] = None,
        order: int = 0
    ):
        self.id = id
        self.content = content
        self.status = status
        self.priority = priority
        self.created_at = created_at or datetime.now()
        self.order = order

    def to_dict(self):
        """Convert to dict for JSON serialization"""
        return {
            "id": self.id,
            "content": self.content,
            "status": self.status,
            "priority": self.priority,
            "createdAt": self.created_at.isoformat(),
            "order": self.order
        }

    @staticmethod
    def from_dict(data: dict) -> 'Task':
        """Create Task from dict"""
        # Support migration from old format
        content = data.get("content")
        if not content:
            # Fallback to old title/description format
            title = data.get("title", "")
            description = data.get("description", "")
            content = f"{title}\n{description}" if description else title

        return Task(
            id=data["id"],
            content=content,
            status=data.get("status", TaskStatus.TODO),
            priority=data.get("priority", TaskPriority.MEDIUM),
            created_at=datetime.fromisoformat(data["createdAt"]) if "createdAt" in data else None,
            order=data.get("order", 0)
        )
