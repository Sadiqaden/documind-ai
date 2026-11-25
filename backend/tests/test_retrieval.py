from app.container import Container
from app.services.embeddings import HashingEmbedder


def test_hashing_embedder_is_normalised_and_deterministic() -> None:
    e = HashingEmbedder()
    a, b = e.embed_query("battery storage"), e.embed_query("battery storage")
    assert abs(float((a * a).sum()) - 1.0) < 1e-5
    assert (a == b).all()
    sim_related = float(a @ e.embed_query("batteries for storage of solar power"))
    sim_unrelated = float(a @ e.embed_query("espresso grinder"))
    assert sim_related > sim_unrelated


def test_retrieves_correct_document_and_page(container: Container, indexed: dict[str, str]) -> None:
    hits = container.retriever.retrieve("monocrystalline panel efficiency percent", top_k=3)
    assert hits[0].document_name == "solar.pdf"
    assert hits[0].page_number == 2

    hits = container.retriever.retrieve("how long should espresso extraction take", top_k=3)
    assert hits[0].document_name == "coffee.pdf"
    assert hits[0].page_number == 1

    hits = container.retriever.retrieve("lithium battery charge cycles", top_k=3)
    assert (hits[0].document_name, hits[0].page_number) == ("solar.pdf", 3)


def test_document_filter(container: Container, indexed: dict[str, str]) -> None:
    hits = container.retriever.retrieve(
        "panel efficiency", top_k=5, document_ids=[indexed["coffee"]]
    )
    assert hits and all(h.document_id == indexed["coffee"] for h in hits)


def test_min_score_filters_irrelevant(container: Container, indexed: dict[str, str]) -> None:
    hits = container.retriever.retrieve(
        "quantum chromodynamics gluon", top_k=5, min_score=container.settings.min_relevance
    )
    assert hits == []


def test_deleted_documents_disappear_from_index(
    client,
    container: Container,  # type: ignore[no-untyped-def]
    indexed: dict[str, str],
) -> None:
    assert client.delete(f"/api/documents/{indexed['solar']}").status_code == 204
    hits = container.retriever.retrieve("monocrystalline panel efficiency", top_k=5)
    assert all(h.document_name != "solar.pdf" for h in hits)
