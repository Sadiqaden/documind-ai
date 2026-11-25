"""Query-time retrieval over the vector store, resolving document names."""

from __future__ import annotations

from dataclasses import dataclass

from app.db import Database
from app.services.embeddings import Embedder
from app.services.vector_store import VectorStore


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    document_id: str
    document_name: str
    page_number: int
    text: str
    score: float


class Retriever:
    def __init__(self, db: Database, embedder: Embedder, store: VectorStore) -> None:
        self.db = db
        self.embedder = embedder
        self.store = store

    def retrieve(
        self,
        query: str,
        top_k: int,
        document_ids: list[str] | None = None,
        min_score: float = 0.0,
        relative_cutoff: float = 0.0,
    ) -> list[RetrievedChunk]:
        """Return top_k chunks scoring >= min_score and >= relative_cutoff * best score."""
        ids = set(document_ids) if document_ids else None
        qvec = self.embedder.embed_query(query)
        hits = self.store.search(qvec, query, top_k, ids)
        names = {d.id: d.filename for d in self.db.list_documents()}
        floor = max(min_score, relative_cutoff * hits[0].score) if hits else min_score
        out = []
        for h in hits:
            if h.score < floor or h.chunk.document_id not in names:
                continue
            out.append(
                RetrievedChunk(
                    chunk_id=h.chunk.id,
                    document_id=h.chunk.document_id,
                    document_name=names[h.chunk.document_id],
                    page_number=h.chunk.page_number,
                    text=h.chunk.text,
                    score=h.score,
                )
            )
        return out
