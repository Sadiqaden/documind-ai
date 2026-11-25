import pytest

from app.services.pdf import (
    PDFValidationError,
    extract_pages,
    safe_display_name,
    validate_pdf_bytes,
)
from tests.conftest import make_pdf


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("report.pdf", "report.pdf"),
        ("../../etc/passwd", "passwd.pdf"),
        ("C:\\evil\\..\\x.PDF", "C_evil_.._x.pdf"),
        ("<script>alert(1)</script>.pdf", "script.pdf"),
        ("résumé 2024.pdf", "resume 2024.pdf"),
        ("", "document.pdf"),
        (None, "document.pdf"),
        ("notes.txt", "notes.txt.pdf"),
    ],
)
def test_safe_display_name(raw: str | None, expected: str) -> None:
    out = safe_display_name(raw)
    assert out == expected
    assert "/" not in out and "\\" not in out


def test_safe_display_name_truncates() -> None:
    assert len(safe_display_name("a" * 500 + ".pdf")) <= 120


def test_validate_rejects_empty_large_and_non_pdf() -> None:
    with pytest.raises(PDFValidationError, match="empty"):
        validate_pdf_bytes(b"", 100)
    with pytest.raises(PDFValidationError, match="limit"):
        validate_pdf_bytes(b"%PDF-" + b"0" * 200, 100)
    with pytest.raises(PDFValidationError, match="not a valid PDF"):
        validate_pdf_bytes(b"<html>hi</html>", 100)
    validate_pdf_bytes(b"%PDF-1.7 ...", 100)


def test_extract_pages_keeps_page_numbers() -> None:
    pages = extract_pages(make_pdf(["first page alpha", "second page beta", "third gamma"]), 10)
    assert [p.page_number for p in pages] == [1, 2, 3]
    assert "beta" in pages[1].text and "gamma" in pages[2].text


def test_extract_rejects_too_many_pages() -> None:
    with pytest.raises(PDFValidationError, match="limit"):
        extract_pages(make_pdf(["x"] * 4), 3)


def test_extract_rejects_textless_pdf() -> None:
    with pytest.raises(PDFValidationError, match="No extractable text"):
        extract_pages(make_pdf(["", ""]), 10)


def test_extract_rejects_corrupt_pdf() -> None:
    with pytest.raises(PDFValidationError):
        extract_pages(b"%PDF-1.4\n garbage garbage", 10)


def test_extract_rejects_password_protected_pdf() -> None:
    with pytest.raises(PDFValidationError, match="Encrypted"):
        extract_pages(make_pdf(["secret text"], encrypt="hunter2"), 10)
