"""Knowledge Vault — query service.

Vector recall: embed query/fragments with sentence-transformers, store in the
fragment_vector SQLite table, cosine-search in memory.
"""
import json
import math
from typing import List, Dict, Tuple, Optional

from . import repository, settings_manager

# ---- lazy embedder -------------------------------------------------------

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer  # type: ignore
        name = settings_manager.load_settings().get("embed_model", "").strip()
        if not name:
            raise RuntimeError("embed_model is not configured in knowledge_vault settings")
        _model = SentenceTransformer(name)
    return _model


def _embed(text: str) -> List[float]:
    import numpy as np  # type: ignore
    vec = _get_model().encode(text, normalize_embeddings=True)
    return vec.tolist()


# ---- vector store (in-memory cosine over fragment_vector table) ----------

def _load_vectors() -> List[Tuple[int, List[float]]]:
    return repository.get_all_vectors()


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _search_vectors(qvec: List[float], top_k: int) -> List[Tuple[int, float]]:
    scored = [(_cosine(qvec, vec), fid) for fid, vec in _load_vectors()]
    scored.sort(reverse=True)
    return [(fid, score) for score, fid in scored[:top_k]]


# ---- public API ----------------------------------------------------------

def index_fragment(fragment_id: int, text: str) -> None:
    """Embed text and store its vector."""
    vec = _embed(text)
    repository.save_vector(fragment_id, vec)


def search(query: str, top_k: int = 10) -> List[Dict]:
    """Vector recall over fragments. Returns fragment dicts + similarity."""
    if not query.strip():
        return []
    qvec = _embed(query)
    hits = _search_vectors(qvec, top_k)
    results = []
    for fid, score in hits:
        frag = repository.get_fragment(fid)
        if frag and not frag.archived:
            d = frag.to_dict()
            d["score"] = round(score, 4)
            results.append(d)
    return results


def find_duplicate_pairs(high: Optional[float] = None,
                         fuzzy_low: Optional[float] = None) -> dict:
    """Near-duplicate fragment pairs from stored vectors. Zero token cost."""
    _high = high if high is not None else 0.97
    _low = fuzzy_low if fuzzy_low is not None else 0.85
    vecs = _load_vectors()
    exact, fuzzy = [], []
    for i in range(len(vecs)):
        fid_a, va = vecs[i]
        for j in range(i + 1, len(vecs)):
            fid_b, vb = vecs[j]
            score = _cosine(va, vb)
            if score >= _high:
                exact.append({"fragment_a": fid_a, "fragment_b": fid_b, "score": round(score, 4)})
            elif score >= _low:
                fuzzy.append({"fragment_a": fid_a, "fragment_b": fid_b, "score": round(score, 4)})
    return {"exact": exact, "fuzzy": fuzzy}
