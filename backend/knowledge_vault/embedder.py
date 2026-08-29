"""Knowledge Vault — text embedding via sentence-transformers.

The model is loaded lazily on first use (it's a multi-hundred-MB download /
load) so it never slows app startup or other tools. Once cached locally we run
in offline mode: otherwise sentence-transformers revalidates each model file
against huggingface.co on every load, which stalls for minutes (or forever)
when the network can't reach HF.
"""
import os
from typing import List, Optional

from . import settings_manager

_model = None
_model_name: Optional[str] = None


def _get_model():
    global _model, _model_name
    want = settings_manager.load_settings().get("embed_model", "<embed-model>")
    if _model is None or _model_name != want:
        # Use the local HF cache only — no network round-trips on load.
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(want)
        _model_name = want
    return _model


def embed(text: str) -> List[float]:
    model = _get_model()
    vec = model.encode(text or "", normalize_embeddings=True)
    return [float(x) for x in vec]


def embed_many(texts: List[str]) -> List[List[float]]:
    model = _get_model()
    vecs = model.encode(texts, normalize_embeddings=True)
    return [[float(x) for x in v] for v in vecs]
