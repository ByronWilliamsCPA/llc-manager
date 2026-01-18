"""Owner schemas for API request/response validation."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import Field, field_validator

from llc_manager.models.owner import OwnershipType
from llc_manager.schemas.base import BaseSchema, FullSchema


class OwnerBase(BaseSchema):
    """Base schema for owner data."""

    owner_name: str = Field(..., min_length=1, max_length=255)
    owner_entity_id: UUID | None = None
    ownership_type: OwnershipType = OwnershipType.MEMBER
    ownership_percentage: Decimal = Field(
        default=Decimal("0.00"), ge=Decimal(0), le=Decimal(100)
    )
    capital_contribution: Decimal | None = Field(None, ge=Decimal(0))
    profit_share_percentage: Decimal | None = Field(
        None, ge=Decimal(0), le=Decimal(100)
    )
    loss_share_percentage: Decimal | None = Field(
        None, ge=Decimal(0), le=Decimal(100)
    )
    voting_percentage: Decimal | None = Field(None, ge=Decimal(0), le=Decimal(100))

    start_date: date | None = None
    end_date: date | None = None

    ein_or_ssn: str | None = Field(None, max_length=20)
    address: str | None = Field(None, max_length=255)
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, min_length=2, max_length=2)
    zip_code: str | None = Field(None, max_length=10)
    email: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=20)

    notes: str | None = None
    is_active: bool = True

    @field_validator(
        "ownership_percentage",
        "profit_share_percentage",
        "loss_share_percentage",
        "voting_percentage",
        mode="before",
    )
    @classmethod
    def convert_to_decimal(
        cls, v: float | int | str | Decimal | None
    ) -> Decimal | None:
        """Convert numeric values to Decimal."""
        if v is None:
            return None
        return Decimal(str(v))


class OwnerCreate(OwnerBase):
    """Schema for creating a new owner."""

    entity_id: UUID


class OwnerUpdate(BaseSchema):
    """Schema for updating an existing owner."""

    owner_name: str | None = Field(None, min_length=1, max_length=255)
    owner_entity_id: UUID | None = None
    ownership_type: OwnershipType | None = None
    ownership_percentage: Decimal | None = Field(
        None, ge=Decimal(0), le=Decimal(100)
    )
    capital_contribution: Decimal | None = Field(None, ge=Decimal(0))
    profit_share_percentage: Decimal | None = Field(
        None, ge=Decimal(0), le=Decimal(100)
    )
    loss_share_percentage: Decimal | None = Field(
        None, ge=Decimal(0), le=Decimal(100)
    )
    voting_percentage: Decimal | None = Field(None, ge=Decimal(0), le=Decimal(100))

    start_date: date | None = None
    end_date: date | None = None

    ein_or_ssn: str | None = Field(None, max_length=20)
    address: str | None = Field(None, max_length=255)
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, min_length=2, max_length=2)
    zip_code: str | None = Field(None, max_length=10)
    email: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=20)

    notes: str | None = None
    is_active: bool | None = None

    @field_validator(
        "ownership_percentage",
        "profit_share_percentage",
        "loss_share_percentage",
        "voting_percentage",
        mode="before",
    )
    @classmethod
    def convert_to_decimal(
        cls, v: float | int | str | Decimal | None
    ) -> Decimal | None:
        """Convert numeric values to Decimal."""
        if v is None:
            return None
        return Decimal(str(v))


class OwnerResponse(FullSchema, OwnerBase):
    """Schema for owner response."""

    id: UUID
    entity_id: UUID
