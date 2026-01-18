"""Tax filing schemas for API request/response validation."""

from datetime import date
from uuid import UUID

from pydantic import Field

from llc_manager.models.tax_filing import FilingFrequency, FilingStatus, TaxFilingType
from llc_manager.schemas.base import BaseSchema, FullSchema


class TaxFilingBase(BaseSchema):
    """Base schema for tax filing data."""

    filing_type: TaxFilingType
    jurisdiction: str = Field(..., min_length=1, max_length=50)
    tax_year: int = Field(..., ge=1900, le=2100)
    tax_period: str | None = Field(None, max_length=20)
    frequency: FilingFrequency = FilingFrequency.ANNUAL

    due_date: date | None = None
    extended_due_date: date | None = None
    filed_date: date | None = None

    status: FilingStatus = FilingStatus.PENDING
    form_number: str | None = Field(None, max_length=50)
    confirmation_number: str | None = Field(None, max_length=100)
    preparer: str | None = Field(None, max_length=255)

    amount_due: str | None = Field(None, max_length=50)
    amount_paid: str | None = Field(None, max_length=50)

    notes: str | None = None


class TaxFilingCreate(TaxFilingBase):
    """Schema for creating a new tax filing."""

    entity_id: UUID


class TaxFilingUpdate(BaseSchema):
    """Schema for updating an existing tax filing."""

    filing_type: TaxFilingType | None = None
    jurisdiction: str | None = Field(None, min_length=1, max_length=50)
    tax_year: int | None = Field(None, ge=1900, le=2100)
    tax_period: str | None = Field(None, max_length=20)
    frequency: FilingFrequency | None = None

    due_date: date | None = None
    extended_due_date: date | None = None
    filed_date: date | None = None

    status: FilingStatus | None = None
    form_number: str | None = Field(None, max_length=50)
    confirmation_number: str | None = Field(None, max_length=100)
    preparer: str | None = Field(None, max_length=255)

    amount_due: str | None = Field(None, max_length=50)
    amount_paid: str | None = Field(None, max_length=50)

    notes: str | None = None


class TaxFilingResponse(FullSchema, TaxFilingBase):
    """Schema for tax filing response."""

    id: UUID
    entity_id: UUID
    is_overdue: bool
