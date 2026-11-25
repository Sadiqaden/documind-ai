from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.container import Container, build_container
from app.main import create_app
from app.services.demo import seed_demo_documents
from tests.conftest import COFFEE_PAGES, SOLAR_PAGES, make_pdf


@pytest.fixture
def demo_settings(settings: Settings, tmp_path: Path) -> Settings:
    docs = tmp_path / "demo_docs"
    docs.mkdir()
    (docs / "solar.pdf").write_bytes(make_pdf(SOLAR_PAGES))
    (docs / "coffee.pdf").write_bytes(make_pdf(COFFEE_PAGES))
    (docs / "notes.txt").write_text("ignored")
    settings.demo_mode = True
    settings.demo_docs_dir = docs
    settings.demo_rate_limit_per_minute = 100
    return settings


@pytest.fixture
def demo_container(demo_settings: Settings) -> Container:
    return build_container(demo_settings)


@pytest.fixture
def demo_client(demo_settings: Settings, demo_container: Container) -> Iterator[TestClient]:
    with TestClient(create_app(demo_settings, demo_container)) as tc:
        yield tc


def test_seeds_documents_on_startup(demo_client: TestClient) -> None:
    docs = demo_client.get("/api/documents").json()["documents"]
    assert sorted(d["filename"] for d in docs) == ["coffee.pdf", "solar.pdf"]
    assert all(d["status"] == "ready" for d in docs)


def test_seeding_is_idempotent_and_repairs_failed_docs(
    demo_client: TestClient, demo_container: Container
) -> None:
    assert seed_demo_documents(demo_container) == 0
    doc = demo_container.db.list_documents()[0]
    demo_container.db.set_status(doc.id, "failed", "boom")
    assert seed_demo_documents(demo_container) == 1
    assert demo_container.db.get_document(doc.id).status == "ready"  # type: ignore[union-attr]
    assert len(demo_container.db.list_documents()) == 2


def test_changed_demo_file_is_reindexed(
    demo_client: TestClient, demo_container: Container, demo_settings: Settings
) -> None:
    new_pages = ["Coffee guide v2.", "Cold brew steeps for 12 to 18 hours."]
    (demo_settings.demo_docs_dir / "coffee.pdf").write_bytes(make_pdf(new_pages))
    assert seed_demo_documents(demo_container) == 1
    hits = demo_container.retriever.retrieve("cold brew steeping hours", top_k=1)
    assert hits[0].document_name == "coffee.pdf" and hits[0].page_number == 2
    assert len(demo_container.db.list_documents()) == 2


def test_missing_demo_dir_does_not_crash(settings: Settings, tmp_path: Path) -> None:
    settings.demo_mode = True
    settings.demo_docs_dir = tmp_path / "nope"
    assert seed_demo_documents(build_container(settings)) == 0


def test_library_is_read_only(demo_client: TestClient) -> None:
    doc_id = demo_client.get("/api/documents").json()["documents"][0]["id"]
    r = demo_client.post(
        "/api/documents", files={"file": ("x.pdf", make_pdf(["hi"]), "application/pdf")}
    )
    assert r.status_code == 403 and "read-only demo" in r.json()["detail"]
    assert demo_client.delete(f"/api/documents/{doc_id}").status_code == 403
    assert demo_client.post(f"/api/documents/{doc_id}/reindex").status_code == 403
    assert len(demo_client.get("/api/documents").json()["documents"]) == 2
    # reading and opening PDFs still works
    assert demo_client.get(f"/api/documents/{doc_id}/file").status_code == 200


def test_health_reports_demo_settings(demo_client: TestClient) -> None:
    h = demo_client.get("/api/health").json()
    assert h["demo_mode"] is True and h["suggested_questions"]
    assert h["limits"]["max_question_chars"] == 500
    assert h["limits"]["rate_limit_per_minute"] == 100
    assert h["limits"]["daily_questions_remaining"] == 200


def test_daily_question_cap(demo_client: TestClient, demo_container: Container) -> None:
    assert demo_container.daily_quota is not None
    demo_container.daily_quota.limit = 2
    codes = [
        demo_client.post("/api/chat", json={"question": "espresso time"}).status_code
        for _ in range(3)
    ]
    assert codes == [200, 200, 429]
    assert demo_client.get("/api/health").json()["limits"]["daily_questions_remaining"] == 0


def test_invalid_questions_do_not_use_quota(
    demo_client: TestClient, demo_container: Container
) -> None:
    assert demo_client.post("/api/chat", json={"question": "x" * 600}).status_code == 422
    assert demo_container.daily_quota is not None
    assert demo_container.daily_quota.remaining == 200


def test_demo_caps_agent_steps(demo_settings: Settings) -> None:
    demo_settings.agent_max_steps = 8
    assert demo_settings.effective_agent_steps == 3
    demo_settings.demo_mode = False
    assert demo_settings.effective_agent_steps == 8


def test_non_demo_has_no_quota(container: Container, client: TestClient) -> None:
    assert container.daily_quota is None
    assert client.get("/api/health").json()["demo_mode"] is False
