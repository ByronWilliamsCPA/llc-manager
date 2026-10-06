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


def downgrade() -> None:
    """Downgrade database schema.

    PostgreSQL cannot drop an enum label, so ``document_type_enum`` is rebuilt
    without the estate-planning labels. The downgrade refuses to run while any
    document row still uses them.

    Raises:
        RuntimeError: If any document row uses one of the new document types.
    """
    bind = op.get_bind()
    in_use = bind.execute(
        sa.text(
            "SELECT count(*) FROM documents WHERE document_type::text = ANY(:labels)"
        ),
        {"labels": list(_NEW_DOCUMENT_TYPES)},
    ).scalar_one()
    if in_use:
        message = (
            f"{in_use} document rows use an estate-planning document type; "
            "reassign or remove them before downgrading."
        )
        raise RuntimeError(message)

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
