"""Document model for tracking entity documents and files."""

from datetime import date
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Date, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from llc_manager.db.base import AuditMixin, Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from llc_manager.models.entity import Entity


class DocumentType(StrEnum):
    """Types of entity documents."""

    # Formation documents
    ARTICLES_OF_ORGANIZATION = "articles_of_organization"
    ARTICLES_OF_INCORPORATION = "articles_of_incorporation"
    CERTIFICATE_OF_FORMATION = "certificate_of_formation"
    OPERATING_AGREEMENT = "operating_agreement"
    BYLAWS = "bylaws"
    PARTNERSHIP_AGREEMENT = "partnership_agreement"

    # Meeting minutes
    MEETING_MINUTES = "meeting_minutes"
    ANNUAL_MEETING = "annual_meeting"
    SPECIAL_MEETING = "special_meeting"
    WRITTEN_CONSENT = "written_consent"

    # State filings
    ANNUAL_REPORT = "annual_report"
    AMENDMENT = "amendment"
    STATEMENT_OF_INFORMATION = "statement_of_information"
    CERTIFICATE_OF_GOOD_STANDING = "certificate_of_good_standing"
    FOREIGN_QUALIFICATION = "foreign_qualification"

    # Tax documents
    EIN_LETTER = "ein_letter"
    TAX_RETURN = "tax_return"
    TAX_ELECTION = "tax_election"  # S-Corp election, etc.

    # Banking
    BANK_RESOLUTION = "bank_resolution"
    SIGNATURE_CARD = "signature_card"

    # Contracts and agreements
    CONTRACT = "contract"
    LEASE = "lease"
    INSURANCE_POLICY = "insurance_policy"

    # Ownership
    MEMBERSHIP_CERTIFICATE = "membership_certificate"
    STOCK_CERTIFICATE = "stock_certificate"
    TRANSFER_AGREEMENT = "transfer_agreement"

    # Other
    CORRESPONDENCE = "correspondence"
    OTHER = "other"


class Document(Base, UUIDPrimaryKeyMixin, AuditMixin):
    """Represents a document associated with an entity.

    Attributes:
        entity_id: Foreign key to the owning entity.
        document_type: Type of document.
        title: Title or name of the document.
        description: Description of the document.
        file_path: Path to the stored file.
        file_name: Original file name.
        file_size: Size of the file in bytes.
        mime_type: MIME type of the file.
        document_date: Date of the document.
        effective_date: Date the document became effective.
        expiration_date: Date the document expires.
        version: Version number of the document.
        tags: Comma-separated tags for categorization.
        notes: Additional notes about the document.
        is_confidential: Whether the document is confidential.
    """

    __tablename__ = "documents"

    # Entity relationship
    entity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Document information
    document_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, name="document_type_enum"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # File information
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size: Mapped[int | None] = mapped_column(nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Dates
    document_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Versioning and categorization
    version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Additional info
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_confidential: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Relationships
    entity: Mapped["Entity"] = relationship("Entity", back_populates="documents")

    def __repr__(self) -> str:
        """Return string representation of the document."""
        return (
            f"<Document(id={self.id}, type='{self.document_type}', "
            f"title='{self.title}')>"
        )

    @property
    def is_expired(self) -> bool:
        """Check if the document has expired."""
        if self.expiration_date:
            return date.today() > self.expiration_date
        return False

    @property
    def tag_list(self) -> list[str]:
        """Return tags as a list."""
        if self.tags:
            return [tag.strip() for tag in self.tags.split(",")]
        return []
