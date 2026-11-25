"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import chat, documents
from app.config import Settings, get_settings
from app.container import Container, build_container
from app.schemas import HealthResponse
from app.services.demo import DEMO_QUESTIONS, seed_demo_documents

# Same policy as the nginx config used by docker-compose.
PAGE_SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "frame-ancestors 'self'"
    ),
    "X-Frame-Options": "SAMEORIGIN",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("documind")


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        c = container or build_container(settings)
        app.state.container = c
        # Documents left mid-index by a crash/restart would otherwise stay "processing" forever.
        for d in c.db.list_documents():
            if d.status == "processing":
                c.db.set_status(d.id, "failed", "Indexing was interrupted; please re-index.")
        if c.settings.demo_mode:
            seed_demo_documents(c)
        yield
        c.db.close()

    app = FastAPI(title="DocuMind AI", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Any:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error."})

    app.include_router(documents.router)
    app.include_router(chat.router)

    @app.get("/api/health", response_model=HealthResponse, tags=["meta"])
    def health(request: Request) -> HealthResponse:
        c: Container = request.app.state.container
        s = c.settings
        return HealthResponse(
            status="ok",
            llm_provider=s.llm_provider,
            llm_configured=s.llm_configured,
            model=s.anthropic_model if s.llm_provider == "anthropic" else None,
            embedding_model=c.embedder.name,
            documents=len(c.db.list_documents()),
            indexed_chunks=c.store.size,
            demo_mode=s.demo_mode,
            suggested_questions=DEMO_QUESTIONS if s.demo_mode else [],
            limits={
                "max_upload_mb": s.max_upload_mb,
                "max_pages": s.max_pages,
                "max_question_chars": s.effective_question_chars,
                "rate_limit_per_minute": s.effective_rate_limit,
                **({"daily_questions_remaining": c.daily_quota.remaining} if c.daily_quota else {}),
            },
        )

    if settings.frontend_dist_dir is not None:
        mount_frontend(app, settings.frontend_dist_dir)

    return app


def mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve the built React app (single-container mode), with SPA fallback to index.html."""
    root = dist.resolve()
    index = root / "index.html"
    if not index.is_file():
        log.warning("FRONTEND_DIST_DIR=%s has no index.html; not serving the frontend.", dist)
        return
    if (root / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found.")
        target = (root / path).resolve()
        if path and target.is_file() and root in target.parents:
            return FileResponse(target, headers=PAGE_SECURITY_HEADERS)
        return FileResponse(index, headers=PAGE_SECURITY_HEADERS)


app = create_app()
