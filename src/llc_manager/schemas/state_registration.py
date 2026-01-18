"""State registration schemas for API request/response validation."""

from datetime import date
from uuid import UUID

from pydantic import Field

from llc_manager.models.state_registration import RegistrationStatus, RegistrationType
from llc_manager.schemas.base import BaseSchema, FullSchema


class StateRegistrationBase(BaseSchema):
    """Base schema for state registration data."""

    state: str = Field(..., min_length=2, max_length=2)
    registration_type: RegistrationType = RegistrationType.DOMESTIC
    status: RegistrationStatus = RegistrationStatus.ACTIVE
    file_number: str | None = Field(None, max_length=50)
    registered_name: str | None = Field(None, max_length=255)

    registration_date: date | None = None
    effective_date: date | None = None
    expiration_date: date | None = None
    annual_report_due: date | None = None
    last_annual_report: date | None = None
    next_renewal_date: date | None = None

    filing_fee: str | None = Field(None, max_length=50)
    annual_fee: str | None = Field(None, max_length=50)

    notes: str | None = None
    is_good_standing: bool = True


class StateRegistrationCreate(StateRegistrationBase):
    """Schema for creating a new state registration."""

    entity_id: UUID


class StateRegistrationUpdate(BaseSchema):
    """Schema for updating an existing state registration."""

    state: str | None = Field(None, min_length=2, max_length=2)
    registration_type: RegistrationType | None = None
    status: RegistrationStatus | None = None
    file_number: str | None = Field(None, max_length=50)
    registered_name: str | None = Field(None, max_length=255)

    registration_date: date | None = None
    effective_date: date | None = None
    expiration_date: date | None = None
    annual_report_due: date | None = None
    last_annual_report: date | None = None
    next_renewal_date: date | None = None

    filing_fee: str | None = Field(None, max_length=50)
    annual_fee: str | None = Field(None, max_length=50)

    notes: str | None = None
    is_good_standing: bool | None = None


class StateRegistrationResponse(FullSchema, StateRegistrationBase):
    """Schema for state registration response."""

    id: UUID
    entity_id: UUID
