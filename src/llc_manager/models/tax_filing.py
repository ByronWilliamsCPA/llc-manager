"""Tax filing model for tracking entity tax obligations and filings."""

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Date, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from llc_manager.db.base import AuditMixin, Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from llc_manager.models.entity import Entity


class TaxFilingType(StrEnum):
    """Types of tax filings."""

    FEDERAL_INCOME = "federal_income"
    STATE_INCOME = "state_income"
    FRANCHISE_TAX = "franchise_tax"
    SALES_TAX = "sales_tax"
    PAYROLL_TAX = "payroll_tax"
    PROPERTY_TAX = "property_tax"
    ESTIMATED_TAX = "estimated_tax"
    ANNUAL_REPORT = "annual_report"
    K1 = "k1"
    OTHER = "other"


class FilingFrequency(StrEnum):
    """Frequency of tax filing."""

    ANNUAL = "annual"
    QUARTERLY = "quarterly"
    MONTHLY = "monthly"
    SEMI_ANNUAL = "semi_annual"
    ONE_TIME = "one_time"


class FilingStatus(StrEnum):
    """Status of a tax filing."""

    PENDING = "pending"
    FILED = "filed"
    EXTENDED = "extended"
    LATE = "late"
    NOT_REQUIRED = "not_required"


class TaxFiling(Base, UUIDPrimaryKeyMixin, AuditMixin):
    """Represents a tax filing obligation or completed filing for an entity.

    Attributes:
        entity_id: Foreign key to the owning entity.
        filing_type: Type of tax filing.
        jurisdiction: State or jurisdiction (use "Federal" for federal).
        tax_year: Tax year for the filing.
        tax_period: Specific period (e.g., "Q1 2024", "2024").
        frequency: How often this filing is required.
        due_date: Date the filing is due.
        extended_due_date: Extended due date if extension filed.
        filed_date: Date the filing was completed.
        status: Current status of the filing.
        form_number: Tax form number (e.g., "1065", "Form 568").
        confirmation_number: Filing confirmation number.
        preparer: Name of tax preparer.
        amount_due: Amount due with the filing.
        amount_paid: Amount paid with the filing.
        notes: Additional notes about the filing.
    """

    __tablename__ = "tax_filings"

    # Entity relationship
    entity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Filing information
    filing_type: Mapped[TaxFilingType] = mapped_column(
        Enum(TaxFilingType, name="tax_filing_type_enum"),
        nullable=False,
    )
    jurisdiction: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    tax_year: Mapped[int] = mapped_column(nullable=False, index=True)
    tax_period: Mapped[str | None] = mapped_column(String(20), nullable=True)
    frequency: Mapped[FilingFrequency] = mapped_column(
        Enum(FilingFrequency, name="filing_frequency_enum"),
        nullable=False,
        default=FilingFrequency.ANNUAL,
    )

    # Dates
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    extended_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    filed_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Status and details
    status: Mapped[FilingStatus] = mapped_column(
        Enum(FilingStatus, name="filing_status_enum"),
        nullable=False,
        default=FilingStatus.PENDING,
    )
    form_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confirmation_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    preparer: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Financial
    amount_due: Mapped[str | None] = mapped_column(String(50), nullable=True)
    amount_paid: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Additional info
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    entity: Mapped["Entity"] = relationship("Entity", back_populates="tax_filings")

    def __repr__(self) -> str:
        """Return string representation of the tax filing."""
        return (
            f"<TaxFiling(id={self.id}, type='{self.filing_type}', "
            f"jurisdiction='{self.jurisdiction}', year={self.tax_year})>"
        )

    @property
    def is_overdue(self) -> bool:
        """Check if the filing is overdue."""
        if self.status == FilingStatus.FILED:
            return False
        if self.extended_due_date:
            return datetime.now(UTC).date() > self.extended_due_date
        if self.due_date:
            return datetime.now(UTC).date() > self.due_date
        return False
