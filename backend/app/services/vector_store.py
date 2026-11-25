"""Local in-memory vector index backed by SQLite.

Vectors are persisted in the ``chunks`` table; this class keeps a normalised numpy matrix in
memory and rebuilds it lazily whenever the index changes. Suitable for development and small
corpora (tens of thousands of chunks). Swap for pgvector/Qdrant/etc. for larger deployments.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

import numpy as np

from app.db import ChunkRow, Database
from app.services.embeddings import tokenize


@dataclass(frozen=True)
class SearchHit:
    chunk: ChunkRow
    score: float
    vector_score: float
    keyword_score: float


class VectorStore:
    def __init__(self, db: Database, keyword_weight: float = 0.3) -> None:
        self._db = db
        self._lock = threading.Lock()
        self._dirty = True
        self._chunks: list[ChunkRow] = []
        self._matrix: np.ndarray | None = None
        self._token_sets: list[frozenset[str]] = []
        self.keyword_weight = keyword_weight

    def invalidate(self) -> None:
        with self._lock:
            self._dirty = True

    def _ensure_loaded(self) -> None:
        with self._lock:
            if not self._dirty:
                return
            chunks = self._db.all_chunks()
            dims = {c.embedding.shape[0] for c in chunks}
            if len(dims) > 1:
                # Mixed embedding models (provider changed without re-index): keep the majority
                # dimension so search still works; stale docs are flagged in the API.
                majority = max(dims, key=lambda d: sum(c.embedding.shape[0] == d for c in chunks))
                chunks = [c for c in chunks if c.embedding.shape[0] == majority]
            self._chunks = chunks
            self._matrix = np.vstack([c.embedding for c in chunks]) if chunks else None
            self._token_sets = [frozenset(tokenize(c.text)) for c in chunks]
            self._dirty = False

    def search(
        self, query_vec: np.ndarray, query_text: str, top_k: int, document_ids: set[str] | None
    ) -> list[SearchHit]:
        self._ensure_loaded()
        matrix = self._matrix
        if matrix is None or matrix.shape[1] != query_vec.shape[0]:
            return []
        vec_scores = matrix @ query_vec
        q_tokens = set(tokenize(query_text))
        hits: list[SearchHit] = []
        for i, chunk in enumerate(self._chunks):
            if document_ids is not None and chunk.document_id not in document_ids:
                continue
            kw = len(q_tokens & self._token_sets[i]) / len(q_tokens) if q_tokens else 0.0
            vs = max(float(vec_scores[i]), 0.0)
            score = (1 - self.keyword_weight) * vs + self.keyword_weight * kw
            hits.append(SearchHit(chunk=chunk, score=score, vector_score=vs, keyword_score=kw))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]

    @property
    def size(self) -> int:
        self._ensure_loaded()
        return len(self._chunks)
