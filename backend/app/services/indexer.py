"""Document ingestion: extract -> chunk -> embed -> persist."""

from __future__ import annotations

import logging
import uuid

from app.config import Settings
from app.db import Database
from app.services.chunking import chunk_pages
from app.services.embeddings import Embedder
from app.services.pdf import PDFValidationError, extract_pages
from app.services.vector_store import VectorStore

log = logging.getLogger(__name__)


class Indexer:
    def __init__(
        self, settings: Settings, db: Database, embedder: Embedder, store: VectorStore
    ) -> None:
        self.settings = settings
        self.db = db
        self.embedder = embedder
        self.store = store

    def index_document(self, doc_id: str) -> None:
        doc = self.db.get_document(doc_id)
        if doc is None:
            return
        path = self.settings.uploads_dir / doc.stored_name
        try:
            pages = extract_pages(path, self.settings.max_pages)
            chunks = chunk_pages(pages, self.settings.chunk_size, self.settings.chunk_overlap)
            vectors = self.embedder.embed_documents([c.text for c in chunks])
            if self.db.get_document(doc_id) is None:  # deleted while indexing
                return
            self.db.replace_index(
                doc_id,
                [(p.page_number, p.text) for p in pages],
                [
                    (uuid.uuid4().hex, c.ordinal, c.page_number, c.text, vectors[i])
                    for i, c in enumerate(chunks)
                ],
                self.embedder.name,
            )
            log.info("Indexed %s: %d pages, %d chunks", doc_id, len(pages), len(chunks))
        except PDFValidationError as exc:
            self.db.set_status(doc_id, "failed", str(exc))
        except FileNotFoundError:
            self.db.set_status(doc_id, "failed", "Stored file is missing; please re-upload.")
        except Exception:
            log.exception("Indexing failed for %s", doc_id)
            self.db.set_status(doc_id, "failed", "Unexpected error while indexing.")
        finally:
            self.store.invalidate()
