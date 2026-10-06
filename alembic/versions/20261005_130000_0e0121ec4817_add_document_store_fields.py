"""Add document store fields: category, sha256, consent, estate document types.

Revision ID: 0e0121ec4817
Revises: 316e25bc258b
Create Date: 2026-10-05 13:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0e0121ec4817"  # pragma: allowlist secret
down_revision: str | None = "316e25bc258b"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# SQLAlchemy stores enum member NAMES, so the PostgreSQL labels are upper case.
_CATEGORY_LABELS = (
    "ESTATE_PLANNING",
    "LLCS",
    "TRUSTS",
    "TAX_RETURNS",
    "INSURANCE",
    "PERSONAL_RECORDS",
    "OTHER",
)
_NEW_DOCUMENT_TYPES = (
    "WILL",
    "TRUST_AGREEMENT",
    "POWER_OF_ATTORNEY",
    "HEALTHCARE_DIRECTIVE",
)
_OLD_DOCUMENT_TYPES = (
    "ARTICLES_OF_ORGANIZATION",
    "ARTICLES_OF_INCORPORATION",
    "CERTIFICATE_OF_FORMATION",
    "OPERATING_AGREEMENT",
    "BYLAWS",
    "PARTNERSHIP_AGREEMENT",
    "MEETING_MINUTES",
    "ANNUAL_MEETING",
    "SPECIAL_MEETING",
    "WRITTEN_CONSENT",
    "ANNUAL_REPORT",
    "AMENDMENT",
    "STATEMENT_OF_INFORMATION",
    "CERTIFICATE_OF_GOOD_STANDING",
    "FOREIGN_QUALIFICATION",
    "EIN_LETTER",
    "TAX_RETURN",
    "TAX_ELECTION",
    "BANK_RESOLUTION",
    "SIGNATURE_CARD",
    "CONTRACT",
    "LEASE",
    "INSURANCE_POLICY",
    "MEMBERSHIP_CERTIFICATE",
    "STOCK_CERTIFICATE",
    "TRANSFER_AGREEMENT",
    "CORRESPONDENCE",
    "OTHER",
)

_category_enum = sa.Enum(*_CATEGORY_LABELS, name="document_category_enum")

# A fixed literal (no interpolation); tests/unit/test_migration_0e0121ec4817.py
# checks that it names exactly the labels in _NEW_DOCUMENT_TYPES.
_IN_USE_SQL = (
    "SELECT count(*) FROM documents WHERE document_type::text IN "
    "('WILL', 'TRUST_AGREEMENT', 'POWER_OF_ATTORNEY', 'HEALTHCARE_DIRECTIVE')"
)
_IN_USE_MESSAGE = (
    "document rows use an estate-planning document type; "
    "reassign or remove them before downgrading."
)


def upgrade() -> None:
    """Upgrade database schema.

    Adds estate-planning labels to ``document_type_enum`` and the columns
    ``category`` (default ``OTHER``), ``sha256`` and ``consent_on_file``
    (default false) to ``documents``, plus indexes for the list endpoint.
    """
    with op.get_context().autocommit_block():
        for label in _NEW_DOCUMENT_TYPES:
            op.execute(
                f"ALTER TYPE document_type_enum ADD VALUE IF NOT EXISTS '{label}'"
            )

    _category_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "documents",
        sa.Column(
            "category",
            _category_enum,
            nullable=False,
            server_default="OTHER",
        ),
    )
    op.add_column("documents", sa.Column("sha256", sa.String(length=64), nullable=True))
    op.add_column(
        "documents",
        sa.Column(
            "consent_on_file",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(op.f("ix_documents_category"), "documents", ["category"])
    op.create_index(op.f("ix_documents_sha256"), "documents", ["sha256"])
    op.create_index("ix_documents_updated_at", "documents", ["updated_at"])


def _refuse_if_new_types_in_use() -> None:
    """Stop the downgrade while any document uses an estate-planning type.

    Raises:
        RuntimeError: If any document row uses one of the new types (online).
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

    PostgreSQL cannot drop an enum label, so ``document_type_enum`` is rebuilt
    without the estate-planning labels. The downgrade refuses to run while any
    document row still uses them, and the check runs before anything is
    dropped. In offline (``--sql``) mode the emitted script raises the same
    refusal from the database. A document row that still uses a new type makes
    ``_refuse_if_new_types_in_use`` raise ``RuntimeError``.

    """
    # #EDGE: Data integrity - the guard must run before any drop; offline mode
    # cannot query, so it emits a PL/pgSQL block that fails the script.
    # #VERIFY: alembic downgrade 316e25bc258b --sql from 0e0121ec4817 shows the
    # DO block first.
    _refuse_if_new_types_in_use()
    bind = op.get_bind()

    op.drop_index("ix_documents_updated_at", table_name="documents")
    op.drop_index(op.f("ix_documents_sha256"), table_name="documents")
    op.drop_index(op.f("ix_documents_category"), table_name="documents")
    op.drop_column("documents", "consent_on_file")
    op.drop_column("documents", "sha256")
    op.drop_column("documents", "category")
    _category_enum.drop(bind, checkfirst=True)

    labels = ", ".join(f"'{label}'" for label in _OLD_DOCUMENT_TYPES)
    op.execute("ALTER TYPE document_type_enum RENAME TO document_type_enum_old")
    op.execute(f"CREATE TYPE document_type_enum AS ENUM ({labels})")
    op.execute(
        "ALTER TABLE documents ALTER COLUMN document_type TYPE document_type_enum "
        "USING document_type::text::document_type_enum"
    )
    op.execute("DROP TYPE document_type_enum_old")
