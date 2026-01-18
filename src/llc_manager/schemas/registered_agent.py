"""Registered agent schemas for API request/response validation."""

from datetime import date
from uuid import UUID

from pydantic import Field

from llc_manager.schemas.base import BaseSchema, FullSchema


class RegisteredAgentBase(BaseSchema):
    """Base schema for registered agent data."""

    state: str = Field(..., min_length=2, max_length=2)
    agent_name: str = Field(..., min_length=1, max_length=255)
    agent_company: str | None = Field(None, max_length=255)

    address: str | None = Field(None, max_length=255)
    city: str | None = Field(None, max_length=100)
    state_address: str | None = Field(None, min_length=2, max_length=2)
    zip_code: str | None = Field(None, max_length=10)

    phone: str | None = Field(None, max_length=20)
    email: str | None = Field(None, max_length=255)

    effective_date: date | None = None
    expiration_date: date | None = None
    renewal_date: date | None = None

    annual_cost: str | None = Field(None, max_length=50)
    account_number: str | None = Field(None, max_length=100)

    notes: str | None = None
    is_active: bool = True


class RegisteredAgentCreate(RegisteredAgentBase):
    """Schema for creating a new registered agent."""

    entity_id: UUID


class RegisteredAgentUpdate(BaseSchema):
    """Schema for updating an existing registered agent."""

    state: str | None = Field(None, min_length=2, max_length=2)
    agent_name: str | None = Field(None, min_length=1, max_length=255)
    agent_company: str | None = Field(None, max_length=255)

    address: str | None = Field(None, max_length=255)
    city: str | None = Field(None, max_length=100)
    state_address: str | None = Field(None, min_length=2, max_length=2)
    zip_code: str | None = Field(None, max_length=10)

    phone: str | None = Field(None, max_length=20)
    email: str | None = Field(None, max_length=255)

    effective_date: date | None = None
    expiration_date: date | None = None
    renewal_date: date | None = None

    annual_cost: str | None = Field(None, max_length=50)
    account_number: str | None = Field(None, max_length=100)

    notes: str | None = None
    is_active: bool | None = None


class RegisteredAgentResponse(FullSchema, RegisteredAgentBase):
    """Schema for registered agent response."""

    id: UUID
    entity_id: UUID
