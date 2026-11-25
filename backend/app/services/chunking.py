"""Page-aware chunking. Chunks never span pages, so every chunk maps to exactly one page."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.pdf import ExtractedPage

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n{2,}")


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    page_number: int
    text: str


def _split_long(segment: str, size: int) -> list[str]:
    words = segment.split()
    out: list[str] = []
    cur: list[str] = []
    length = 0
    for w in words:
        if length + len(w) + 1 > size and cur:
            out.append(" ".join(cur))
            cur, length = [], 0
        cur.append(w)
        length += len(w) + 1
    if cur:
        out.append(" ".join(cur))
    return out


def chunk_page(text: str, size: int, overlap: int) -> list[str]:
    """Greedy sentence packing up to `size` chars with ~`overlap` chars of trailing context."""
    if not text.strip():
        return []
    overlap = min(overlap, size // 2)
    segments: list[str] = []
    for seg in _SENTENCE_SPLIT.split(text):
        seg = " ".join(seg.split())
        if not seg:
            continue
        segments.extend(_split_long(seg, size) if len(seg) > size else [seg])

    chunks: list[str] = []
    cur = ""
    for seg in segments:
        candidate = f"{cur} {seg}".strip()
        if len(candidate) <= size or not cur:
            cur = candidate
            continue
        chunks.append(cur)
        tail = cur[-overlap:] if overlap else ""
        if tail and " " in tail:
            tail = tail[tail.index(" ") + 1 :]  # start overlap on a word boundary
        cur = f"{tail} {seg}".strip() if tail else seg
        if len(cur) > size:  # overlap pushed us over; drop it
            cur = seg
    if cur:
        chunks.append(cur)
    return chunks


def chunk_pages(pages: list[ExtractedPage], size: int, overlap: int) -> list[Chunk]:
    out: list[Chunk] = []
    for page in pages:
        for text in chunk_page(page.text, size, overlap):
            out.append(Chunk(ordinal=len(out), page_number=page.page_number, text=text))
    return out
