"""Knowledge Vault — entities.

Two layers:
  - RawFragment: the immutable, append-only source of truth (user's raw input).
  - KnowledgeNode / Edge: the AI-managed, derived "knowledge network" that can
    be rebuilt from the raw layer at any time.
"""
from datetime import datetime


class RawFragment:
    """An immutable knowledge fragment as the user entered it. Never edited or
    deleted by the AI (archived instead of deleted)."""

    def __init__(self, id, content, note="", raw_text="", kind="",
                 created_at=None, archived=0, last_accessed=None):
        self.id = id
        self.content = content        # the knowledge body (e.g. a URL, a command)
        self.note = note              # user's annotation
        self.raw_text = raw_text      # original pasted blob (unprocessed)
        self.kind = kind              # optional: url|command|script|link|note...
        self.created_at = created_at
        self.archived = archived      # 0/1 — soft "removed" (raw is never hard-deleted)
        self.last_accessed = last_accessed
        self.label_ids = []           # user-managed tag ids (populated on load)
        self.freshness = "fresh"      # fresh|aging|stale — derived (set on load)

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


class KnowledgeNode:
    """A purified node in the AI-managed network. Derived from >=1 fragments."""

    def __init__(self, id, title, summary="", kind="", fragment_ids="",
                 freshness="fresh", updated_at=None):
        self.id = id
        self.title = title
        self.summary = summary
        self.kind = kind
        self.fragment_ids = fragment_ids  # JSON list of source RawFragment ids
        self.freshness = freshness        # fresh | aging | stale
        self.updated_at = updated_at

    def to_dict(self):
        import json
        return {
            "id": self.id, "title": self.title, "summary": self.summary,
            "kind": self.kind,
            "fragment_ids": json.loads(self.fragment_ids or "[]"),
            "freshness": self.freshness, "updated_at": self.updated_at,
        }

    @staticmethod
    def from_row(r):
        return KnowledgeNode(r[0], r[1], r[2], r[3], r[4], r[5], r[6])


class Edge:
    """A relation between two knowledge nodes (AI-inferred)."""

    def __init__(self, id, source_id, target_id, relation="related", weight=1.0):
        self.id = id
        self.source_id = source_id
        self.target_id = target_id
        self.relation = relation      # related | prereq | alternative | same-topic...
        self.weight = weight

    def to_dict(self):
        return {
            "id": self.id, "source_id": self.source_id,
            "target_id": self.target_id, "relation": self.relation,
            "weight": self.weight,
        }

    @staticmethod
    def from_row(r):
        return Edge(r[0], r[1], r[2], r[3], r[4])
