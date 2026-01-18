"""Owner model for tracking LLC ownership."""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Date, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from llc_manager.db.base import AuditMixin, Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from llc_manager.models.entity import Entity


class OwnershipType(StrEnum):
    """Types of ownership in an entity."""

    MEMBER = "member"  # Standard LLC member
    MANAGING_MEMBER = "managing_member"  # LLC managing member
    SHAREHOLDER = "shareholder"  # Corporation shareholder
    GENERAL_PARTNER = "general_partner"  # Partnership general partner
    LIMITED_PARTNER = "limited_partner"  # Partnership limited partner
    BENEFICIARY = "beneficiary"  # Trust beneficiary
    TRUSTEE = "trustee"  # Trust trustee
    DIRECTOR = "director"  # Corporation director
    OFFICER = "officer"  # Corporation officer


class Owner(Base, UUIDPrimaryKeyMixin, AuditMixin):
    """Represents an owner or member of an entity.

    Attributes:
        entity_id: Foreign key to the owning entity.
        owner_name: Name of the owner (person or entity).
        owner_entity_id: If owner is another entity, reference to it.
        ownership_type: Type of ownership relationship.
        ownership_percentage: Percentage of ownership.
        capital_contribution: Capital contributed by the owner.
        profit_share_percentage: Share of profits (if different from ownership).
        loss_share_percentage: Share of losses (if different from ownership).
        voting_percentage: Voting percentage (if different from ownership).
        start_date: Date ownership began.
        end_date: Date ownership ended (null if current).
        ein_or_ssn: EIN or SSN of owner (encrypted/masked in display).
        address: Owner's address.
        city: Owner's city.
        state: Owner's state.
        zip_code: Owner's ZIP code.
        email: Owner's email address.
        phone: Owner's phone number.
        notes: Additional notes.
        is_active: Whether this ownership is currently active.
    """

    __tablename__ = "owners"

    # Entity relationship
    entity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Owner identification
    owner_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    owner_entity_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Ownership details
    ownership_type: Mapped[OwnershipType] = mapped_column(
        Enum(OwnershipType, name="ownership_type_enum"),
        nullable=False,
        default=OwnershipType.MEMBER,
    )
    ownership_percentage: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    capital_contribution: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 2),
        nullable=True,
    )
    profit_share_percentage: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,
    )
    loss_share_percentage: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,
    )
    voting_percentage: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,
    )

    # Dates
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Contact information
    ein_or_ssn: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # Should be encrypted
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Additional info
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships
    entity: Mapped["Entity"] = relationship(
        "Entity",
        back_populates="owners",
        foreign_keys=[entity_id],
    )
    owner_entity: Mapped["Entity | None"] = relationship(
        "Entity",
        foreign_keys=[owner_entity_id],
    )

    def __repr__(self) -> str:
        """Return string representation of the owner."""
        return (
            f"<Owner(id={self.id}, name='{self.owner_name}', "
            f"ownership={self.ownership_percentage}%)>"
        )
