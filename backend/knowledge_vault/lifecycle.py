"""Knowledge Vault — lifecycle (freshness) management.

Marks knowledge nodes by how recently their source fragments were accessed.
URLs age faster than commands. Pure local heuristics — no AI, no network.
"""
import json
from datetime import datetime, date

from . import repository, settings_manager

# Kind-specific decay: how many days until a kind is considered "aging".
_AGING_DAYS = {"url": 45, "link": 45, "command": 120, "script": 120}
_DEFAULT_AGING = 90


def _days_since(iso: str) -> int:
    if not iso:
        return 10**6
    try:
        d = datetime.fromisoformat(iso).date()
        return (date.today() - d).days
    except ValueError:
        return 10**6


def recompute_freshness() -> dict:
    """Recompute freshness for every node. Returns counts by bucket."""
    settings = settings_manager.load_settings()
    stale_days = settings.get("stale_days", 90)
    frag_by_id = {f.id: f for f in repository.get_fragments(include_archived=True)}
    counts = {"fresh": 0, "aging": 0, "stale": 0}

    for node in repository.get_nodes():
        fids = json.loads(node.fragment_ids or "[]")
        # A node's recency = most recently touched source fragment.
        recency = 10**6
        kind = node.kind or ""
        for fid in fids:
            f = frag_by_id.get(fid)
            if not f:
                continue
            kind = kind or f.kind
            recency = min(recency, _days_since(f.last_accessed or f.created_at))

        aging_at = _AGING_DAYS.get(kind, _DEFAULT_AGING)
        if recency >= stale_days:
            bucket = "stale"
        elif recency >= aging_at:
            bucket = "aging"
        else:
            bucket = "fresh"
        repository.set_node_freshness(node.id, bucket)
        counts[bucket] += 1
    return counts


def stale_nodes() -> list:
    return [n.to_dict() for n in repository.get_nodes() if n.freshness == "stale"]
