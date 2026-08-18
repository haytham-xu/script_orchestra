"""
CloudStorage abstract interface (REQUIREMENTS §3.2).

Every backend (mock, baidu, future) must implement these five methods.
All I/O is stream-based so encryption can pipe read→encrypt→upload
without producing intermediate on-disk copies.
"""
from abc import ABC, abstractmethod
from typing import BinaryIO, Iterator, TypedDict


class FileMeta(TypedDict):
    remote_path: str
    size: int


class CloudStorage(ABC):
    """Contract for a remote file store."""

    @abstractmethod
    def upload(self, source: BinaryIO, remote_path: str, size: int) -> None:
        """Upload a stream to ``remote_path``.

        ``size`` is the total length in bytes so the backend can allocate
        upload sessions or send correct headers. ``source`` is read to EOF.
        Overwrites any existing file at ``remote_path``.
        """

    @abstractmethod
    def download(self, remote_path: str, target: BinaryIO) -> None:
        """Download the file at ``remote_path`` into ``target`` stream."""

    @abstractmethod
    def delete(self, remote_path: str) -> None:
        """Delete the file at ``remote_path``.

        Backends may soft-delete (move to a cloud trash) if the underlying
        service supports it; from the caller's perspective it must be gone.
        """

    @abstractmethod
    def exists(self, remote_path: str) -> bool:
        """Return True iff a file exists at ``remote_path``."""

    @abstractmethod
    def list_files(self, remote_prefix: str) -> Iterator[FileMeta]:
        """Yield metadata for every file under ``remote_prefix`` (recursive)."""
