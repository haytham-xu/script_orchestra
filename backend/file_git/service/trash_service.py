"""
TrashService — soft-delete for local files (REQUIREMENTS §3.6 trash/).

Instead of ``os.remove``, we move the file into
``.fgit/trash/<yyyymmdd>/<middle_path>`` preserving directory layout.
The user can manually clean up the trash later, or a hook does it
after ``hook_retention_days``.
"""
from __future__ import annotations

import os
import shutil
from datetime import datetime, timedelta


TRASH_DIRNAME = "trash"


class TrashService:
    @staticmethod
    def _trash_root(repo_root: str) -> str:
        return os.path.join(repo_root, ".fgit", TRASH_DIRNAME)

    @staticmethod
    def _date_dir(repo_root: str) -> str:
        stamp = datetime.now().strftime("%Y%m%d")
        path = os.path.join(TrashService._trash_root(repo_root), stamp)
        os.makedirs(path, exist_ok=True)
        return path

    @staticmethod
    def move_to_trash(repo_root: str, middle_path: str) -> str:
        """Move the file at ``<repo_root>/<middle_path>`` into today's trash.

        Returns the destination path. If the source doesn't exist,
        returns an empty string (idempotent semantics — sync layer
        treats delete of missing files as success).
        """
        source = os.path.join(repo_root, *middle_path.split("/"))
        if not os.path.exists(source):
            return ""

        dest = os.path.join(TrashService._date_dir(repo_root), *middle_path.split("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        # If a file with the same name was trashed earlier today, add a
        # numeric suffix to avoid clobbering.
        base, ext = os.path.splitext(dest)
        counter = 1
        while os.path.exists(dest):
            dest = f"{base}.{counter}{ext}"
            counter += 1
        shutil.move(source, dest)
        return dest

    @staticmethod
    def cleanup_old(repo_root: str, retention_days: int) -> int:
        """Delete trash date-folders older than ``retention_days``.

        Returns the number of folders removed.
        """
        root = TrashService._trash_root(repo_root)
        if not os.path.isdir(root):
            return 0
        cutoff = datetime.now() - timedelta(days=retention_days)
        removed = 0
        for entry in os.listdir(root):
            entry_path = os.path.join(root, entry)
            if not os.path.isdir(entry_path):
                continue
            try:
                folder_date = datetime.strptime(entry, "%Y%m%d")
            except ValueError:
                continue
            if folder_date < cutoff:
                try:
                    shutil.rmtree(entry_path)
                    removed += 1
                except Exception as exc:
                    print(f"[TrashService] failed to remove {entry_path}: {exc}")
        return removed

    @staticmethod
    def cleanup_all(repo_root: str) -> int:
        """Delete every date folder under trash/. Returns count removed."""
        root = TrashService._trash_root(repo_root)
        if not os.path.isdir(root):
            return 0
        removed = 0
        for entry in os.listdir(root):
            entry_path = os.path.join(root, entry)
            if os.path.isdir(entry_path):
                try:
                    shutil.rmtree(entry_path)
                    removed += 1
                except Exception as exc:
                    print(f"[TrashService] failed to remove {entry_path}: {exc}")
        return removed
