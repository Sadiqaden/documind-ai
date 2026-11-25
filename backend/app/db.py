"""SQLite persistence for document metadata, pages and chunks (incl. embedding vectors)."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    page_count INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    error TEXT,
    embedding_model TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pages (
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY (document_id, page_number)
);
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    page_number INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(document_id);
"""


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True)
class DocumentRow:
    id: str
    filename: str
    stored_name: str
    size_bytes: int
    page_count: int
    chunk_count: int
    status: str
    error: str | None
    embedding_model: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ChunkRow:
    id: str
    document_id: str
    ordinal: int
    page_number: int
    text: str
    embedding: np.ndarray


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.executescript(SCHEMA)

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def close(self) -> None:
        self._conn.close()

    # --- documents -------------------------------------------------------
    def insert_document(self, doc_id: str, filename: str, stored_name: str, size: int) -> None:
        ts = now_iso()
        with self.tx() as c:
            c.execute(
                "INSERT INTO documents (id, filename, stored_name, size_bytes, status, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, 'processing', ?, ?)",
                (doc_id, filename, stored_name, size, ts, ts),
            )

    def set_status(self, doc_id: str, status: str, error: str | None = None) -> None:
        with self.tx() as c:
            c.execute(
                "UPDATE documents SET status = ?, error = ?, updated_at = ? WHERE id = ?",
                (status, error, now_iso(), doc_id),
            )

    def update_size(self, doc_id: str, size: int) -> None:
        with self.tx() as c:
            c.execute(
                "UPDATE documents SET size_bytes = ?, updated_at = ? WHERE id = ?",
                (size, now_iso(), doc_id),
            )

    def get_document(self, doc_id: str) -> DocumentRow | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        return DocumentRow(**dict(row)) if row else None

    def list_documents(self) -> list[DocumentRow]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
        return [DocumentRow(**dict(r)) for r in rows]

    def delete_document(self, doc_id: str) -> None:
        with self.tx() as c:
            c.execute("DELETE FROM documents WHERE id = ?", (doc_id,))

    # --- index content ---------------------------------------------------
    def replace_index(
        self,
        doc_id: str,
        pages: list[tuple[int, str]],
        chunks: list[tuple[str, int, int, str, np.ndarray]],
        embedding_model: str,
    ) -> None:
        """Atomically replace pages+chunks for a document and mark it ready."""
        with self.tx() as c:
            c.execute("DELETE FROM pages WHERE document_id = ?", (doc_id,))
            c.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
            c.executemany(
                "INSERT INTO pages (document_id, page_number, text) VALUES (?, ?, ?)",
                [(doc_id, p, t) for p, t in pages],
            )
            c.executemany(
                "INSERT INTO chunks (id, document_id, ordinal, page_number, text, embedding) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (cid, doc_id, o, p, t, np.asarray(v, dtype=np.float32).tobytes())
                    for cid, o, p, t, v in chunks
                ],
            )
            c.execute(
                "UPDATE documents SET page_count = ?, chunk_count = ?, status = 'ready', "
                "error = NULL, embedding_model = ?, updated_at = ? WHERE id = ?",
                (len(pages), len(chunks), embedding_model, now_iso(), doc_id),
            )

    def all_chunks(self) -> list[ChunkRow]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT c.* FROM chunks c JOIN documents d ON d.id = c.document_id "
                "WHERE d.status = 'ready' ORDER BY c.document_id, c.ordinal"
            ).fetchall()
        return [
            ChunkRow(
                id=r["id"],
                document_id=r["document_id"],
                ordinal=r["ordinal"],
                page_number=r["page_number"],
                text=r["text"],
                embedding=np.frombuffer(r["embedding"], dtype=np.float32),
            )
            for r in rows
        ]

    def get_pages(self, doc_id: str) -> list[tuple[int, str]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT page_number, text FROM pages WHERE document_id = ? ORDER BY page_number",
                (doc_id,),
            ).fetchall()
        return [(r["page_number"], r["text"]) for r in rows]
