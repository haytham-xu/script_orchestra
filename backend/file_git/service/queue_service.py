"""
QueueService — persistent queue with lock and action-folder management
(REQUIREMENTS §3.6, §3.7, §3.8).

The queue lives at ``.fgit/queue.json`` and drives resumable sync:

    * Acquire lock at command start (Push/Pull/Manual Upload/Pre Manual DL)
    * Enqueue items with ``status=TODO``
    * ActionExecutor consumes each item, marks IN_PROGRESS → DONE / ERROR
    * When empty, release lock and archive the final queue snapshot into
      ``.fgit/action/<timestamp>_<cmd>/queue.json``

Only one action holds the lock at a time. See REQUIREMENTS §3.8 for
which commands are permitted while locked.
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, TypedDict


QUEUE_FILENAME = "queue.json"
ACTION_DIRNAME = "action"


class ActionType(str, Enum):
    UPLOAD = "UPLOAD"
    DOWNLOAD = "DOWNLOAD"
    LOCAL_DELETE = "LOCAL_DELETE"
    REMOTE_DELETE = "REMOTE_DELETE"


class Status(str, Enum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    ERROR = "ERROR"


class QueueItem(TypedDict, total=False):
    middle_path: str
    encoded_path: str
    action: str          # ActionType value
    status: str          # Status value
    size: int
    retry_count: int
    last_error: Optional[str]


@dataclass
class QueueState:
    lock: bool
    action_folder: Optional[str]
    action_type: Optional[str]
    queue: Dict[str, QueueItem]

    def to_dict(self) -> dict:
        return {
            "lock": self.lock,
            "action_folder": self.action_folder,
            "action_type": self.action_type,
            "queue": self.queue,
        }

    @classmethod
    def empty(cls) -> "QueueState":
        return cls(lock=False, action_folder=None, action_type=None, queue={})

    @classmethod
    def from_dict(cls, data: dict) -> "QueueState":
        return cls(
            lock=data.get("lock", False),
            action_folder=data.get("action_folder"),
            action_type=data.get("action_type"),
            queue=data.get("queue") or {},
        )


class LockError(Exception):
    """Raised when a command tries to acquire an already-held lock."""


class QueueService:
    """Stateless helpers over ``.fgit/queue.json``."""

    # ---- path helpers -------------------------------------------------

    @staticmethod
    def _queue_path(repo_root: str) -> str:
        return os.path.join(repo_root, ".fgit", QUEUE_FILENAME)

    @staticmethod
    def _action_root(repo_root: str) -> str:
        return os.path.join(repo_root, ".fgit", ACTION_DIRNAME)

    # ---- read/write ---------------------------------------------------

    @staticmethod
    def load(repo_root: str) -> QueueState:
        path = QueueService._queue_path(repo_root)
        if not os.path.exists(path):
            return QueueState.empty()
        with open(path, "r", encoding="utf-8") as f:
            return QueueState.from_dict(json.load(f))

    @staticmethod
    def save(repo_root: str, state: QueueState) -> None:
        path = QueueService._queue_path(repo_root)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)

    # ---- lock / action lifecycle -------------------------------------

    @staticmethod
    def acquire(
        repo_root: str,
        action_type: str,
        *,
        allow_when_locked_by_same_action: bool = False,
    ) -> QueueState:
        """Grab the lock for a new action.

        Returns the fresh QueueState (empty queue) with lock=true and
        a newly-created action_folder. If already locked, raises
        ``LockError`` unless the caller opts into resuming.
        """
        state = QueueService.load(repo_root)
        if state.lock:
            if not allow_when_locked_by_same_action:
                raise LockError(
                    f"Repository is locked by a prior '{state.action_type}' operation. "
                    f"Use resume/queue to continue or clear the lock manually."
                )
            # Resume path — caller must handle continuing an existing queue
            return state

        action_folder = QueueService._make_action_folder(repo_root, action_type)
        state = QueueState(
            lock=True,
            action_folder=action_folder,
            action_type=action_type,
            queue={},
        )
        QueueService.save(repo_root, state)
        return state

    @staticmethod
    def release(repo_root: str, *, archive: bool = True) -> None:
        """Archive the current queue to action_folder and unlock.

        ``archive=True`` copies the current queue.json into the action
        folder before clearing. Set to False if the archive already
        happened (e.g. on error-only exit).
        """
        state = QueueService.load(repo_root)
        if archive and state.action_folder:
            dest = os.path.join(
                QueueService._action_root(repo_root),
                state.action_folder,
                QUEUE_FILENAME,
            )
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8") as f:
                json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)

        QueueService.save(repo_root, QueueState.empty())

    @staticmethod
    def is_locked(repo_root: str) -> bool:
        return QueueService.load(repo_root).lock

    @staticmethod
    def _make_action_folder(repo_root: str, action_type: str) -> str:
        """Create ``.fgit/action/<yyyymmdd_hhmm>_<action_type>/`` and return its
        basename (relative to ``.fgit/action/``)."""
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        # Ensure uniqueness even within the same minute
        suffix = 0
        while True:
            candidate = f"{stamp}_{action_type}" + (f"_{suffix}" if suffix else "")
            full = os.path.join(QueueService._action_root(repo_root), candidate)
            if not os.path.exists(full):
                os.makedirs(full, exist_ok=True)
                os.makedirs(os.path.join(full, "log"), exist_ok=True)
                return candidate
            suffix += 1

    @staticmethod
    def action_folder_path(repo_root: str, action_folder: str) -> str:
        return os.path.join(QueueService._action_root(repo_root), action_folder)

    # ---- queue item manipulation -------------------------------------

    @staticmethod
    def enqueue(
        state: QueueState,
        key: str,
        item: QueueItem,
    ) -> None:
        """Add ``item`` to ``state.queue`` under ``key``. Mutates in place."""
        item.setdefault("status", Status.TODO.value)
        item.setdefault("retry_count", 0)
        item.setdefault("last_error", None)
        state.queue[key] = item

    @staticmethod
    def pending_items(state: QueueState) -> List[tuple]:
        """Return [(key, item), …] for items not yet DONE.

        Includes TODO, IN_PROGRESS (crash-recovery) and ERROR (retryable).
        DONE items are already removed by ``mark_done``.
        """
        return [
            (k, v) for k, v in state.queue.items()
            if v.get("status") != Status.DONE.value
        ]

    @staticmethod
    def mark_in_progress(
        repo_root: str,
        state: QueueState,
        key: str,
    ) -> None:
        state.queue[key]["status"] = Status.IN_PROGRESS.value
        QueueService.save(repo_root, state)

    @staticmethod
    def mark_done(
        repo_root: str,
        state: QueueState,
        key: str,
    ) -> None:
        """Remove the item from the queue and persist."""
        state.queue.pop(key, None)
        QueueService.save(repo_root, state)

    @staticmethod
    def mark_error(
        repo_root: str,
        state: QueueState,
        key: str,
        error: str,
    ) -> None:
        item = state.queue[key]
        item["status"] = Status.ERROR.value
        item["retry_count"] = item.get("retry_count", 0) + 1
        item["last_error"] = error
        QueueService.save(repo_root, state)

    # ---- action-folder side files ------------------------------------

    @staticmethod
    def snapshot_index_into_action(
        repo_root: str,
        action_folder: str,
        filename: str,
        data: dict,
    ) -> None:
        """Write ``local_index.json`` / ``cloud_index.json`` snapshots into
        the action folder for audit."""
        dest_dir = QueueService.action_folder_path(repo_root, action_folder)
        os.makedirs(dest_dir, exist_ok=True)
        with open(os.path.join(dest_dir, filename), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
