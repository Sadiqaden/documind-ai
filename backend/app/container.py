"""Wires the application's services together (simple dependency container)."""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import Request

from app.config import Settings
from app.db import Database
from app.ratelimit import DailyQuota, RateLimiter
from app.services.embeddings import Embedder, build_embedder
from app.services.indexer import Indexer
from app.services.llm import LLMProvider, build_llm
from app.services.retrieval import Retriever
from app.services.vector_store import VectorStore


@dataclass
class Container:
    settings: Settings
    db: Database
    embedder: Embedder
    store: VectorStore
    retriever: Retriever
    indexer: Indexer
    chat_limiter: RateLimiter
    upload_limiter: RateLimiter
    daily_quota: DailyQuota | None
    _llm: LLMProvider | None = field(default=None, repr=False)
    _llm_built: bool = False

    def llm(self) -> LLMProvider | None:
        """Lazily build the LLM so the app can start (and serve docs) without an API key."""
        if not self._llm_built:
            self._llm = build_llm(self.settings)
            self._llm_built = True
        return self._llm

    def set_llm(self, llm: LLMProvider | None) -> None:
        self._llm, self._llm_built = llm, True


def build_container(settings: Settings, embedder: Embedder | None = None) -> Container:
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    db = Database(settings.db_path)
    emb = embedder or build_embedder(settings.embedding_provider, settings.fastembed_model)
    store = VectorStore(db)
    return Container(
        settings=settings,
        db=db,
        embedder=emb,
        store=store,
        retriever=Retriever(db, emb, store),
        indexer=Indexer(settings, db, emb, store),
        chat_limiter=RateLimiter(settings.effective_rate_limit),
        upload_limiter=RateLimiter(max(5, settings.rate_limit_per_minute // 2)),
        daily_quota=DailyQuota(settings.demo_daily_question_limit) if settings.demo_mode else None,
    )


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container
