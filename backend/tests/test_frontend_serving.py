from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.container import build_container
from app.main import create_app


@pytest.fixture
def spa_client(settings: Settings, tmp_path: Path) -> Iterator[TestClient]:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>DocuMind</html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    (dist / "favicon.svg").write_text("<svg/>")
    (tmp_path / "secret.txt").write_text("nope")
    settings.frontend_dist_dir = dist
    with TestClient(create_app(settings, build_container(settings))) as tc:
        yield tc


def test_serves_index_and_assets(spa_client: TestClient) -> None:
    r = spa_client.get("/")
    assert r.status_code == 200 and "DocuMind" in r.text
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert spa_client.get("/assets/app.js").text == "console.log(1)"
    assert spa_client.get("/favicon.svg").status_code == 200


def test_spa_fallback_and_api_untouched(spa_client: TestClient) -> None:
    assert "DocuMind" in spa_client.get("/some/client/route").text
    assert spa_client.get("/api/health").json()["status"] == "ok"
    assert spa_client.get("/api/nope").status_code == 404


def test_no_path_traversal(spa_client: TestClient) -> None:
    r = spa_client.get("/..%2Fsecret.txt")
    assert "nope" not in r.text


def test_not_mounted_by_default(client: TestClient) -> None:
    assert client.get("/").status_code == 404
