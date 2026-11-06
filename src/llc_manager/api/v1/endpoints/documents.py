"""Read-only document endpoints: metadata list, detail, and file stream.

Authentication is the ``X-API-Key`` dependency applied to the whole
``/api/v1`` router. Files are located by document ID only, under the
configured documents root (see ``services/document_store.py``).
"""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from llc_manager.core.config import settings
from llc_manager.db.session import get_async_session
from llc_manager.models.document import Document, DocumentCategory
from llc_manager.schemas.document import DocumentListResponse, DocumentRead
from llc_manager.services.document_store import (
    DEFAULT_MIME,
    UnsafePathError,
    resolve_stored_file,
)
from llc_manager.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_async_session)]

_NOT_FOUND = "Document not found"
_FILE_NOT_FOUND = "Document file not found"


async def _get_live_document(db: AsyncSession, document_id: UUID) -> Document:
    """Return a non-deleted document or raise 404.

    Args:
        db (AsyncSession): Database session.
        document_id (UUID): Document ID.

    Returns:
        Document: The document.

    Raises:
        HTTPException: 404 when the document does not exist or is deleted.
    """
    result = await db.execute(
        select(Document).where(
            Document.id == document_id, Document.deleted_at.is_(None)
        )
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return document


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List documents",
    description=(
        "Return document metadata, oldest `updated_at` first, so a consumer "
        "can page through changes. `updated_since` returns documents whose "
        "`updated_at` is at or after the given time (a timestamp without a "
        "zone is read as UTC); any create, file replacement, or metadata edit "
        "moves `updated_at`. Paging is by offset, so a document edited while "
        "a consumer pages can shift later rows: re-poll with a watermark a "
        "few minutes behind the newest `updated_at` seen and de-duplicate by "
        "`id`. Soft-deleted documents are excluded, so deletions do not "
        "appear in this feed."
    ),
    responses={
        200: {"description": "Paginated list of documents"},
        401: {"description": "Missing or invalid API key"},
        503: {"description": "API key not configured on the server"},
    },
)
async def list_documents(
    db: DBSession,
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(50, ge=1, le=200, description="Items per page"),
    updated_since: datetime | None = Query(
        None, description="Only documents updated at or after this time"
    ),
    entity_id: UUID | None = Query(None, description="Filter by entity"),
    category: DocumentCategory | None = Query(None, description="Filter by category"),
) -> DocumentListResponse:
    """List documents with pagination and filters.

    Args:
        db (DBSession): Database session.
        page (int): Page number (1-indexed).
        size (int): Items per page.
        updated_since (datetime | None): Lower bound on ``updated_at``.
        entity_id (UUID | None): Optional entity filter.
        category (DocumentCategory | None): Optional category filter.

    Returns:
        DocumentListResponse: The page of documents and totals.
    """
    # #EDGE: Concurrency - offset paging over a sort key that edits change can
    # skip a row at a page boundary, and updated_at is the transaction start
    # time, so a long import can commit rows behind a consumer's watermark.
    # Consumers overlap their updated_since watermark and de-duplicate by id.
    # #VERIFY: docs/guides/documents.md states the overlap rule; revisit with
    # keyset paging on (updated_at, id) if a consumer cannot de-duplicate.
    query = select(Document).where(Document.deleted_at.is_(None))
    if updated_since is not None:
        if updated_since.tzinfo is None:
            updated_since = updated_since.replace(tzinfo=UTC)
        query = query.where(Document.updated_at >= updated_since)
    if entity_id is not None:
        query = query.where(Document.entity_id == entity_id)
    if category is not None:
        query = query.where(Document.category == category)

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar() or 0

    query = (
        query.order_by(Document.updated_at, Document.id)
        .offset((page - 1) * size)
        .limit(size)
    )
    result = await db.execute(query)
    documents = result.scalars().all()

    return DocumentListResponse(
        items=[DocumentRead.model_validate(d) for d in documents],
        total=total,
        page=page,
        size=size,
        pages=(total + size - 1) // size if total > 0 else 1,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentRead,
    summary="Get document metadata",
    description="Return one non-deleted document's metadata. No file path is returned.",
    responses={
        200: {"description": "Document metadata"},
        401: {"description": "Missing or invalid API key"},
        404: {"description": "Document not found"},
        503: {"description": "API key not configured on the server"},
    },
)
async def get_document(db: DBSession, document_id: UUID) -> DocumentRead:
    """Return one document's metadata.

    Args:
        db (DBSession): Database session.
        document_id (UUID): Document ID.

    Returns:
        DocumentRead: The document metadata.
    """
    return DocumentRead.model_validate(await _get_live_document(db, document_id))


@router.get(
    "/{document_id}/file",
    response_class=FileResponse,
    summary="Download document file",
    description=(
        "Stream the stored file with its MIME type and `Content-Length`. "
        "The file is located by document ID under the server's documents "
        "root; no path is accepted from the caller."
    ),
    responses={
        200: {"description": "File bytes", "content": {DEFAULT_MIME: {}}},
        401: {"description": "Missing or invalid API key"},
        404: {"description": "Document or file not found"},
        503: {"description": "API key not configured on the server"},
    },
)
async def get_document_file(db: DBSession, document_id: UUID) -> FileResponse:
    """Stream a document's stored file.

    Args:
        db (DBSession): Database session.
        document_id (UUID): Document ID.

    Returns:
        FileResponse: The streamed file.

    Raises:
        HTTPException: 404 when the document or its stored file is missing,
            or the stored path is unsafe. The detail never contains a path.
    """
    document = await _get_live_document(db, document_id)
    try:
        path = resolve_stored_file(
            settings.documents_root, document.id, document.mime_type
        )
    except UnsafePathError as exc:
        logger.warning(
            "document_file_unavailable", document_id=str(document.id), reason=str(exc)
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_FILE_NOT_FOUND
        ) from None

    return FileResponse(
        path,
        media_type=document.mime_type or DEFAULT_MIME,
        content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff"},
    )
