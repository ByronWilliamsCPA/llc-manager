"""Registered agent model for tracking entity registered agents."""

from datetime import date
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Date, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from llc_manager.db.base import AuditMixin, Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from llc_manager.models.entity import Entity


class RegisteredAgent(Base, UUIDPrimaryKeyMixin, AuditMixin):
    """Represents a registered agent for an entity in a specific state.

    Attributes:
        entity_id: Foreign key to the owning entity.
        state: Two-letter state abbreviation where agent is registered.
        agent_name: Name of the registered agent.
        agent_company: Company name of registered agent service (if applicable).
        address: Street address of the registered agent.
        city: City of the registered agent.
        state_address: State of the registered agent address.
        zip_code: ZIP code of the registered agent.
        phone: Phone number of the registered agent.
        email: Email address of the registered agent.
        effective_date: Date agent became effective.
        expiration_date: Date agent service expires.
        renewal_date: Date agent service must be renewed.
        annual_cost: Annual cost of registered agent service.
        account_number: Account number with the registered agent service.
        notes: Additional notes about the registered agent.
        is_active: Whether this is the current registered agent.
    """

    __tablename__ = "registered_agents"
    __table_args__ = (
        UniqueConstraint(
            "entity_id", "state", "is_active", name="uq_entity_state_active_agent"
        ),
    )

    # Entity relationship
    entity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # State and agent information
    state: Mapped[str] = mapped_column(String(2), nullable=False, index=True)
    agent_name: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_company: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Agent address
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state_address: Mapped[str | None] = mapped_column(String(2), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Contact information
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Service dates
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    renewal_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Cost and account
    annual_cost: Mapped[str | None] = mapped_column(String(50), nullable=True)
    account_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Additional info
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships
    entity: Mapped["Entity"] = relationship(
        "Entity", back_populates="registered_agents"
    )

    def __repr__(self) -> str:
        """Return string representation of the registered agent."""
        return (
            f"<RegisteredAgent(id={self.id}, state='{self.state}', "
            f"agent='{self.agent_name}')>"
        )

    @property
    def full_address(self) -> str:
        """Return the full formatted address."""
        parts = [self.address]
        if self.city and self.state_address:
            parts.append(f"{self.city}, {self.state_address}")
        if self.zip_code:
            parts.append(self.zip_code)
        return "\n".join(filter(None, parts))
