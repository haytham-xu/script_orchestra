
from typing import Dict, List

class Metadata:
    def __init__(self, auth=None, category_main=None, category_sub=None):
        self.auth: List[str] = auth or []
        self.category_main: List[str] = category_main or []
        self.category_sub: List[str] = category_sub or []

    def to_dict(self):
        return {
            "auth": self.auth,
            "category_main": self.category_main,
            "category_sub": self.category_sub,
        }

    @staticmethod
    def from_dict(d: Dict):
        return Metadata(d.get("auth", []), d.get("category_main", []), d.get("category_sub", []))
