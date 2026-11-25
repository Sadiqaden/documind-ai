from app.services.chunking import chunk_page, chunk_pages
from app.services.pdf import ExtractedPage


def test_chunks_respect_size_and_cover_text() -> None:
    text = " ".join(f"Sentence number {i} talks about topic {i}." for i in range(80))
    chunks = chunk_page(text, size=200, overlap=40)
    assert len(chunks) > 5
    assert all(len(c) <= 200 for c in chunks)
    joined = " ".join(chunks)
    for i in (0, 40, 79):
        assert f"Sentence number {i} " in joined


def test_overlap_carries_context() -> None:
    text = " ".join(f"Fact {i} is here." for i in range(60))
    chunks = chunk_page(text, size=120, overlap=40)
    # the start of each chunk should repeat words from the end of the previous one
    overlaps = sum(
        1 for a, b in zip(chunks, chunks[1:], strict=False) if b.split()[0] in a.split()[-8:]
    )
    assert overlaps >= len(chunks) // 2


def test_very_long_sentence_is_split() -> None:
    chunks = chunk_page("word " * 1000, size=250, overlap=0)
    assert all(len(c) <= 250 for c in chunks)


def test_chunks_never_span_pages() -> None:
    pages = [ExtractedPage(1, "alpha " * 100), ExtractedPage(2, ""), ExtractedPage(3, "beta " * 10)]
    chunks = chunk_pages(pages, size=200, overlap=20)
    assert {c.page_number for c in chunks} == {1, 3}
    assert all(("alpha" in c.text) != ("beta" in c.text) for c in chunks)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))
