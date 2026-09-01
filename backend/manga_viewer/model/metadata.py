from typing import List, Dict

class Metadata:
    def __init__(self, auth=None, category_main=None, category_sub=None,
                 total_folders=0, total_files=0, total_size=0):
        self.auth: List[str] = auth or []
        self.category_main: List[str] = category_main or []
        self.category_sub: List[str] = category_sub or []
        self.total_folders: int = total_folders
        self.total_files: int = total_files
        self.total_size: int = total_size

    def to_dict(self):
        return {
            "auth": self.auth,
            "category_main": self.category_main,
            "category_sub": self.category_sub,
            "total_folders": self.total_folders,
            "total_files": self.total_files,
            "total_size": self.total_size,
        }

    @staticmethod
    def from_dict(d: Dict):
        return Metadata(
            d.get("auth", []),
            d.get("category_main", []),
            d.get("category_sub", []),
            d.get("total_folders", 0),
            d.get("total_files", 0),
            d.get("total_size", 0),
        )
