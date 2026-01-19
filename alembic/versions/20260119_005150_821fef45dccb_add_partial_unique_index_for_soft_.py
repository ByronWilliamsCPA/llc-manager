"""Add partial unique index for soft deletes.

Revision ID: 821fef45dccb
Revises: 0b8d73696951
Create Date: 2026-01-19 00:51:50.895686+00:00
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "821fef45dccb"
down_revision: str | None = "0b8d73696951"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade database schema.

    Replace the full unique index on EIN with a partial unique index
    that only applies to active (non-deleted) entities. This allows
    soft-deleted entities to have duplicate EINs while maintaining
    uniqueness for active entities.
    """
    # Drop the existing unique index on EIN
    op.drop_index("ix_entities_ein", table_name="entities")

    # Create partial unique index for active entities only
    # is_active = true AND deleted_at IS NULL ensures EIN uniqueness
    # only for active, non-deleted entities
    op.execute(
        """
        CREATE UNIQUE INDEX ix_entities_ein_active
        ON entities (ein)
        WHERE is_active = true AND deleted_at IS NULL
        """
    )

    # Also add partial unique index for file_number on state_registrations
    # to allow soft-deleted registrations to have same file_number
    op.drop_index(
        "ix_state_registrations_file_number", table_name="state_registrations"
    )
    op.execute(
        """
        CREATE UNIQUE INDEX ix_state_registrations_file_number_active
        ON state_registrations (file_number)
        WHERE deleted_at IS NULL
        """
    )


def downgrade() -> None:
    """Downgrade database schema."""
    # Drop the partial unique indexes
    op.drop_index("ix_entities_ein_active", table_name="entities")
    op.drop_index(
        "ix_state_registrations_file_number_active", table_name="state_registrations"
    )

    # Recreate the original non-partial indexes
    op.create_index("ix_entities_ein", "entities", ["ein"], unique=True)
    op.create_index(
        "ix_state_registrations_file_number",
        "state_registrations",
        ["file_number"],
        unique=False,
    )
