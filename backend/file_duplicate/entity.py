"""
File Duplicate — Entity / data classes
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ScanRoot:
    """A named root directory to scan."""
    id: int
    name: str
    path: str
    priority: int  # lower = higher priority (keep files from this root)
    file_count: int = 0
    indexed_count: int = 0

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'path': self.path,
            'priority': self.priority,
            'file_count': self.file_count,
            'indexed_count': self.indexed_count,
        }


@dataclass
class FileEntry:
    """One file on disk."""
    id: Optional[int]
    root_id: int
    root_path: str           # the scan root this file belongs to
    file_path: str           # absolute path
    relative_path: str       # relative to root_path
    filename: str
    filesize: int
    mtime: float
    partial_hash: Optional[str] = None   # MD5 of first 64 KB
    full_hash: Optional[str] = None      # MD5 of entire file
    hash_status: str = 'pending'         # pending | partial | full

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'root_id': self.root_id,
            'root_path': self.root_path,
            'file_path': self.file_path,
            'relative_path': self.relative_path,
            'filename': self.filename,
            'filesize': self.filesize,
            'mtime': self.mtime,
            'full_hash': self.full_hash,
            'hash_status': self.hash_status,
        }

    @classmethod
    def from_row(cls, row) -> 'FileEntry':
        return cls(
            id=row[0],
            root_id=row[1],
            root_path=row[2],
            file_path=row[3],
            relative_path=row[4],
            filename=row[5],
            filesize=row[6],
            mtime=row[7],
            partial_hash=row[8],
            full_hash=row[9],
            hash_status=row[10],
        )


@dataclass
class DuplicateGroup:
    """A group of files that are exact duplicates."""
    group_hash: str          # the shared full MD5
    filesize: int
    member_count: int
    members: List[dict] = field(default_factory=list)   # list of FileEntry.to_dict()
    root_ids: List[int] = field(default_factory=list)   # which roots have a member

    def to_dict(self) -> dict:
        return {
            'group_hash': self.group_hash,
            'filesize': self.filesize,
            'member_count': self.member_count,
            'members': self.members,
            'root_ids': self.root_ids,
        }
