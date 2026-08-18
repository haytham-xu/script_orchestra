"""File-Git cloud storage backends (REQUIREMENTS §3.2)."""
from .base import CloudStorage, FileMeta
from .mock import MockCloudStorage

__all__ = ["CloudStorage", "FileMeta", "MockCloudStorage"]
