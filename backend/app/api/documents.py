"""Document library endpoints: upload, list, get, download, delete, re-index."""

from __future__ import annotations

import re
import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse

from app.container import Container, get_container
from app.db import DocumentRow
from app.ratelimit import client_key
from app.schemas import DocumentList, DocumentOut
from app.services.pdf import PDFValidationError, safe_display_name, validate_pdf_bytes

router = APIRouter(prefix="/api/documents", tags=["documents"])
_ID = re.compile(r"^[0-9a-f]{32}$")
ALLOWED_CONTENT_TYPES = {"application/pdf", "application/x-pdf", "application/octet-stream"}
C = Annotated[Container, Depends(get_container)]


def to_out(doc: DocumentRow, c: Container) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        filename=doc.filename,
        size_bytes=doc.size_bytes,
        page_count=doc.page_count,
        chunk_count=doc.chunk_count,
        status=doc.status,
        error=doc.error,
        stale_index=doc.status == "ready" and doc.embedding_model != c.embedder.name,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def _require_writable(c: Container) -> None:
    if c.settings.demo_mode:
        raise HTTPException(
            status_code=403,
            detail="This is a read-only demo: uploading, deleting and re-indexing are disabled.",
        )


def _get_or_404(doc_id: str, c: Container) -> DocumentRow:
    if not _ID.match(doc_id):
        raise HTTPException(status_code=404, detail="Document not found.")
    doc = c.db.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return doc


@router.get("", response_model=DocumentList)
def list_documents(c: C) -> DocumentList:
    return DocumentList(documents=[to_out(d, c) for d in c.db.list_documents()])


@router.post("", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    request: Request,
    background: BackgroundTasks,
    c: C,
    file: Annotated[UploadFile, File(description="PDF file")],
) -> DocumentOut:
    _require_writable(c)
    c.upload_limiter.check(client_key(request))
    s = c.settings
    if file.content_type and file.content_type.lower() not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="Only PDF files are accepted.")
    if file.filename and not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only .pdf files are accepted.")

    data = await file.read(s.max_upload_bytes + 1)  # never buffer more than limit + 1 byte
    try:
        validate_pdf_bytes(data, s.max_upload_bytes)
    except PDFValidationError as exc:
        code = 413 if len(data) > s.max_upload_bytes else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc

    doc_id = uuid.uuid4().hex
    stored_name = f"{doc_id}.pdf"  # never use the client filename on disk
    (s.uploads_dir / stored_name).write_bytes(data)
    c.db.insert_document(doc_id, safe_display_name(file.filename), stored_name, len(data))
    background.add_task(c.indexer.index_document, doc_id)
    doc = c.db.get_document(doc_id)
    assert doc is not None
    return to_out(doc, c)


@router.get("/{doc_id}", response_model=DocumentOut)
def get_document(doc_id: str, c: C) -> DocumentOut:
    return to_out(_get_or_404(doc_id, c), c)


@router.get("/{doc_id}/file")
def download_document(doc_id: str, c: C) -> FileResponse:
    doc = _get_or_404(doc_id, c)
    path = c.settings.uploads_dir / doc.stored_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Stored file is missing.")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=doc.filename,
        content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(doc_id: str, c: C) -> Response:
    _require_writable(c)
    doc = _get_or_404(doc_id, c)
    c.db.delete_document(doc.id)
    (c.settings.uploads_dir / doc.stored_name).unlink(missing_ok=True)
    c.store.invalidate()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{doc_id}/reindex", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED)
def reindex_document(doc_id: str, background: BackgroundTasks, c: C) -> DocumentOut:
    _require_writable(c)
    doc = _get_or_404(doc_id, c)
    if doc.status == "processing":
        raise HTTPException(status_code=409, detail="Document is already being indexed.")
    c.db.set_status(doc.id, "processing")
    c.store.invalidate()
    background.add_task(c.indexer.index_document, doc.id)
    refreshed = c.db.get_document(doc.id)
    assert refreshed is not None
    return to_out(refreshed, c)
