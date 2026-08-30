"""Knowledge Vault — near-duplicate detection over the raw layer.

Reuses the embeddings already computed for search (zero token cost, offline) to
surface fragments that are near-duplicates — including ones worded differently
(exact matching can't catch those; vectors can). Detection is manual/​on-demand,
never on the ingest path: the raw layer stays append-only.

Pairs are tiered by cosine similarity:
- confident (>= KV_DUP_HIGH): almost certainly the same thing
- fuzzy (KV_DUP_FUZZY_LOW .. KV_DUP_HIGH): likely, but worth an optional AI check

An AI check on the fuzzy band is the ONLY token-spending step and is triggered
separately (see controller). It reuses builder._ai_dedup_batch.
"""
import os

from . import repository
from .vector_store import _cosine

_HIGH = float(os.environ.get("KV_DUP_HIGH", "0.92"))
_FUZZY_LOW = float(os.environ.get("KV_DUP_FUZZY_LOW", "0.85"))


def _pair_dict(a, b, sim: float) -> dict:
    """A suspected-duplicate pair, with both fragments' display fields."""
    return {
        "a": {"id": a.id, "content": a.content, "note": a.note, "kind": a.kind},
        "b": {"id": b.id, "content": b.content, "note": b.note, "kind": b.kind},
        "sim": round(sim, 3),
    }


def find_duplicate_pairs(high: float = None, fuzzy_low: float = None) -> dict:
    """Find near-duplicate fragment pairs from stored vectors. Zero token cost.

    Returns {"confident": [pair...], "fuzzy": [pair...]} sorted by similarity
    desc. Pure local cosine over the in-memory vector set (non-archived only) —
    O(N^2) but on one DB read, no per-pair round-trips.
    """
    high = _HIGH if high is None else high
    fuzzy_low = _FUZZY_LOW if fuzzy_low is None else fuzzy_low

    vecs = repository.get_all_vectors()               # [(fid, [floats])], non-archived
    frag_by_id = {f.id: f for f in repository.get_fragments()}
    # Keep only fragments that still exist (and aren't archived).
    items = [(fid, v) for fid, v in vecs if fid in frag_by_id]

    confident, fuzzy = [], []
    for i in range(len(items)):
        fid_a, va = items[i]
        for j in range(i + 1, len(items)):
            fid_b, vb = items[j]
            sim = _cosine(va, vb)
            if sim < fuzzy_low:
                continue
            pair = _pair_dict(frag_by_id[fid_a], frag_by_id[fid_b], sim)
            (confident if sim >= high else fuzzy).append(pair)

    confident.sort(key=lambda p: p["sim"], reverse=True)
    fuzzy.sort(key=lambda p: p["sim"], reverse=True)
    return {"confident": confident, "fuzzy": fuzzy}
