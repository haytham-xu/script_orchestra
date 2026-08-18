"""
ActionExecutor — process a single queue item (REQUIREMENTS §3.7, §3.10).

Given a repo context (root, mode, key, CloudStorage) and one QueueItem,
run its ``action`` (UPLOAD / DOWNLOAD / LOCAL_DELETE / REMOTE_DELETE):

    * UPLOAD:        local → optional encrypt → buffer → cloud.upload
                     → clear buffer entry
    * DOWNLOAD:      cloud.download → buffer → optional decrypt → local
                     → clear buffer entry
    * LOCAL_DELETE:  move local file to .fgit/trash/<date>/
    * REMOTE_DELETE: cloud.delete(encoded_path)

Failures are captured, converted to error log entries by the caller
(``run`` returns the outcome; caller writes to LoggerService).

The BUFFER usage is what enables resumable sync (REQUIREMENTS §3.6):
    * Encryption writes into buffer BEFORE the upload attempt
    * On crash + resume, the encrypted file already exists → skip
      the encrypt step, just upload it
    * Download similarly: keep buffer copy until decryption succeeds
"""
from __future__ import annotations

import io
import os
import shutil
from dataclasses import dataclass
from typing import Optional

from ..cloud.base import CloudStorage
from ..crypto import AesGcmDecryptStream, AesGcmEncryptStream
from .queue_service import ActionType, QueueItem
from .trash_service import TrashService


BUFFER_DIRNAME = "buffer"


@dataclass
class ActionOutcome:
    ok: bool
    detail: str = ""


class ActionExecutor:
    """Stateless executor. Failures return ok=False + detail rather
    than raising; the caller (queue driver) decides whether to log,
    retry, or abort."""

    def __init__(
        self,
        repo_root: str,
        mode: str,
        storage: CloudStorage,
        remote_root: str,
        key: Optional[bytes] = None,
    ):
        self.repo_root = repo_root
        self.mode = mode
        self.storage = storage
        self.remote_root = remote_root.rstrip("/")
        self.key = key
        if mode == "ENCRYPTED" and key is None:
            raise ValueError("ENCRYPTED mode requires a derived key")

    # ---- path helpers -------------------------------------------------

    def _local_path(self, middle_path: str) -> str:
        return os.path.join(self.repo_root, *middle_path.split("/"))

    def _buffer_path(self, encoded_path: str) -> str:
        return os.path.join(
            self.repo_root, ".fgit", BUFFER_DIRNAME, *encoded_path.split("/")
        )

    def _remote_full(self, encoded_path: str) -> str:
        return f"{self.remote_root}/{encoded_path.lstrip('/')}"

    # ---- dispatch -----------------------------------------------------

    def execute(self, item: QueueItem) -> ActionOutcome:
        action = item.get("action")
        try:
            if action == ActionType.UPLOAD.value:
                return self._upload(item)
            if action == ActionType.DOWNLOAD.value:
                return self._download(item)
            if action == ActionType.LOCAL_DELETE.value:
                return self._local_delete(item)
            if action == ActionType.REMOTE_DELETE.value:
                return self._remote_delete(item)
            return ActionOutcome(False, f"unknown action: {action!r}")
        except Exception as exc:
            return ActionOutcome(False, f"{type(exc).__name__}: {exc}")

    # ---- actions ------------------------------------------------------

    def _upload(self, item: QueueItem) -> ActionOutcome:
        middle_path = item["middle_path"]
        encoded_path = item["encoded_path"]
        local_full = self._local_path(middle_path)
        if not os.path.isfile(local_full):
            return ActionOutcome(False, f"local file missing: {middle_path}")

        buffer_full = self._buffer_path(encoded_path)

        # Step 1: prepare payload in buffer (encrypt on demand).
        # If already present (crash-resume), skip re-encrypt.
        if self.mode == "ENCRYPTED":
            if not os.path.isfile(buffer_full):
                os.makedirs(os.path.dirname(buffer_full), exist_ok=True)
                with open(local_full, "rb") as src, open(buffer_full, "wb") as dst:
                    enc = AesGcmEncryptStream(src, self.key)  # type: ignore[arg-type]
                    shutil.copyfileobj(enc, dst)
            upload_source_path = buffer_full
        else:
            # ORIGINAL: upload from local directly (no buffer needed)
            upload_source_path = local_full

        # Step 2: upload
        size = os.path.getsize(upload_source_path)
        with open(upload_source_path, "rb") as src:
            self.storage.upload(src, self._remote_full(encoded_path), size)

        # Step 3: clear buffer entry (ENCRYPTED only)
        if self.mode == "ENCRYPTED" and os.path.isfile(buffer_full):
            os.remove(buffer_full)
            self._prune_empty_dirs(os.path.dirname(buffer_full))

        return ActionOutcome(True, f"uploaded {size} bytes")

    def _download(self, item: QueueItem) -> ActionOutcome:
        middle_path = item["middle_path"]
        encoded_path = item["encoded_path"]
        local_full = self._local_path(middle_path)
        buffer_full = self._buffer_path(encoded_path)

        # Step 1: download ciphertext (or plaintext) to buffer
        # If already present, skip re-download.
        if self.mode == "ENCRYPTED":
            if not os.path.isfile(buffer_full):
                os.makedirs(os.path.dirname(buffer_full), exist_ok=True)
                with open(buffer_full, "wb") as dst:
                    self.storage.download(self._remote_full(encoded_path), dst)

            # Step 2: decrypt to local
            os.makedirs(os.path.dirname(local_full), exist_ok=True)
            with open(buffer_full, "rb") as src, open(local_full, "wb") as dst:
                dec = AesGcmDecryptStream(src, self.key)  # type: ignore[arg-type]
                shutil.copyfileobj(dec, dst)

            # Step 3: clear buffer
            os.remove(buffer_full)
            self._prune_empty_dirs(os.path.dirname(buffer_full))
        else:
            # ORIGINAL: download straight to local
            os.makedirs(os.path.dirname(local_full), exist_ok=True)
            with open(local_full, "wb") as dst:
                self.storage.download(self._remote_full(encoded_path), dst)

        size = os.path.getsize(local_full)
        return ActionOutcome(True, f"downloaded {size} bytes")

    def _local_delete(self, item: QueueItem) -> ActionOutcome:
        middle_path = item["middle_path"]
        moved = TrashService.move_to_trash(self.repo_root, middle_path)
        if moved:
            return ActionOutcome(True, f"trashed → {os.path.relpath(moved, self.repo_root)}")
        return ActionOutcome(True, "local file already missing (idempotent)")

    def _remote_delete(self, item: QueueItem) -> ActionOutcome:
        encoded_path = item["encoded_path"]
        self.storage.delete(self._remote_full(encoded_path))
        return ActionOutcome(True, "removed from cloud")

    # ---- misc ---------------------------------------------------------

    def _prune_empty_dirs(self, path: str) -> None:
        """Walk up from ``path`` removing empty dirs until we hit
        ``.fgit/buffer/`` (which we always keep)."""
        buffer_root = os.path.join(self.repo_root, ".fgit", BUFFER_DIRNAME)
        current = path
        while (
            current
            and os.path.isdir(current)
            and os.path.abspath(current) != os.path.abspath(buffer_root)
        ):
            try:
                os.rmdir(current)
            except OSError:
                return  # non-empty
            current = os.path.dirname(current)
