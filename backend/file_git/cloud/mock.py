"""
MockCloudStorage — a local-filesystem-backed implementation of
CloudStorage for development and unit tests.

Files are stored under a configurable ``base_dir``, mirroring the
"remote path" layout as directories on disk. Path separators are
normalized so tests behave the same on POSIX and Windows.
"""
import os
import shutil
from typing import BinaryIO, Iterator

from .base import CloudStorage, FileMeta


class MockCloudStorage(CloudStorage):
    def __init__(self, base_dir: str):
        self.base_dir = os.path.abspath(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)

    # ---- path helpers -------------------------------------------------

    def _to_local(self, remote_path: str) -> str:
        """Map a remote path (POSIX-style) to a local filesystem path."""
        rel = remote_path.replace('\\', '/').lstrip('/')
        return os.path.join(self.base_dir, *rel.split('/'))

    def _from_local(self, local_path: str) -> str:
        rel = os.path.relpath(local_path, self.base_dir)
        return '/' + rel.replace('\\', '/')

    # ---- CloudStorage impl --------------------------------------------

    def upload(self, source: BinaryIO, remote_path: str, size: int) -> None:
        del size  # unused; kept for interface parity
        target_path = self._to_local(remote_path)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, 'wb') as out:
            shutil.copyfileobj(source, out)

    def download(self, remote_path: str, target: BinaryIO) -> None:
        src = self._to_local(remote_path)
        if not os.path.isfile(src):
            raise FileNotFoundError(f"remote file not found: {remote_path}")
        with open(src, 'rb') as f:
            shutil.copyfileobj(f, target)

    def delete(self, remote_path: str) -> None:
        target = self._to_local(remote_path)
        if os.path.isfile(target):
            os.remove(target)
        elif os.path.isdir(target):
            shutil.rmtree(target)
        # No-op if missing — matches REQUIREMENTS §3.7 semantics
        # (the sync layer treats delete as idempotent).

    def exists(self, remote_path: str) -> bool:
        return os.path.exists(self._to_local(remote_path))

    def list_files(self, remote_prefix: str) -> Iterator[FileMeta]:
        root = self._to_local(remote_prefix)
        if not os.path.isdir(root):
            return
        for cur_dir, _dirs, files in os.walk(root):
            for name in files:
                full = os.path.join(cur_dir, name)
                stat = os.stat(full)
                yield FileMeta(
                    remote_path=self._from_local(full),
                    size=stat.st_size,
                )
