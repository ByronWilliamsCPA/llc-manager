"""Add individual and household entity types and Xero mapping fields.

Revision ID: 316e25bc258b
Revises: 821fef45dccb
Create Date: 2026-10-05 12:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "316e25bc258b"  # pragma: allowlist secret
down_revision: str | None = "821fef45dccb"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# SQLAlchemy stores enum member NAMES, so the PostgreSQL labels are upper case.
_OLD_ENTITY_TYPES = (
    "LLC",
    "CORPORATION",
    "S_CORPORATION",
    "PARTNERSHIP",
    "SOLE_PROPRIETORSHIP",
    "TRUST",
    "NON_PROFIT",
    "OTHER",
)
_NEW_ENTITY_TYPES = ("INDIVIDUAL", "HOUSEHOLD")

_IN_USE_SQL = (
    "SELECT count(*) FROM entities "
    "WHERE entity_type::text IN ('INDIVIDUAL', 'HOUSEHOLD')"
)
_IN_USE_MESSAGE = (
    "entity rows use the individual or household type; "
    "reassign or remove them before downgrading."
)


def upgrade() -> None:
    """Upgrade database schema.

    Adds the ``INDIVIDUAL`` and ``HOUSEHOLD`` labels to ``entity_type_enum``,
    ``entities.xero_tenant_id`` with a partial unique index over non-deleted
    rows, and ``bank_accounts.xero_account_id`` with a partial unique index
    over non-deleted rows.
    """
    # PostgreSQL does not let a transaction use an enum label it added (and
    # before version 12 refuses ALTER TYPE ... ADD VALUE inside a transaction
    # block at all), so the labels are added and committed in an autocommit
    # block before the rest of the migration runs.
    # #CRITICAL: Data integrity - the labels stay committed even if a later
    # step of this upgrade fails, because they are outside its transaction.
    # IF NOT EXISTS makes re-running the upgrade after such a failure safe.
    # #VERIFY: on a scratch database, run upgrade, downgrade, and upgrade again
    # and confirm each succeeds.
    with op.get_context().autocommit_block():
        for label in _NEW_ENTITY_TYPES:
            op.execute(f"ALTER TYPE entity_type_enum ADD VALUE IF NOT EXISTS '{label}'")

    op.add_column(
        "entities",
        sa.Column("xero_tenant_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_entities_xero_tenant_id_active",
        "entities",
        ["xero_tenant_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.add_column(
        "bank_accounts",
        sa.Column("xero_account_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_bank_accounts_xero_account_id_active",
        "bank_accounts",
        ["xero_account_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def _refuse_if_new_types_in_use() -> None:
    """Stop the downgrade while any entity uses an individual or household type.

    Raises:
        RuntimeError: If any entity row uses one of the new types (online).
    """
    if op.get_context().as_sql:
        op.execute(
            "DO $$ BEGIN "
            f"IF EXISTS ({_IN_USE_SQL.replace('count(*)', '1')}) THEN "
            f"RAISE EXCEPTION '{_IN_USE_MESSAGE}'; "
            "END IF; END $$"
        )
        return
    in_use = op.get_bind().execute(sa.text(_IN_USE_SQL)).scalar_one()
    if in_use:
        message = f"{in_use} {_IN_USE_MESSAGE}"
        raise RuntimeError(message)


def downgrade() -> None:
    """Downgrade database schema.

    PostgreSQL cannot drop an enum label, so the type is rebuilt without the
    two new labels. The downgrade refuses to run while any entity row still
    uses them, rather than silently rewriting or deleting data. The check runs
    before anything is dropped, so a refused downgrade changes nothing even
    without transactional DDL. The guard raises ``RuntimeError`` when any
    entity row uses an individual or household type; in offline (``--sql``)
    mode the emitted script raises the same refusal from the database.
    """
    # #EDGE: Data integrity - the guard must run before any drop; offline
    # mode cannot query, so it emits a PL/pgSQL block that fails the script.
    # #VERIFY: alembic downgrade 821fef45dccb --sql shows the DO block first.
    _refuse_if_new_types_in_use()

    op.drop_index("ix_bank_accounts_xero_account_id_active", table_name="bank_accounts")
    op.drop_column("bank_accounts", "xero_account_id")
    op.drop_index("ix_entities_xero_tenant_id_active", table_name="entities")
    op.drop_column("entities", "xero_tenant_id")

    labels = ", ".join(f"'{label}'" for label in _OLD_ENTITY_TYPES)
    op.execute("ALTER TYPE entity_type_enum RENAME TO entity_type_enum_old")
    op.execute(f"CREATE TYPE entity_type_enum AS ENUM ({labels})")
    op.execute(
        "ALTER TABLE entities ALTER COLUMN entity_type TYPE entity_type_enum "
        "USING entity_type::text::entity_type_enum"
    )
    op.execute("DROP TYPE entity_type_enum_old")
