"""Entity schemas for API request/response validation.

An entity is a legal entity (LLC, trust, corporation, and so on), a person
(``individual``), or a family (``household``). See ADR-002.
"""

from datetime import date
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from llc_manager.models.entity import EntityType
from llc_manager.schemas.base import BaseSchema, FullSchema, XeroId

# Entity types that are not legal entities and carry no legal-entity fields.
PERSONAL_ENTITY_TYPES = frozenset({EntityType.INDIVIDUAL, EntityType.HOUSEHOLD})
LEGAL_ONLY_FIELDS = ("ein", "formation_state", "formation_date")


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
    xero_tenant_id: XeroId | None = None
    purpose: str | None = None
    notes: str | None = None
    is_active: bool = True


class EntityCreate(EntityBase):
    """Schema for creating a new entity."""

    @model_validator(mode="after")
    def _no_legal_fields_on_personal_entities(self) -> Self:
        """Reject legal-entity fields on an individual or household.

        Returns:
            Self: The validated model.

        Raises:
            ValueError: If an individual or household sets EIN, formation
                state, or formation date. The message names fields only.
        """
        if self.entity_type in PERSONAL_ENTITY_TYPES and any(
            getattr(self, name) for name in LEGAL_ONLY_FIELDS
        ):
            msg = (
                "ein, formation_state, and formation_date must be empty for "
                "individual and household entities"
            )
            raise ValueError(msg)
        return self


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
    xero_tenant_id: XeroId | None = None
    purpose: str | None = None
    notes: str | None = None
    is_active: bool | None = None


class EntityBankAccountRef(BaseSchema):
    """Bank account summary embedded in entity responses.

    Carries only what an external system needs to map its own account to this
    entity: the account UUID, its Xero account ID, and display hints. Contact
    details and routing numbers stay out of the entity response.
    """

    id: UUID
    account_nickname: str | None = None
    account_number_last4: str | None = None
    xero_account_id: str | None = None
    is_active: bool = True


class EntityResponse(FullSchema, EntityBase):
    """Schema for entity response."""

    id: UUID
    bank_accounts: list[EntityBankAccountRef] = Field(default_factory=list)


class EntityListResponse(BaseSchema):
    """Schema for paginated entity list response."""

    items: list[EntityResponse]
    total: int
    page: int
    size: int
    pages: int
