"""Entity (LLC) schemas for API request/response validation."""

from datetime import date
from uuid import UUID

from pydantic import Field

from llc_manager.models.entity import EntityType
from llc_manager.schemas.base import BaseSchema, FullSchema


class EntityBase(BaseSchema):
    """Base schema for entity data."""

    legal_name: str = Field(..., min_length=1, max_length=255)
    dba_names: str | None = None
    ein: str | None = Field(None, max_length=20, pattern=r"^\d{2}-\d{7}$|^$")
    entity_type: EntityType = EntityType.LLC

    formation_state: str | None = Field(None, min_length=2, max_length=2)
    formation_date: date | None = None
    fiscal_year_end: str | None = Field(
        None, pattern=r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$"
    )

    business_address: str | None = Field(None, max_length=255)
    business_city: str | None = Field(None, max_length=100)
    business_state: str | None = Field(None, min_length=2, max_length=2)
    business_zip: str | None = Field(None, max_length=10)

    mailing_address: str | None = Field(None, max_length=255)
    mailing_city: str | None = Field(None, max_length=100)
    mailing_state: str | None = Field(None, min_length=2, max_length=2)
    mailing_zip: str | None = Field(None, max_length=10)

    accounting_record_id: str | None = Field(None, max_length=100)
    purpose: str | None = None
    notes: str | None = None
    is_active: bool = True


class EntityCreate(EntityBase):
    """Schema for creating a new entity."""


class EntityUpdate(BaseSchema):
    """Schema for updating an existing entity."""

    legal_name: str | None = Field(None, min_length=1, max_length=255)
    dba_names: str | None = None
    ein: str | None = Field(None, max_length=20, pattern=r"^\d{2}-\d{7}$|^$")
    entity_type: EntityType | None = None

    formation_state: str | None = Field(None, min_length=2, max_length=2)
    formation_date: date | None = None
    fiscal_year_end: str | None = Field(
        None, pattern=r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$"
    )

    business_address: str | None = Field(None, max_length=255)
    business_city: str | None = Field(None, max_length=100)
    business_state: str | None = Field(None, min_length=2, max_length=2)
    business_zip: str | None = Field(None, max_length=10)

    mailing_address: str | None = Field(None, max_length=255)
    mailing_city: str | None = Field(None, max_length=100)
    mailing_state: str | None = Field(None, min_length=2, max_length=2)
    mailing_zip: str | None = Field(None, max_length=10)

    accounting_record_id: str | None = Field(None, max_length=100)
    purpose: str | None = None
    notes: str | None = None
    is_active: bool | None = None


class EntityResponse(FullSchema, EntityBase):
    """Schema for entity response."""

    id: UUID


class EntityListResponse(BaseSchema):
    """Schema for paginated entity list response."""

    items: list[EntityResponse]
    total: int
    page: int
    size: int
    pages: int
