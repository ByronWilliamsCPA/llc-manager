"""Entity (LLC) model representing the core business entity."""

from datetime import date
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Date, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from llc_manager.db.base import AuditMixin, Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from llc_manager.models.bank_account import BankAccount
    from llc_manager.models.document import Document
    from llc_manager.models.entity_relationship import EntityRelationship
    from llc_manager.models.owner import Owner
    from llc_manager.models.registered_agent import RegisteredAgent
    from llc_manager.models.state_registration import StateRegistration
    from llc_manager.models.tax_filing import TaxFiling


class EntityType(StrEnum):
    """Types of business entities."""

    LLC = "llc"
    CORPORATION = "corporation"
    S_CORPORATION = "s_corporation"
    PARTNERSHIP = "partnership"
    SOLE_PROPRIETORSHIP = "sole_proprietorship"
    TRUST = "trust"
    NON_PROFIT = "non_profit"
    OTHER = "other"


class Entity(Base, UUIDPrimaryKeyMixin, AuditMixin):
    """Represents a business entity (LLC or other type).

    Attributes:
        legal_name: The official legal name of the entity.
        dba_names: Comma-separated list of DBA (Doing Business As) names.
        ein: Employer Identification Number.
        entity_type: Type of business entity.
        formation_state: State where the entity was formed.
        formation_date: Date the entity was formed.
        fiscal_year_end: Fiscal year end month and day (e.g., "12-31").
        business_address: Primary business address.
        business_city: City of business address.
        business_state: State of business address.
        business_zip: ZIP code of business address.
        mailing_address: Mailing address (if different from business).
        mailing_city: City of mailing address.
        mailing_state: State of mailing address.
        mailing_zip: ZIP code of mailing address.
        accounting_record_id: External accounting system record ID.
        purpose: Purpose or business description.
        notes: Additional notes about the entity.
        is_active: Whether the entity is currently active.
    """

    __tablename__ = "entities"

    # Basic identification
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    dba_names: Mapped[str | None] = mapped_column(Text, nullable=True)
    ein: Mapped[str | None] = mapped_column(
        String(20), nullable=True, unique=True, index=True
    )
    entity_type: Mapped[EntityType] = mapped_column(
        Enum(EntityType, name="entity_type_enum"),
        nullable=False,
        default=EntityType.LLC,
    )

    # Formation details
    formation_state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    formation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    fiscal_year_end: Mapped[str | None] = mapped_column(
        String(5), nullable=True
    )  # MM-DD format

    # Business address
    business_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    business_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    business_state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    business_zip: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Mailing address
    mailing_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mailing_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mailing_state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    mailing_zip: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # External references
    accounting_record_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )

    # Additional info
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships
    owners: Mapped[list["Owner"]] = relationship(
        "Owner",
        back_populates="entity",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    bank_accounts: Mapped[list["BankAccount"]] = relationship(
        "BankAccount",
        back_populates="entity",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    state_registrations: Mapped[list["StateRegistration"]] = relationship(
        "StateRegistration",
        back_populates="entity",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    registered_agents: Mapped[list["RegisteredAgent"]] = relationship(
        "RegisteredAgent",
        back_populates="entity",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    tax_filings: Mapped[list["TaxFiling"]] = relationship(
        "TaxFiling",
        back_populates="entity",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    documents: Mapped[list["Document"]] = relationship(
        "Document",
        back_populates="entity",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # Entity relationships (parent side)
    child_relationships: Mapped[list["EntityRelationship"]] = relationship(
        "EntityRelationship",
        foreign_keys="EntityRelationship.parent_entity_id",
        back_populates="parent_entity",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # Entity relationships (child side)
    parent_relationships: Mapped[list["EntityRelationship"]] = relationship(
        "EntityRelationship",
        foreign_keys="EntityRelationship.child_entity_id",
        back_populates="child_entity",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        """Return string representation of the entity."""
        return f"<Entity(id={self.id}, legal_name='{self.legal_name}')>"

    @property
    def parent_entities(self) -> list["Entity"]:
        """Get all parent entities."""
        return [rel.parent_entity for rel in self.parent_relationships]

    @property
    def child_entities(self) -> list["Entity"]:
        """Get all child entities."""
        return [rel.child_entity for rel in self.child_relationships]
