"""
LoggerService — structured per-action logging (REQUIREMENTS §3.7 log/).

Each action folder gets ``log/success.log`` and ``log/error.log``.
Lines are TSV-like:

    <iso timestamp>\t<action>\t<middle_path>\t<detail>

Callers pass the action_folder relative name (e.g.
``20260816_1430_push``); the service resolves absolute paths.

Also provides a hook to clean up old action folders.
"""
from __future__ import annotations

import os
import shutil
from datetime import datetime, timedelta

from .queue_service import QueueService


class LoggerService:
    @staticmethod
    def _log_dir(repo_root: str, action_folder: str) -> str:
        path = os.path.join(
            QueueService.action_folder_path(repo_root, action_folder),
            "log",
        )
        os.makedirs(path, exist_ok=True)
        return path

    @staticmethod
    def _write_line(
        repo_root: str,
        action_folder: str,
        filename: str,
        action: str,
        middle_path: str,
        detail: str,
    ) -> None:
        line = "\t".join([
            datetime.now().isoformat(timespec="seconds"),
            action,
            middle_path,
            detail.replace("\n", " ").replace("\t", " "),
        ])
        path = os.path.join(LoggerService._log_dir(repo_root, action_folder), filename)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    @staticmethod
    def log_success(
        repo_root: str,
        action_folder: str,
        action: str,
        middle_path: str,
        detail: str = "",
    ) -> None:
        LoggerService._write_line(
            repo_root, action_folder, "success.log", action, middle_path, detail
        )

    @staticmethod
    def log_error(
        repo_root: str,
        action_folder: str,
        action: str,
        middle_path: str,
        detail: str,
    ) -> None:
        LoggerService._write_line(
            repo_root, action_folder, "error.log", action, middle_path, detail
        )

    @staticmethod
    def log_anomaly(
        repo_root: str,
        action_folder: str,
        middle_path: str,
        detail: str,
    ) -> None:
        """REQUIREMENTS §3.11: strange local/cloud discrepancies go into a
        dedicated anomaly.log alongside success/error."""
        LoggerService._write_line(
            repo_root, action_folder, "anomaly.log", "ANOMALY", middle_path, detail
        )

    # ---- hook: clean up old action folders ---------------------------

    @staticmethod
    def cleanup_old_actions(repo_root: str, retention_days: int) -> int:
        """Delete action folders older than ``retention_days``. Returns count.

        Folder naming pattern is ``<yyyymmdd_hhmm>_<action_type>[_N]``
        as produced by QueueService.
        """
        root = os.path.join(repo_root, ".fgit", "action")
        if not os.path.isdir(root):
            return 0
        cutoff = datetime.now() - timedelta(days=retention_days)
        removed = 0
        for entry in os.listdir(root):
            entry_path = os.path.join(root, entry)
            if not os.path.isdir(entry_path):
                continue
            # Parse the leading yyyymmdd_hhmm
            try:
                stamp = "_".join(entry.split("_")[:2])
                folder_date = datetime.strptime(stamp, "%Y%m%d_%H%M")
            except ValueError:
                continue
            if folder_date < cutoff:
                try:
                    shutil.rmtree(entry_path)
                    removed += 1
                except Exception as exc:
                    print(f"[LoggerService] failed to remove {entry_path}: {exc}")
        return removed

    @staticmethod
    def cleanup_all_actions(repo_root: str) -> int:
        root = os.path.join(repo_root, ".fgit", "action")
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
                    print(f"[LoggerService] failed to remove {entry_path}: {exc}")
        return removed
