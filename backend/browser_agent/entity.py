"""Browser Agent — data entities for the download queue.

Ported from the 2023 browser_plugin prototype.
"""
from datetime import datetime
from enum import Enum


class Status(Enum):
    TODO = 'TODO'
    IN_PROGRESS = 'IN_PROGRESS'
    FAILED = 'FAILED'
    COMPLETED = 'COMPLETED'


class BrowserTab:
    def __init__(self, id, code, created_at, updated_at, status, retry_times,
                 file_name, size, download_link):
        self.id = id
        self.code = code
        self.created_at = created_at
        self.updated_at = updated_at
        self.status = status            # stored as the string value (Status.*.value)
        self.retry_times = retry_times
        self.file_name = file_name
        self.size = size
        self.download_link = download_link

    @classmethod
    def new_instance(cls, code, file_name, size, download_link):
        return cls(None, code, datetime.now(), datetime.now(),
                   Status.TODO.value, 0, file_name, size, download_link)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "code": self.code,
            "created_at": str(self.created_at),
            "updated_at": str(self.updated_at),
            "status": self.status,
            "retry_times": self.retry_times,
            "file_name": self.file_name,
            "size": self.size,
            "download_link": self.download_link,
        }
