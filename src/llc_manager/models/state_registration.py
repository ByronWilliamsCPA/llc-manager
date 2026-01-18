"""State registration model for tracking entity registrations in various states."""

from datetime import date
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Date, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from llc_manager.db.base import AuditMixin, Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from llc_manager.models.entity import Entity


class RegistrationStatus(StrEnum):
    """Status of state registration."""

    ACTIVE = "active"
    PENDING = "pending"
    EXPIRED = "expired"
    WITHDRAWN = "withdrawn"
    REVOKED = "revoked"
    SUSPENDED = "suspended"
    REINSTATED = "reinstated"


class RegistrationType(StrEnum):
    """Type of state registration."""

    DOMESTIC = "domestic"  # State of formation
    FOREIGN = "foreign"  # Registered to do business in another state
    ASSUMED_NAME = "assumed_name"  # DBA registration
    PROFESSIONAL = "professional"  # Professional license
    SPECIALTY = "specialty"  # Other specialty registration


class StateRegistration(Base, UUIDPrimaryKeyMixin, AuditMixin):
    """Represents a state registration for an entity.

    Attributes:
        entity_id: Foreign key to the owning entity.
        state: Two-letter state abbreviation.
        registration_type: Type of registration in this state.
        status: Current status of the registration.
        file_number: State-assigned registration/file number.
        registration_date: Date of initial registration.
        effective_date: Date registration became effective.
        expiration_date: Date registration expires (if applicable).
        annual_report_due: Date annual report is due.
        last_annual_report: Date of last filed annual report.
        next_renewal_date: Date of next required renewal.
        filing_fee: Cost of registration filing.
        annual_fee: Annual fee for maintaining registration.
        registered_name: Name registered in this state (may differ from legal name).
        notes: Additional notes about the registration.
        is_good_standing: Whether the entity is in good standing.
    """

    __tablename__ = "state_registrations"
    __table_args__ = (
        UniqueConstraint(
            "entity_id", "state", "registration_type", name="uq_entity_state_type"
        ),
    )

    # Entity relationship
    entity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # State information
    state: Mapped[str] = mapped_column(String(2), nullable=False, index=True)
    registration_type: Mapped[RegistrationType] = mapped_column(
        Enum(RegistrationType, name="registration_type_enum"),
        nullable=False,
        default=RegistrationType.DOMESTIC,
    )
    status: Mapped[RegistrationStatus] = mapped_column(
        Enum(RegistrationStatus, name="registration_status_enum"),
        nullable=False,
        default=RegistrationStatus.ACTIVE,
    )
    file_number: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True
    )
    registered_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Important dates
    registration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    annual_report_due: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_annual_report: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_renewal_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Fees
    filing_fee: Mapped[str | None] = mapped_column(String(50), nullable=True)
    annual_fee: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Additional info
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_good_standing: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships
    entity: Mapped["Entity"] = relationship(
        "Entity", back_populates="state_registrations"
    )

    def __repr__(self) -> str:
        """Return string representation of the state registration."""
        return (
            f"<StateRegistration(id={self.id}, state='{self.state}', "
            f"type='{self.registration_type}', status='{self.status}')>"
        )
