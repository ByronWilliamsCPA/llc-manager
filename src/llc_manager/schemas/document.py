"""Document schemas for API request/response validation."""

from datetime import date, datetime
from uuid import UUID

from pydantic import Field, model_validator

from llc_manager.models.document import DocumentCategory, DocumentType
from llc_manager.schemas.base import BaseSchema, FullSchema


class DocumentBase(BaseSchema):
    """Base schema for document data."""

    document_type: DocumentType
    category: DocumentCategory = DocumentCategory.OTHER
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
    consent_on_file: bool = False


class DocumentCreate(DocumentBase):
    """Schema for creating a new document.

    ``consent_on_file`` records taxpayer consent for a tax return, so it may
    be true only in the Tax Returns category (the manifest import enforces the
    same rule).
    """

    entity_id: UUID

    @model_validator(mode="after")
    def _consent_only_for_tax_returns(self) -> "DocumentCreate":
        """Reject ``consent_on_file`` outside the Tax Returns category.

        Returns:
            DocumentCreate: The validated schema.

        Raises:
            ValueError: If consent is set for any other category.
        """
        if self.consent_on_file and self.category is not DocumentCategory.TAX_RETURNS:
            msg = "consent_on_file is only valid for the Tax Returns category"
            raise ValueError(msg)
        return self


class DocumentUpdate(BaseSchema):
    """Schema for updating an existing document."""

    document_type: DocumentType | None = None
    category: DocumentCategory | None = None
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
    consent_on_file: bool | None = None


class DocumentResponse(FullSchema, DocumentBase):
    """Schema for document response."""

    id: UUID
    entity_id: UUID
    is_expired: bool
    tag_list: list[str]


class DocumentRead(BaseSchema):
    """Document metadata served to other services by ``/api/v1/documents``.

    This is the cross-service document contract. It never includes a file
    path; the file is fetched by ID from ``/api/v1/documents/{id}/file``.
    """

    id: UUID
    title: str
    category: DocumentCategory
    document_type: DocumentType
    entity_id: UUID
    document_date: date | None = None
    effective_date: date | None = None
    is_confidential: bool
    consent_on_file: bool
    sha256: str | None = None
    mime_type: str | None = None
    file_size: int | None = None
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseSchema):
    """Paginated document list, oldest ``updated_at`` first."""

    items: list[DocumentRead]
    total: int
    page: int
    size: int
    pages: int
