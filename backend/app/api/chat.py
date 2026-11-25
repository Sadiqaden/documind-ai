"""Question answering, agent and raw search endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from app.container import Container, get_container
from app.ratelimit import client_key
from app.schemas import AskRequest, AskResponse, SearchRequest, SearchResponse, SearchResult
from app.services.agent import AgentService
from app.services.llm import LLMError
from app.services.qa import QAService

router = APIRouter(prefix="/api", tags=["chat"])
C = Annotated[Container, Depends(get_container)]


def _validate_ids(ids: list[str] | None, c: Container) -> list[str] | None:
    if not ids:
        return None
    ready = {d.id for d in c.db.list_documents() if d.status == "ready"}
    valid = [i for i in dict.fromkeys(ids) if i in ready]
    if not valid:
        raise HTTPException(status_code=400, detail="None of the selected documents are ready.")
    return valid


@router.post("/chat", response_model=AskResponse)
async def ask(body: AskRequest, request: Request, c: C) -> AskResponse:
    c.chat_limiter.check(client_key(request))
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Question must not be empty.")
    if len(question) > c.settings.effective_question_chars:
        raise HTTPException(
            status_code=422,
            detail=f"Questions are limited to {c.settings.effective_question_chars} characters.",
        )
    if not any(d.status == "ready" for d in c.db.list_documents()):
        raise HTTPException(status_code=400, detail="Upload and index a document first.")
    doc_ids = _validate_ids(body.document_ids, c)
    if c.daily_quota:
        c.daily_quota.consume()

    try:
        llm = c.llm()
    except LLMError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    try:
        if body.mode == "agent":
            if llm is None:
                raise HTTPException(
                    status_code=400, detail="Agent mode requires an LLM provider (Anthropic)."
                )
            agent = AgentService(c.db, c.retriever, llm, c.settings.effective_agent_steps)
            return await run_in_threadpool(agent.run, question, doc_ids, body.history)
        qa = QAService(c.retriever, llm, c.settings.top_k, c.settings.min_relevance)
        return await run_in_threadpool(qa.answer, question, doc_ids, body.history)
    except LLMError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/search", response_model=SearchResponse)
def search(body: SearchRequest, request: Request, c: C) -> SearchResponse:
    c.chat_limiter.check(client_key(request))
    hits = c.retriever.retrieve(body.query, body.top_k, _validate_ids(body.document_ids, c))
    return SearchResponse(
        results=[
            SearchResult(
                chunk_id=h.chunk_id,
                document_id=h.document_id,
                document_name=h.document_name,
                page_number=h.page_number,
                text=h.text,
                score=round(h.score, 4),
            )
            for h in hits
        ]
    )
