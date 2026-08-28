"""Knowledge Vault — query service.

Default query is pure vector recall (fast, no AI, no token cost): embed the
query, cosine-search fragment vectors, return the matching raw fragments.
AI deep-answer is a separate, optional path (added with the builder stage).
"""
from typing import List, Dict

from . import repository, embedder
from .vector_store import get_store


def index_fragment(fragment_id: int, text: str) -> None:
    """Embed a fragment's text and store its vector (called on ingest / build)."""
    vec = embedder.embed(text)
    get_store().add(fragment_id, vec)


def search(query: str, top_k: int = 10) -> List[Dict]:
    """Vector recall over fragments. Returns fragment dicts + similarity."""
    if not query.strip():
        return []
    qvec = embedder.embed(query)
    hits = get_store().search(qvec, top_k)
    results = []
    for fid, score in hits:
        frag = repository.get_fragment(fid)
        if frag and not frag.archived:
            d = frag.to_dict()
            d["score"] = round(score, 4)
            results.append(d)
    return results
