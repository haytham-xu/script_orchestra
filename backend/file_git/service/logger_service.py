"""
LoggerService — structured per-action logging (REQUIREMENTS §3.7 log/).

Each action folder gets ``log/success.log``, ``log/error.log``, and
``log/file_log.jsonl``.

TSV logs (success/error/anomaly):
    <iso timestamp>\t<action>\t<middle_path>\t<detail>

file_log.jsonl — one JSON object per line:
    { ts, path, mode, status, in_local, in_remote, action, result, detail }

Callers pass the action_folder relative name (e.g.
``20260816_1430_push``); the service resolves absolute paths.

Also provides a hook to clean up old action folders.
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timedelta
from typing import Optional

from .queue_service import QueueService


class BatchLogWriter:
    """Keeps success.log / error.log / file_log.jsonl handles open for the
    duration of a long drain, so a 500k-item push does three ``open()`` calls
    instead of a million. Use via ``LoggerService.open_batch`` in a
    ``with``/``try-finally`` block. Not thread-safe — the drain loop is the
    only writer."""

    def __init__(self, log_dir: str) -> None:
        os.makedirs(log_dir, exist_ok=True)
        self._success = open(os.path.join(log_dir, "success.log"), "a", encoding="utf-8")
        self._error = open(os.path.join(log_dir, "error.log"), "a", encoding="utf-8")
        self._file_log = open(os.path.join(log_dir, "file_log.jsonl"), "a", encoding="utf-8")

    @staticmethod
    def _tsv(action: str, middle_path: str, detail: str) -> str:
        return "\t".join([
            datetime.now().isoformat(timespec="seconds"),
            action,
            middle_path,
            (detail or "").replace("\n", " ").replace("\t", " "),
        ]) + "\n"

    def success(self, action: str, middle_path: str, detail: str = "") -> None:
        self._success.write(self._tsv(action, middle_path, detail))

    def error(self, action: str, middle_path: str, detail: str = "") -> None:
        self._error.write(self._tsv(action, middle_path, detail))

    def file_state(self, path: str, mode: str, status: str, in_local: bool,
                   in_remote: bool, action: str, result=None, detail: str = "") -> None:
        record = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "path": path, "mode": mode, "status": status,
            "in_local": in_local, "in_remote": in_remote,
            "action": action, "result": result, "detail": detail,
        }
        self._file_log.write(json.dumps(record, ensure_ascii=False) + "\n")

    def flush(self) -> None:
        self._success.flush()
        self._error.flush()
        self._file_log.flush()

    def close(self) -> None:
        for fh in (self._success, self._error, self._file_log):
            try:
                fh.close()
            except Exception:
                pass

    def __enter__(self) -> "BatchLogWriter":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


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
    def open_batch(repo_root: str, action_folder: str) -> "BatchLogWriter":
        """Open a batched log writer whose handles stay open across a drain."""
        return BatchLogWriter(LoggerService._log_dir(repo_root, action_folder))

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

    @staticmethod
    def log_file_state(
        repo_root: str,
        action_folder: str,
        path: str,
        mode: str,
        status: str,
        in_local: bool,
        in_remote: bool,
        action: str,
        result: Optional[str] = None,
        detail: str = "",
    ) -> None:
        """Append one structured record to file_log.jsonl.

        Call twice per file:
          1. At enqueue time (result=None) — records the decision.
          2. After execution (result='ok'|'error') — records the outcome.
        The jsonl is append-only; callers can correlate by (path, action).
        """
        record = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "path": path,
            "mode": mode,
            "status": status,
            "in_local": in_local,
            "in_remote": in_remote,
            "action": action,
            "result": result,
            "detail": detail,
        }
        log_path = os.path.join(
            LoggerService._log_dir(repo_root, action_folder), "file_log.jsonl"
        )
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    @staticmethod
    def read_file_log(repo_root: str, action_folder: str, limit: int = 2000) -> list:
        """Read up to `limit` most-recent records from file_log.jsonl."""
        log_path = os.path.join(
            QueueService.action_folder_path(repo_root, action_folder),
            "log", "file_log.jsonl",
        )
        if not os.path.exists(log_path):
            return []
        records = []
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return records[-limit:]

    @staticmethod
    def list_action_folders(repo_root: str) -> list:
        """Return action folder names sorted newest-first."""
        root = os.path.join(repo_root, ".fgit", "action")
        if not os.path.isdir(root):
            return []
        folders = [
            e for e in os.listdir(root)
            if os.path.isdir(os.path.join(root, e))
        ]
        return sorted(folders, reverse=True)

    # ---- hook: clean up old action folders ---------------------------

    @staticmethod
    def cleanup_old_actions(repo_root: str, retention_days: int) -> int:
        """Delete action folders older than ``retention_days``. Returns count."""
        root = os.path.join(repo_root, ".fgit", "action")
        if not os.path.isdir(root):
            return 0
        cutoff = datetime.now() - timedelta(days=retention_days)
        removed = 0
        for entry in os.listdir(root):
            entry_path = os.path.join(root, entry)
            if not os.path.isdir(entry_path):
                continue
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
