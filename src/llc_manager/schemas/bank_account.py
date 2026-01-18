"""Bank account schemas for API request/response validation."""

from datetime import date
from uuid import UUID

from pydantic import Field

from llc_manager.models.bank_account import AccountType
from llc_manager.schemas.base import BaseSchema, FullSchema


class BankAccountBase(BaseSchema):
    """Base schema for bank account data."""

    bank_name: str = Field(..., min_length=1, max_length=255)
    account_name: str | None = Field(None, max_length=255)
    account_type: AccountType = AccountType.BUSINESS_CHECKING
    account_number_last4: str | None = Field(None, min_length=4, max_length=4)
    routing_number: str | None = Field(None, min_length=9, max_length=9)
    account_nickname: str | None = Field(None, max_length=100)

    opened_date: date | None = None
    closed_date: date | None = None

    primary_contact: str | None = Field(None, max_length=255)
    contact_phone: str | None = Field(None, max_length=20)
    contact_email: str | None = Field(None, max_length=255)
    branch_address: str | None = None
    online_banking_url: str | None = Field(None, max_length=500)

    notes: str | None = None
    is_primary: bool = False
    is_active: bool = True


class BankAccountCreate(BankAccountBase):
    """Schema for creating a new bank account."""

    entity_id: UUID


class BankAccountUpdate(BaseSchema):
    """Schema for updating an existing bank account."""

    bank_name: str | None = Field(None, min_length=1, max_length=255)
    account_name: str | None = Field(None, max_length=255)
    account_type: AccountType | None = None
    account_number_last4: str | None = Field(None, min_length=4, max_length=4)
    routing_number: str | None = Field(None, min_length=9, max_length=9)
    account_nickname: str | None = Field(None, max_length=100)

    opened_date: date | None = None
    closed_date: date | None = None

    primary_contact: str | None = Field(None, max_length=255)
    contact_phone: str | None = Field(None, max_length=20)
    contact_email: str | None = Field(None, max_length=255)
    branch_address: str | None = None
    online_banking_url: str | None = Field(None, max_length=500)

    notes: str | None = None
    is_primary: bool | None = None
    is_active: bool | None = None


class BankAccountResponse(FullSchema, BankAccountBase):
    """Schema for bank account response."""

    id: UUID
    entity_id: UUID
