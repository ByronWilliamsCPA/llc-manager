"""Base schema classes with common configuration."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    """Base schema with common configuration."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class TimestampSchema(BaseSchema):
    """Schema with timestamp fields."""

    created_at: datetime
    updated_at: datetime


class AuditSchema(TimestampSchema):
    """Schema with audit fields."""

    created_by: str | None = None
    updated_by: str | None = None
    deleted_at: datetime | None = None
    deleted_by: str | None = None


class UUIDSchema(BaseSchema):
    """Schema with UUID primary key."""

    id: UUID


class FullSchema(UUIDSchema, AuditSchema):
    """Full schema with UUID, timestamps, and audit fields."""
