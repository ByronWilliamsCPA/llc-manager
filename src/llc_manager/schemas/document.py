"""Document schemas for API request/response validation."""

from datetime import date
from uuid import UUID

from pydantic import Field

from llc_manager.models.document import DocumentType
from llc_manager.schemas.base import BaseSchema, FullSchema


class DocumentBase(BaseSchema):
    """Base schema for document data."""

    document_type: DocumentType
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None

    file_path: str | None = Field(None, max_length=500)
    file_name: str | None = Field(None, max_length=255)
    file_size: int | None = Field(None, ge=0)
    mime_type: str | None = Field(None, max_length=100)

    document_date: date | None = None
    effective_date: date | None = None
    expiration_date: date | None = None

    version: str | None = Field(None, max_length=20)
    tags: str | None = None

    notes: str | None = None
    is_confidential: bool = False


class DocumentCreate(DocumentBase):
    """Schema for creating a new document."""

    entity_id: UUID


class DocumentUpdate(BaseSchema):
    """Schema for updating an existing document."""

    document_type: DocumentType | None = None
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None

    file_path: str | None = Field(None, max_length=500)
    file_name: str | None = Field(None, max_length=255)
    file_size: int | None = Field(None, ge=0)
    mime_type: str | None = Field(None, max_length=100)

    document_date: date | None = None
    effective_date: date | None = None
    expiration_date: date | None = None

    version: str | None = Field(None, max_length=20)
    tags: str | None = None

    notes: str | None = None
    is_confidential: bool | None = None


class DocumentResponse(FullSchema, DocumentBase):
    """Schema for document response."""

    id: UUID
    entity_id: UUID
    is_expired: bool
    tag_list: list[str]
