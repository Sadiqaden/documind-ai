"""Pydantic request/response models (the public API contract)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DocumentOut(BaseModel):
    id: str
    filename: str
    size_bytes: int
    page_count: int
    chunk_count: int
    status: Literal["processing", "ready", "failed"]
    error: str | None = None
    stale_index: bool = False
    created_at: str
    updated_at: str


class DocumentList(BaseModel):
    documents: list[DocumentOut]


class Citation(BaseModel):
    label: str
    document_id: str
    document_name: str
    page_number: int
    excerpt: str
    score: float


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    document_ids: list[str] | None = Field(
        default=None, description="Restrict retrieval to these documents (default: all ready docs)"
    )
    history: list[ChatTurn] = Field(default_factory=list, max_length=12)
    mode: Literal["ask", "agent"] = "ask"


class ToolTrace(BaseModel):
    tool: str
    input: dict[str, object]
    summary: str
    is_error: bool = False


class AskResponse(BaseModel):
    answer: str
    citations: list[Citation]
    insufficient_evidence: bool
    provider: str
    model: str | None = None
    tool_trace: list[ToolTrace] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    document_ids: list[str] | None = None
    top_k: int = Field(6, ge=1, le=20)


class SearchResult(BaseModel):
    chunk_id: str
    document_id: str
    document_name: str
    page_number: int
    text: str
    score: float


class SearchResponse(BaseModel):
    results: list[SearchResult]


class HealthResponse(BaseModel):
    status: str
    llm_provider: str
    llm_configured: bool
    model: str | None
    embedding_model: str
    documents: int
    indexed_chunks: int
    demo_mode: bool = False
    suggested_questions: list[str] = Field(default_factory=list)
    limits: dict[str, float | int]


class ErrorResponse(BaseModel):
    detail: str
