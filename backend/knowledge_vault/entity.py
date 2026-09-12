"""Knowledge Vault — entities."""
from datetime import datetime


class RawFragment:
    """An immutable knowledge fragment as the user entered it. Never edited or
    deleted by the AI (archived instead of deleted)."""

    def __init__(self, id, content, note="", raw_text="", kind="",
                 created_at=None, archived=0, last_accessed=None):
        self.id = id
        self.content = content
        self.note = note
        self.raw_text = raw_text
        self.kind = kind
        self.created_at = created_at
        self.archived = archived
        self.last_accessed = last_accessed
        self.label_ids = []
        self.freshness = "fresh"

    @classmethod
    def new_instance(cls, content, note="", raw_text="", kind=""):
        now = datetime.now().isoformat()
        return cls(None, content, note, raw_text or content, kind,
                   created_at=now, archived=0, last_accessed=None)

    def to_dict(self):
        return {
            "id": self.id, "content": self.content, "note": self.note,
            "raw_text": self.raw_text, "kind": self.kind,
            "created_at": self.created_at, "archived": self.archived,
            "last_accessed": self.last_accessed,
            "label_ids": self.label_ids,
            "freshness": self.freshness,
        }

    @staticmethod
    def from_row(r):
        return RawFragment(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7])
