from fastapi.testclient import TestClient

from app.container import Container
from tests.conftest import SOLAR_PAGES, FakeLLM, make_pdf, text_response, upload


def test_health_does_not_leak_secrets(client: TestClient, container: Container) -> None:
    container.settings.anthropic_api_key = "sk-ant-SECRET"  # type: ignore[assignment]
    r = client.get("/api/health")
    assert r.status_code == 200
    assert "SECRET" not in r.text and "sk-ant" not in r.text
    assert r.json()["limits"]["max_upload_mb"] == 1


def test_upload_list_get_download_delete(client: TestClient) -> None:
    doc = upload(client, "../../My Report.pdf", make_pdf(SOLAR_PAGES))
    assert doc["filename"] == "My Report.pdf"
    listed = client.get("/api/documents").json()["documents"]
    assert len(listed) == 1
    d = client.get(f"/api/documents/{doc['id']}").json()
    assert d["status"] == "ready" and d["page_count"] == 3 and d["chunk_count"] >= 3

    f = client.get(f"/api/documents/{doc['id']}/file")
    assert f.status_code == 200 and f.content.startswith(b"%PDF")
    assert f.headers["content-type"] == "application/pdf"

    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204
    assert client.get(f"/api/documents/{doc['id']}").status_code == 404
    assert client.get("/api/documents").json()["documents"] == []


def test_upload_validation(client: TestClient) -> None:
    r = client.post("/api/documents", files={"file": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 415
    r = client.post("/api/documents", files={"file": ("a.pdf", b"not a pdf", "application/pdf")})
    assert r.status_code == 400
    big = b"%PDF-1.4\n" + b"0" * (1024 * 1024 + 10)
    r = client.post("/api/documents", files={"file": ("big.pdf", big, "application/pdf")})
    assert r.status_code == 413


def test_textless_pdf_is_marked_failed(client: TestClient) -> None:
    doc = upload(client, "blank.pdf", make_pdf(["", ""]))
    d = client.get(f"/api/documents/{doc['id']}").json()
    assert d["status"] == "failed" and "No extractable text" in d["error"]


def test_reindex(client: TestClient, container: Container) -> None:
    doc = upload(client, "solar.pdf", make_pdf(SOLAR_PAGES))
    before = client.get(f"/api/documents/{doc['id']}").json()
    r = client.post(f"/api/documents/{doc['id']}/reindex")
    assert r.status_code == 202
    after = client.get(f"/api/documents/{doc['id']}").json()
    assert after["status"] == "ready" and after["chunk_count"] == before["chunk_count"]
    assert container.store.size == before["chunk_count"]


def test_invalid_ids_return_404(client: TestClient) -> None:
    assert client.get("/api/documents/../../etc").status_code == 404
    assert client.delete("/api/documents/xyz").status_code == 404
    assert client.post("/api/documents/" + "0" * 32 + "/reindex").status_code == 404


def test_chat_requires_documents(client: TestClient) -> None:
    r = client.post("/api/chat", json={"question": "hello"})
    assert r.status_code == 400


def test_chat_extractive_and_llm(
    client: TestClient, container: Container, indexed: dict[str, str]
) -> None:
    r = client.post("/api/chat", json={"question": "espresso extraction seconds"})
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "extractive"
    assert body["citations"][0]["document_name"] == "coffee.pdf"

    container.set_llm(FakeLLM([text_response("It takes 25-30 seconds [S1].")]))
    r = client.post(
        "/api/chat",
        json={
            "question": "espresso extraction seconds",
            "history": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ],
        },
    )
    body = r.json()
    assert body["provider"] == "fake" and body["citations"][0]["page_number"] == 1


def test_chat_validation(client: TestClient, indexed: dict[str, str]) -> None:
    assert client.post("/api/chat", json={"question": ""}).status_code == 422
    assert client.post("/api/chat", json={"question": "x" * 5000}).status_code == 422
    r = client.post("/api/chat", json={"question": "q", "document_ids": ["f" * 32]})
    assert r.status_code == 400


def test_agent_mode_requires_llm(client: TestClient, indexed: dict[str, str]) -> None:
    r = client.post("/api/chat", json={"question": "summarize", "mode": "agent"})
    assert r.status_code == 400


def test_missing_api_key_is_503(
    client: TestClient, container: Container, indexed: dict[str, str]
) -> None:
    container.settings.llm_provider = "anthropic"
    container._llm_built = False
    r = client.post("/api/chat", json={"question": "panel efficiency"})
    assert r.status_code == 503 and "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_rate_limit(client: TestClient, container: Container, indexed: dict[str, str]) -> None:
    container.chat_limiter.limit = 2
    container.chat_limiter.reset()
    codes = [client.post("/api/search", json={"query": "panels"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_search_endpoint(client: TestClient, indexed: dict[str, str]) -> None:
    r = client.post("/api/search", json={"query": "burr grinder particle size", "top_k": 2})
    res = r.json()["results"]
    assert res[0]["document_name"] == "coffee.pdf" and res[0]["page_number"] == 2
