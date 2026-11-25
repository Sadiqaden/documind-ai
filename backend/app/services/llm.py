"""LLM provider abstraction.

``AnthropicLLM`` calls Claude through the official ``anthropic`` SDK. The provider exposes a
single ``create`` method returning a normalised ``LLMResponse`` so the QA pipeline and the
tool-using agent can be unit-tested with a fake provider (no network, no API key).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.config import Settings

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """A provider failure that is safe to surface to the client (no secrets)."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[ToolCall]
    stop_reason: str | None
    model: str | None
    # Content to append verbatim as the assistant turn (keeps thinking/fallback blocks intact).
    raw_content: list[Any] = field(default_factory=list)


class LLMProvider(Protocol):
    name: str
    model: str | None

    def create(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse: ...


class AnthropicLLM:
    name = "anthropic"

    def __init__(self, settings: Settings) -> None:
        import anthropic

        if not settings.anthropic_api_key:
            raise LLMError("ANTHROPIC_API_KEY is not configured on the server.", 503)
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key.get_secret_value(), timeout=120.0, max_retries=2
        )
        self.model: str | None = settings.anthropic_model
        self._effort = settings.anthropic_effort
        self._max_tokens = settings.anthropic_max_tokens
        self._fallback = settings.anthropic_refusal_fallback

    def create(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        a = self._anthropic
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens or self._max_tokens,
            "system": system,
            "messages": messages,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": self._effort},
        }
        if tools:
            kwargs["tools"] = tools
        try:
            if self._fallback:
                resp = self._client.beta.messages.create(
                    betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
                )
            else:
                resp = self._client.messages.create(**kwargs)
        except a.AuthenticationError as exc:
            raise LLMError("The LLM provider rejected the server's API key.", 502) from exc
        except a.PermissionDeniedError as exc:
            raise LLMError("The API key lacks permission for this model.", 502) from exc
        except a.NotFoundError as exc:
            raise LLMError(f"Model '{self.model}' was not found.", 502) from exc
        except a.RateLimitError as exc:
            raise LLMError("LLM provider rate limit hit. Try again soon.", 429) from exc
        except a.BadRequestError as exc:
            log.warning("Anthropic bad request: %s", exc.message)
            raise LLMError("The LLM provider rejected the request.", 502) from exc
        except a.APIStatusError as exc:
            raise LLMError(f"LLM provider error (HTTP {exc.status_code}).", 502) from exc
        except a.APIConnectionError as exc:
            raise LLMError("Could not reach the LLM provider.", 504) from exc

        text_parts: list[str] = []
        calls: list[ToolCall] = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                calls.append(ToolCall(id=block.id, name=block.name, input=dict(block.input)))
        if resp.stop_reason == "refusal":
            text_parts = ["The model declined to answer this request."]
        return LLMResponse(
            text="".join(text_parts).strip(),
            tool_calls=calls,
            stop_reason=resp.stop_reason,
            model=resp.model,
            raw_content=list(resp.content),
        )


def build_llm(settings: Settings) -> LLMProvider | None:
    """Return the configured LLM, or None for the offline extractive mode."""
    if settings.llm_provider == "extractive":
        return None
    return AnthropicLLM(settings)
