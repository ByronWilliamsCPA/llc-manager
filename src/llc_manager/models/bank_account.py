"""Bank account model for tracking entity banking information."""

from datetime import date
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Date, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from llc_manager.db.base import AuditMixin, Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from llc_manager.models.entity import Entity


class AccountType(StrEnum):
    """Types of bank accounts."""

    CHECKING = "checking"
    SAVINGS = "savings"
    MONEY_MARKET = "money_market"
    CD = "cd"
    BUSINESS_CHECKING = "business_checking"
    BUSINESS_SAVINGS = "business_savings"
    MERCHANT_ACCOUNT = "merchant_account"
    PAYROLL = "payroll"
    OTHER = "other"


class BankAccount(Base, UUIDPrimaryKeyMixin, AuditMixin):
    """Represents a bank account associated with an entity.

    Attributes:
        entity_id: Foreign key to the owning entity.
        bank_name: Name of the bank or financial institution.
        account_name: Name on the account.
        account_type: Type of bank account.
        account_number_last4: Last 4 digits of account number.
        routing_number: Bank routing number.
        account_nickname: Nickname for easy identification.
        opened_date: Date account was opened.
        closed_date: Date account was closed (null if open).
        primary_contact: Primary contact at the bank.
        contact_phone: Phone number for the contact.
        contact_email: Email for the contact.
        branch_address: Address of the bank branch.
        online_banking_url: URL for online banking.
        notes: Additional notes about the account.
        is_primary: Whether this is the primary account for the entity.
        is_active: Whether the account is currently active.
    """

    __tablename__ = "bank_accounts"

    # Entity relationship
    entity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Bank information
    bank_name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    account_type: Mapped[AccountType] = mapped_column(
        Enum(AccountType, name="account_type_enum"),
        nullable=False,
        default=AccountType.BUSINESS_CHECKING,
    )
    account_number_last4: Mapped[str | None] = mapped_column(
        String(4), nullable=True
    )  # Only store last 4 for security
    routing_number: Mapped[str | None] = mapped_column(String(9), nullable=True)
    account_nickname: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Dates
    opened_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Contact information
    primary_contact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    branch_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    online_banking_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Additional info
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_primary: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships
    entity: Mapped["Entity"] = relationship("Entity", back_populates="bank_accounts")

    def __repr__(self) -> str:
        """Return string representation of the bank account."""
        return (
            f"<BankAccount(id={self.id}, bank='{self.bank_name}', "
            f"last4='{self.account_number_last4}')>"
        )
