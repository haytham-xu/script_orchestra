"""File-Git cloud storage backends (REQUIREMENTS §3.2)."""
from .base import CloudStorage, FileMeta
from .mock import MockCloudStorage
from .baidu import BaiduCloudStorage

__all__ = ["CloudStorage", "FileMeta", "MockCloudStorage", "BaiduCloudStorage"]
