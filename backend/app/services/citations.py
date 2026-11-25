"""Source registry and citation validation.

Every passage shown to the LLM gets a stable label (S1, S2, ...). The model must cite with
``[S#]`` markers. After generation we keep only markers that refer to passages that were actually
provided, strip anything else, and map each surviving label back to the real document name and
page number. The LLM therefore cannot introduce a citation to a document/page it was not shown.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.schemas import Citation

_MARKER = re.compile(r"\[(S\d+(?:\s*,\s*S\d+)*)\]")
_LABEL = re.compile(r"S\d+")


@dataclass
class Source:
    label: str
    chunk_id: str
    document_id: str
    document_name: str
    page_number: int
    text: str
    score: float


@dataclass
class SourceRegistry:
    sources: dict[str, Source] = field(default_factory=dict)
    _by_chunk: dict[str, str] = field(default_factory=dict)

    def add(
        self,
        chunk_id: str,
        document_id: str,
        document_name: str,
        page_number: int,
        text: str,
        score: float,
    ) -> Source:
        if chunk_id in self._by_chunk:
            return self.sources[self._by_chunk[chunk_id]]
        label = f"S{len(self.sources) + 1}"
        src = Source(label, chunk_id, document_id, document_name, page_number, text, score)
        self.sources[label] = src
        self._by_chunk[chunk_id] = label
        return src

    def __len__(self) -> int:
        return len(self.sources)


def format_sources_for_prompt(sources: list[Source]) -> str:
    blocks = []
    for s in sources:
        blocks.append(
            f'<source id="{s.label}" document="{s.document_name}" page="{s.page_number}">\n'
            f"{s.text}\n</source>"
        )
    return "\n\n".join(blocks)


@dataclass(frozen=True)
class ValidatedAnswer:
    text: str
    citations: list[Citation]
    invalid_labels: list[str]


def validate_citations(answer: str, registry: SourceRegistry) -> ValidatedAnswer:
    """Strip unknown citation labels and return citations in order of first use."""
    used: list[str] = []
    invalid: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        labels = _LABEL.findall(match.group(1))
        keep = []
        for lab in labels:
            if lab in registry.sources:
                keep.append(lab)
                if lab not in used:
                    used.append(lab)
            elif lab not in invalid:
                invalid.append(lab)
        return f"[{', '.join(keep)}]" if keep else ""

    cleaned = _MARKER.sub(_replace, answer)
    cleaned = re.sub(r"[ \t]+([.,;:])", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()

    citations = []
    for lab in used:
        s = registry.sources[lab]
        citations.append(
            Citation(
                label=s.label,
                document_id=s.document_id,
                document_name=s.document_name,
                page_number=s.page_number,
                excerpt=s.text[:600],
                score=round(s.score, 4),
            )
        )
    return ValidatedAnswer(text=cleaned, citations=citations, invalid_labels=invalid)
