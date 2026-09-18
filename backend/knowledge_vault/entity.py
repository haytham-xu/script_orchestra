"""Knowledge Vault — entities."""
from datetime import datetime
import json


def _parse_blocks(raw):
    """Return blocks list from stored content string. Old plain-text content is
    wrapped into a single text block so every fragment always has a blocks list."""
    if not raw:
        return [{"type": "text", "body": ""}]
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass
    return [{"type": "text", "body": raw}]


def _blocks_to_storage(blocks):
    """Serialise blocks list to the string stored in the content column."""
    return json.dumps(blocks, ensure_ascii=False)


def _blocks_to_plain(blocks):
    """Plain-text representation used for vector embedding / raw_text."""
    return "\n\n".join(b.get("body", "") for b in blocks if b.get("body"))


class RawFragment:
    """An immutable knowledge fragment as the user entered it."""

    def __init__(self, id, content, note="", raw_text="", kind="",
                 created_at=None, archived=0, last_accessed=None, header=""):
        self.id = id
        # content column stores either JSON blocks or legacy plain text
        self.blocks = _parse_blocks(content)
        self.note = note
        self.raw_text = raw_text
        self.kind = kind
        self.created_at = created_at
        self.archived = archived
        self.last_accessed = last_accessed
        self.header = header
        self.label_ids = []
        self.freshness = "fresh"
        self.group_id = None

    @classmethod
    def new_instance(cls, blocks, note="", raw_text="", kind="", header=""):
        """blocks is a list of {type, body, lang?} dicts."""
        now = datetime.now().isoformat()
        storage = _blocks_to_storage(blocks)
        plain = _blocks_to_plain(blocks)
        return cls(None, storage, note, raw_text or plain, kind,
                   created_at=now, archived=0, last_accessed=None, header=header)

    def content_storage(self):
        """Return the JSON string to write back to the content column."""
        return _blocks_to_storage(self.blocks)

    def to_dict(self):
        return {
            "id": self.id,
            "blocks": self.blocks,
            "note": self.note,
            "raw_text": self.raw_text,
            "kind": self.kind,
            "created_at": self.created_at,
            "archived": self.archived,
            "last_accessed": self.last_accessed,
            "header": self.header,
            "label_ids": self.label_ids,
            "freshness": self.freshness,
            "group_id": self.group_id,
        }

    @staticmethod
    def from_row(r):
        # Columns: id, content, note, raw_text, kind, created_at, archived, last_accessed, header
        return RawFragment(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7],
                           header=r[8] if len(r) > 8 else "")


class FragmentGroup:
    """A nestable folder-like container grouping multiple fragments."""

    def __init__(self, id, name, note="", parent_id=None, created_at=None):
        self.id = id
        self.name = name
        self.note = note
        self.parent_id = parent_id
        self.created_at = created_at

    @classmethod
    def new_instance(cls, name, note="", parent_id=None):
        return cls(None, name, note, parent_id, created_at=datetime.now().isoformat())

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "note": self.note,
            "parent_id": self.parent_id,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_row(r):
        # Columns: id, name, note, parent_id, created_at
        return FragmentGroup(r[0], r[1], r[2], r[3], r[4])
