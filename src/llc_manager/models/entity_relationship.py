"""Entity relationship model for tracking relationships between entities."""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Date, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from llc_manager.db.base import AuditMixin, Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from llc_manager.models.entity import Entity


class RelationshipType(StrEnum):
    """Types of relationships between entities."""

    PARENT_SUBSIDIARY = "parent_subsidiary"  # Parent owns subsidiary
    HOLDING_COMPANY = "holding_company"  # Holding company structure
    MEMBER = "member"  # One entity is a member of another
    MANAGER = "manager"  # One entity manages another
    JOINT_VENTURE = "joint_venture"  # Joint venture relationship
    AFFILIATE = "affiliate"  # Affiliated entities
    SERIES = "series"  # Series LLC relationship
    DISREGARDED_ENTITY = "disregarded_entity"  # Disregarded entity for tax purposes
    OTHER = "other"


class EntityRelationship(Base, UUIDPrimaryKeyMixin, AuditMixin):
    """Represents a relationship between two entities.

    Attributes:
        parent_entity_id: Foreign key to the parent/controlling entity.
        child_entity_id: Foreign key to the child/controlled entity.
        relationship_type: Type of relationship between entities.
        ownership_percentage: Percentage of ownership (if applicable).
        effective_date: Date the relationship became effective.
        end_date: Date the relationship ended (null if current).
        description: Description of the relationship.
        notes: Additional notes about the relationship.
        is_active: Whether the relationship is currently active.
    """

    __tablename__ = "entity_relationships"
    __table_args__ = (
        UniqueConstraint(
            "parent_entity_id",
            "child_entity_id",
            "relationship_type",
            name="uq_entity_relationship",
        ),
    )

    # Entity relationships
    parent_entity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    child_entity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Relationship details
    relationship_type: Mapped[RelationshipType] = mapped_column(
        Enum(RelationshipType, name="relationship_type_enum"),
        nullable=False,
    )
    ownership_percentage: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,
    )

    # Dates
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Additional info
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships
    parent_entity: Mapped["Entity"] = relationship(
        "Entity",
        foreign_keys=[parent_entity_id],
        back_populates="child_relationships",
    )
    child_entity: Mapped["Entity"] = relationship(
        "Entity",
        foreign_keys=[child_entity_id],
        back_populates="parent_relationships",
    )

    def __repr__(self) -> str:
        """Return string representation of the entity relationship."""
        return (
            f"<EntityRelationship(id={self.id}, type='{self.relationship_type}', "
            f"parent={self.parent_entity_id}, child={self.child_entity_id})>"
        )
