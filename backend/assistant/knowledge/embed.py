"""
Local sentence-transformers embedding wrapper.

The model is loaded lazily on first use so server startup stays fast and
the ~500 MB weights only exist in RAM when actually needed.

Vectors are returned L2-normalized (`normalize_embeddings=True`), so
cosine similarity between two vectors is just a dot product.
"""
import logging
import threading
from typing import List, Optional

from .config import EMBEDDING_MODEL

logger = logging.getLogger("assistant.knowledge.embed")

_lock = threading.Lock()
_model = None
_model_name: Optional[str] = None
_dimension: Optional[int] = None


def _load():
    global _model, _model_name, _dimension
    with _lock:
        if _model is not None:
            return _model
        from sentence_transformers import SentenceTransformer
        logger.info(f"[kb] loading embedding model: {EMBEDDING_MODEL}")
        _model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
        _model_name = EMBEDDING_MODEL
        _dimension = int(_model.get_sentence_embedding_dimension())
        logger.info(f"[kb] embedding model loaded, dim={_dimension}")
        return _model


def dimension() -> int:
    if _dimension is None:
        _load()
    return int(_dimension)


def embed_texts(texts: List[str]) -> List[bytes]:
    """
    Encode a batch of strings. Returns each vector as raw float32 bytes so
    it can be blob-stored in SQLite.
    """
    if not texts:
        return []
    import numpy as np

    model = _load()
    vectors = model.encode(
        texts,
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return [v.astype(np.float32).tobytes() for v in vectors]


def embed_query(text: str) -> bytes:
    """Convenience: embed a single query string."""
    return embed_texts([text])[0]
