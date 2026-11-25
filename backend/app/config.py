"""Application configuration loaded from environment variables / .env.

Secrets (ANTHROPIC_API_KEY) live only on the backend and are never returned by any endpoint.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    llm_provider: Literal["anthropic", "extractive"] = "anthropic"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    anthropic_max_tokens: int = Field(16000, ge=256, le=64000)
    anthropic_refusal_fallback: bool = True

    embedding_provider: Literal["hash", "fastembed"] = "hash"
    fastembed_model: str = "BAAI/bge-small-en-v1.5"

    max_upload_mb: float = Field(25, gt=0)
    max_pages: int = Field(500, gt=0)
    chunk_size: int = Field(1000, ge=200)
    chunk_overlap: int = Field(150, ge=0)
    top_k: int = Field(6, ge=1, le=20)
    min_relevance: float = Field(0.08, ge=0.0, le=1.0)
    rate_limit_per_minute: int = Field(30, ge=1)
    agent_max_steps: int = Field(5, ge=1, le=10)
    max_question_chars: int = 2000

    # Public demo mode: preloaded sample documents, no uploads/deletes/re-indexing, tighter
    # per-IP limits and a global daily cap on questions (protects your API bill).
    demo_mode: bool = False
    demo_docs_dir: Path = Path("./demo_docs")
    demo_rate_limit_per_minute: int = Field(6, ge=1)
    demo_daily_question_limit: int = Field(200, ge=1)
    demo_max_question_chars: int = Field(500, ge=20)
    demo_agent_max_steps: int = Field(3, ge=1, le=10)

    data_dir: Path = Path("./data")
    # When set (single-container deploys), the backend also serves the built frontend.
    frontend_dist_dir: Path | None = None
    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    @property
    def effective_rate_limit(self) -> int:
        return self.demo_rate_limit_per_minute if self.demo_mode else self.rate_limit_per_minute

    @property
    def effective_question_chars(self) -> int:
        if self.demo_mode:
            return min(self.max_question_chars, self.demo_max_question_chars)
        return self.max_question_chars

    @property
    def effective_agent_steps(self) -> int:
        if self.demo_mode:
            return min(self.agent_max_steps, self.demo_agent_max_steps)
        return self.agent_max_steps

    @property
    def max_upload_bytes(self) -> int:
        return int(self.max_upload_mb * 1024 * 1024)

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "documind.sqlite3"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def llm_configured(self) -> bool:
        if self.llm_provider == "extractive":
            return True
        return bool(self.anthropic_api_key and self.anthropic_api_key.get_secret_value())


@lru_cache
def get_settings() -> Settings:
    return Settings()
