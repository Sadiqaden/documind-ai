"""PDF validation, safe filenames and page-aware text extraction."""

from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

PDF_MAGIC = b"%PDF-"
_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._ -]+")


class PDFValidationError(ValueError):
    """Raised when an uploaded file is not an acceptable PDF."""


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int  # 1-based
    text: str


def safe_display_name(filename: str | None, max_len: int = 120) -> str:
    """Return a sanitized display filename (no paths, control chars or odd unicode)."""
    name = Path(filename or "document.pdf").name  # strips any directory components
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = _SAFE_CHARS.sub("_", name).strip(" ._") or "document"
    stem, dot, ext = name.rpartition(".")
    if not dot or ext.lower() != "pdf":
        stem, ext = name, "pdf"
    stem = stem[: max_len - 4].rstrip(" ._") or "document"
    return f"{stem}.pdf"


def validate_pdf_bytes(data: bytes, max_bytes: int) -> None:
    if not data:
        raise PDFValidationError("The uploaded file is empty.")
    if len(data) > max_bytes:
        raise PDFValidationError(
            f"File exceeds the {max_bytes / (1024 * 1024):.0f} MB upload limit."
        )
    if not data[:1024].lstrip().startswith(PDF_MAGIC):
        raise PDFValidationError("File is not a valid PDF (missing %PDF header).")


def _clean(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"-\n(?=[a-z])", "", text)  # de-hyphenate line-wrapped words
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pages(source: bytes | Path, max_pages: int) -> list[ExtractedPage]:
    """Extract text per page. Raises PDFValidationError for unreadable/encrypted/oversized PDFs."""
    try:
        stream = io.BytesIO(source) if isinstance(source, bytes) else open(source, "rb")  # noqa: SIM115
        with stream:
            reader = PdfReader(stream)
            if reader.is_encrypted:
                try:
                    if not reader.decrypt(""):
                        raise PDFValidationError("Encrypted PDFs are not supported.")
                except PDFValidationError:
                    raise
                except Exception as exc:
                    raise PDFValidationError("Encrypted PDFs are not supported.") from exc
            n = len(reader.pages)
            if n > max_pages:
                raise PDFValidationError(f"PDF has {n} pages; the limit is {max_pages}.")
            pages: list[ExtractedPage] = []
            for i, page in enumerate(reader.pages, start=1):
                try:
                    raw = page.extract_text() or ""
                except Exception:  # a single malformed page should not kill the document
                    raw = ""
                pages.append(ExtractedPage(page_number=i, text=_clean(raw)))
    except PDFValidationError:
        raise
    except (PdfReadError, ValueError, OSError) as exc:
        raise PDFValidationError(f"Could not read PDF: {exc}") from exc

    if not any(p.text for p in pages):
        raise PDFValidationError(
            "No extractable text found. Scanned/image-only PDFs need OCR, which is not supported."
        )
    return pages
