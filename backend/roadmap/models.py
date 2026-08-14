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


class TaskSize(str, Enum):
    """Task size"""
    SMALL = "S"
    MEDIUM = "M"
    BIG = "B"


class TaskCategory(str, Enum):
    """Task category - internal identifiers only, no semantic meaning"""
    A = "a"
    B = "b"
    C = "c"
    D = "d"


class Task:
    """Task model"""
    def __init__(
        self,
        id: str,
        header: str,
        content: str,
        status: TaskStatus = TaskStatus.TODO,
        priority: TaskPriority = TaskPriority.MEDIUM,
        size: TaskSize = TaskSize.MEDIUM,
        eta: Optional[datetime] = None,
        category: TaskCategory = TaskCategory.A,
        created_at: Optional[datetime] = None,
        order: int = 0,
        in_progress_at: Optional[datetime] = None,
        returned_from_in_progress: bool = False,
        returned_at: Optional[datetime] = None,
        done_at: Optional[datetime] = None
    ):
        self.id = id
        self.header = header
        self.content = content
        self.status = status
        self.priority = priority
        self.size = size
        self.eta = eta
        self.category = category
        self.created_at = created_at or datetime.now()
        self.order = order
        self.in_progress_at = in_progress_at
        self.returned_from_in_progress = returned_from_in_progress
        self.returned_at = returned_at
        self.done_at = done_at

    def to_dict(self):
        """Convert to dict for JSON serialization"""
        return {
            "id": self.id,
            "header": self.header,
            "content": self.content,
            "status": self.status,
            "priority": self.priority,
            "size": self.size,
            "eta": self.eta.isoformat() if self.eta else None,
            "category": self.category,
            "createdAt": self.created_at.isoformat(),
            "order": self.order,
            "inProgressAt": self.in_progress_at.isoformat() if self.in_progress_at else None,
            "returnedFromInProgress": self.returned_from_in_progress,
            "returnedAt": self.returned_at.isoformat() if self.returned_at else None,
            "doneAt": self.done_at.isoformat() if self.done_at else None
        }

    @staticmethod
    def from_dict(data: dict) -> 'Task':
        """Create Task from dict"""
        # Support migration from old format (content -> header + content)
        header = data.get("header")
        content = data.get("content", "")

        if not header:
            # If no header field, split old content field
            old_content = data.get("content", "")
            if old_content:
                # Use first line as header, rest as content
                lines = old_content.split('\n', 1)
                header = lines[0]
                content = lines[1] if len(lines) > 1 else ""
            else:
                # Fallback to old title/description format
                header = data.get("title", "")
                content = data.get("description", "")

        return Task(
            id=data["id"],
            header=header,
            content=content,
            status=data.get("status", TaskStatus.TODO),
            priority=data.get("priority", TaskPriority.MEDIUM),
            size=data.get("size", TaskSize.MEDIUM),
            eta=datetime.fromisoformat(data["eta"]) if data.get("eta") else None,
            category=data.get("category", TaskCategory.A),
            created_at=datetime.fromisoformat(data["createdAt"]) if "createdAt" in data else None,
            order=data.get("order", 0),
            in_progress_at=datetime.fromisoformat(data["inProgressAt"]) if data.get("inProgressAt") else None,
            returned_from_in_progress=data.get("returnedFromInProgress", False),
            returned_at=datetime.fromisoformat(data["returnedAt"]) if data.get("returnedAt") else None,
            done_at=datetime.fromisoformat(data["doneAt"]) if data.get("doneAt") else None
        )
