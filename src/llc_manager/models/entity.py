"""Entity model: a legal entity, an individual, or a household."""

from datetime import date
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Date, Enum, Index, String, Text, text
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
    """Types of entities.

    ``INDIVIDUAL`` (one per person) and ``HOUSEHOLD`` (one per family) are not
    legal entities. They exist so personal accounts and personal documents
    (wills, powers of attorney, health directives) attach to an entity like
    everything else. See ADR-002.
    """

    LLC = "llc"
    CORPORATION = "corporation"
    S_CORPORATION = "s_corporation"
    PARTNERSHIP = "partnership"
    SOLE_PROPRIETORSHIP = "sole_proprietorship"
    TRUST = "trust"
    NON_PROFIT = "non_profit"
    INDIVIDUAL = "individual"
    HOUSEHOLD = "household"
    OTHER = "other"


class Entity(Base, UUIDPrimaryKeyMixin, AuditMixin):
    """Represents a legal entity, an individual, or a household.

    Attributes:
        legal_name (Mapped[str]): The official legal name of the entity.
        dba_names (Mapped[str | None]): Comma-separated list of DBA (Doing Business As) names.
        ein (Mapped[str | None]): Employer Identification Number.
        entity_type (Mapped[EntityType]): Type of entity.
        formation_state (Mapped[str | None]): State where the entity was formed.
        formation_date (Mapped[date | None]): Date the entity was formed.
        fiscal_year_end (Mapped[str | None]): Fiscal year end month and day (e.g., "12-31").
        business_address (Mapped[str | None]): Primary business address.
        business_city (Mapped[str | None]): City of business address.
        business_state (Mapped[str | None]): State of business address.
        business_zip (Mapped[str | None]): ZIP code of business address.
        mailing_address (Mapped[str | None]): Mailing address (if different from business).
        mailing_city (Mapped[str | None]): City of mailing address.
        mailing_state (Mapped[str | None]): State of mailing address.
        mailing_zip (Mapped[str | None]): ZIP code of mailing address.
        accounting_record_id (Mapped[str | None]): External accounting system record ID.
        xero_tenant_id (Mapped[str | None]): Xero organisation (tenant) ID that
            maps to this entity, unique among non-deleted entities.
        purpose (Mapped[str | None]): Purpose or business description.
        notes (Mapped[str | None]): Additional notes about the entity.
        is_active (Mapped[bool]): Whether the entity is currently active.
        owners (Mapped[list['Owner']]): Related owner records.
        bank_accounts (Mapped[list['BankAccount']]): Related bank account records.
        state_registrations (Mapped[list['StateRegistration']]): Related state registration records.
        registered_agents (Mapped[list['RegisteredAgent']]): Related registered agent records.
        tax_filings (Mapped[list['TaxFiling']]): Related tax filing records.
        documents (Mapped[list['Document']]): Related document records.
        child_relationships (Mapped[list['EntityRelationship']]): Relationships where this entity is the parent.
        parent_relationships (Mapped[list['EntityRelationship']]): Relationships where this entity is the child.
    """

    __tablename__ = "entities"
    __table_args__ = (
        Index(
            "ix_entities_xero_tenant_id_active",
            "xero_tenant_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

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
    xero_tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Additional info
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships
    owners: Mapped[list["Owner"]] = relationship(
        "Owner",
        back_populates="entity",
        foreign_keys="Owner.entity_id",
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
