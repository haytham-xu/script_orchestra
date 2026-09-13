"""Apprentice — plain data classes."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Task:
    id: int
    title: str
    description: str
    repo_path: str
    status: str
    created_at: str
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    pid: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "repo_path": self.repo_path,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "pid": self.pid,
        }

    @classmethod
    def from_row(cls, row) -> "Task":
        return cls(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            repo_path=row["repo_path"],
            status=row["status"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            pid=row["pid"],
        )


@dataclass
class MemoryShort:
    id: int
    task_id: int
    raw_log: str
    created_at: str
    user_score: Optional[int] = None
    user_note: Optional[str] = None
    distilled: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "raw_log": self.raw_log,
            "user_score": self.user_score,
            "user_note": self.user_note,
            "created_at": self.created_at,
            "distilled": bool(self.distilled),
        }

    @classmethod
    def from_row(cls, row) -> "MemoryShort":
        return cls(
            id=row["id"],
            task_id=row["task_id"],
            raw_log=row["raw_log"],
            created_at=row["created_at"],
            user_score=row["user_score"],
            user_note=row["user_note"],
            distilled=row["distilled"],
        )


@dataclass
class MemoryLong:
    id: int
    content: str
    updated_at: str

    def to_dict(self) -> dict:
        return {"id": self.id, "content": self.content, "updated_at": self.updated_at}

    @classmethod
    def from_row(cls, row) -> "MemoryLong":
        return cls(id=row["id"], content=row["content"], updated_at=row["updated_at"])


@dataclass
class HumanMessage:
    id: int
    task_id: int
    direction: str  # 'user_to_cmd' | 'cmd_to_user'
    content: str
    read_by_cmd: int
    created_at: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "direction": self.direction,
            "content": self.content,
            "read_by_cmd": bool(self.read_by_cmd),
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row) -> "HumanMessage":
        return cls(
            id=row["id"],
            task_id=row["task_id"],
            direction=row["direction"],
            content=row["content"],
            read_by_cmd=row["read_by_cmd"],
            created_at=row["created_at"],
        )


@dataclass
class RedLine:
    id: int
    rule: str
    created_at: str

    def to_dict(self) -> dict:
        return {"id": self.id, "rule": self.rule, "created_at": self.created_at}

    @classmethod
    def from_row(cls, row) -> "RedLine":
        return cls(id=row["id"], rule=row["rule"], created_at=row["created_at"])
