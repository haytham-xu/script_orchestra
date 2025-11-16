
from typing import Dict, List, Optional

class Tag:
    def __init__(self,
                 auth=None,
                 name=None,
                 category_main="",
                 category_sub="",
                 custom=None,
                 mosaic:str = None,
                 others=None):
        self.auth: List[str] = auth or []
        self.name: List[str] = name or []
        self.category_main: str = category_main
        self.category_sub: str = category_sub
        self.custom: List[str] = custom or []
        self.mosaic: str = mosaic
        self.others: List[str] = others or []

    def to_dict(self):
        return {
            "auth": self.auth,
            "name": self.name,
            "category_main": self.category_main,
            "category_sub": self.category_sub,
            "custom": self.custom,
            "mosaic": self.mosaic,
            "others": self.others,
        }

    @staticmethod
    def from_dict(d: Dict):
        return Tag(
            d.get("auth", []),
            d.get("name", []),
            d.get("category_main", ""),
            d.get("category_sub", ""),
            d.get("custom", []),
            d.get("mosaic", None),
            d.get("others", []),
        )


