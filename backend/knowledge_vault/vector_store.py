"""Knowledge Vault — vector store abstraction.

VectorStore is the interface; SqliteVectorStore keeps embeddings in the
project's SQLite (vectors stored via repository, cosine similarity computed
in memory). Fine for thousands of fragments. To scale, add a ChromaVectorStore
implementing the same interface — business code (query_service/builder) won't
change.
"""
from typing import List, Tuple

from . import repository


class VectorStore:
    def add(self, fragment_id: int, vector: List[float]) -> None:
        raise NotImplementedError

    def search(self, query_vec: List[float], top_k: int) -> List[Tuple[int, float]]:
        """Return [(fragment_id, similarity)] sorted desc."""
        raise NotImplementedError


def _cosine(a: List[float], b: List[float]) -> float:
    # embeddings are L2-normalized by the embedder, so dot == cosine.
    n = min(len(a), len(b))
    return sum(a[i] * b[i] for i in range(n))


class SqliteVectorStore(VectorStore):
    def add(self, fragment_id: int, vector: List[float]) -> None:
        repository.save_vector(fragment_id, vector)

    def search(self, query_vec: List[float], top_k: int) -> List[Tuple[int, float]]:
        scored = [(fid, _cosine(query_vec, vec))
                  for fid, vec in repository.get_all_vectors()]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]


# Default store; swap here to change backends project-wide.
_store: VectorStore = SqliteVectorStore()


def get_store() -> VectorStore:
    return _store
