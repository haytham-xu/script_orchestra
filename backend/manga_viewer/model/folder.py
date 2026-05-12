
from manga_viewer.model.tag import Tag
from typing import Dict, List

class Folder:
    def __init__(self,
                 id_: str,
                 name: str,
                 path: str,
                 file_list=None,
                 size=0,
                 number=0,
                 initialized=False,
                 tags=None):
        self.id: str = id_
        self.name: str = name
        self.path: str = path
        self.file_list: List[str] = file_list or []
        self.size: int = size
        self.number: int = number
        self.initialized: bool = initialized
        self.tags: Tag = tags or Tag()

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "files": self.file_list,  # Frontend expects 'files', not 'file_list'
            "size": self.size,
            "number": self.number,
            "initialized": self.initialized,
            "tags": self.tags.to_dict(),
        }

    @staticmethod
    def from_dict(d: Dict):
        return Folder(
            d.get("id", ""),
            d.get("name", ""),
            d.get("path", ""),
            d.get("file_list") or d.get("files", []),  # Support both 'file_list' and 'files'
            d.get("size", 0),
            d.get("number", 0),
            d.get("initialized", False),
            Tag.from_dict(d.get("tags", {})),
        )