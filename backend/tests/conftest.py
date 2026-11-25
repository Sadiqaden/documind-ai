from __future__ import annotations

import io
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.config import Settings
from app.container import Container, build_container
from app.main import create_app
from app.services.llm import LLMResponse


def make_pdf(pages: list[str], encrypt: str | None = None) -> bytes:
    """Build a real PDF with one text block per page."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter, encrypt=encrypt)
    for text in pages:
        y = 740
        for line in text.split("\n"):
            # crude wrapping so long paragraphs stay on the page
            while line:
                c.drawString(60, y, line[:95])
                line = line[95:]
                y -= 14
        c.showPage()
    c.save()
    return buf.getvalue()


SOLAR_PAGES = [
    "Solar Energy Handbook. Introduction to photovoltaic systems and their history.",
    "Photovoltaic panel efficiency. Monocrystalline silicon panels typically reach 20 to 23 "
    "percent efficiency, while polycrystalline panels reach 15 to 17 percent.",
    "Battery storage. Lithium iron phosphate batteries offer around 6000 charge cycles and are "
    "commonly paired with residential solar installations.",
]
COFFEE_PAGES = [
    "Coffee Brewing Guide. Espresso extraction should take 25 to 30 seconds at 9 bar pressure.",
    "Grinding. A burr grinder produces a more uniform particle size than a blade grinder.",
]


class FakeLLM:
    """Scriptable LLM: pass a list of responses or a function(system, messages, tools)."""

    name = "fake"

    def __init__(self, script: list[LLMResponse] | Callable[..., LLMResponse]) -> None:
        self.model: str | None = "fake-model"
        self.script = script
        self.calls: list[dict[str, Any]] = []

    def create(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.calls.append({"system": system, "messages": list(messages), "tools": tools})
        if callable(self.script):
            return self.script(system, messages, tools)
        return self.script.pop(0)


def text_response(text: str) -> LLMResponse:
    return LLMResponse(
        text=text,
        tool_calls=[],
        stop_reason="end_turn",
        model="fake-model",
        raw_content=[{"type": "text", "text": text}],
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        data_dir=tmp_path / "data",
        llm_provider="extractive",
        anthropic_api_key=None,
        max_upload_mb=1,
        max_pages=50,
        chunk_size=300,
        chunk_overlap=50,
        rate_limit_per_minute=1000,
    )


@pytest.fixture
def container(settings: Settings) -> Iterator[Container]:
    c = build_container(settings)
    yield c


@pytest.fixture
def client(settings: Settings, container: Container) -> Iterator[TestClient]:
    app = create_app(settings, container)
    with TestClient(app) as tc:
        yield tc


def upload(client: TestClient, name: str, data: bytes) -> dict[str, Any]:
    r = client.post("/api/documents", files={"file": (name, data, "application/pdf")})
    assert r.status_code == 202, r.text
    return r.json()


@pytest.fixture
def indexed(client: TestClient) -> dict[str, str]:
    solar = upload(client, "solar.pdf", make_pdf(SOLAR_PAGES))
    coffee = upload(client, "coffee.pdf", make_pdf(COFFEE_PAGES))
    return {"solar": solar["id"], "coffee": coffee["id"]}
