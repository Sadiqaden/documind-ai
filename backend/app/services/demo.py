"""Public demo mode: load the bundled sample PDFs into the library at startup."""

from __future__ import annotations

import logging
import shutil
import uuid
from typing import TYPE_CHECKING

from app.services.pdf import safe_display_name

if TYPE_CHECKING:
    from app.container import Container

log = logging.getLogger(__name__)

# Shown as one-click suggestions in the UI; they match the bundled sample documents.
DEMO_QUESTIONS = [
    "How much is the home office stipend?",
    "What are the security requirements for remote work?",
    "How efficient are monocrystalline solar panels?",
    "What is the payback period for solar panels?",
]


def seed_demo_documents(c: Container) -> int:
    """Index every PDF in ``demo_docs_dir`` that isn't already ready. Returns docs (re)indexed.

    Runs synchronously at startup so the demo is usable as soon as the server accepts traffic.
    Idempotent across restarts: documents are matched by filename. A document is re-indexed when
    it isn't ready, was indexed with a different embedding model, or the PDF on disk changed size
    (e.g. you replaced a sample file).
    """
    src_dir = c.settings.demo_docs_dir
    if not src_dir.is_dir():
        log.warning("DEMO_MODE is on but %s does not exist; the library will be empty.", src_dir)
        return 0
    existing = {d.filename: d for d in c.db.list_documents()}
    count = 0
    for path in sorted(src_dir.glob("*.pdf")):
        name = safe_display_name(path.name)
        doc = existing.get(name)
        size = path.stat().st_size
        if (
            doc
            and doc.status == "ready"
            and doc.embedding_model == c.embedder.name
            and doc.size_bytes == size
        ):
            continue
        if doc is None:
            doc_id = uuid.uuid4().hex
            stored = f"{doc_id}.pdf"
            shutil.copyfile(path, c.settings.uploads_dir / stored)
            c.db.insert_document(doc_id, name, stored, size)
        else:
            doc_id = doc.id
            if doc.size_bytes != size:
                shutil.copyfile(path, c.settings.uploads_dir / doc.stored_name)
                c.db.update_size(doc_id, size)
            c.db.set_status(doc_id, "processing")
        c.indexer.index_document(doc_id)
        count += 1
    log.info("Demo mode: seeded %d document(s) from %s", count, src_dir)
    return count
