"""Bulk Excel importer for LLC Manager entity data.

Usage::

    uv run python scripts/import_excel.py import data.xlsx
    uv run python scripts/import_excel.py import data.xlsx --dry-run
    uv run python scripts/import_excel.py import data.xlsx --report results.txt

The workbook format is defined in docs/development/data-import-format.md.
"""

from __future__ import annotations

import asyncio
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from uuid import UUID

import click
import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from llc_manager.db.session import AsyncSessionLocal
from llc_manager.models.bank_account import BankAccount
from llc_manager.models.entity import Entity
from llc_manager.models.owner import Owner
from llc_manager.models.registered_agent import RegisteredAgent
from llc_manager.models.state_registration import StateRegistration
from llc_manager.models.tax_filing import TaxFiling

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXPECTED_TABS: list[str] = [
    "Entities",
    "Owners",
    "StateRegistrations",
    "BankAccounts",
    "TaxFilings",
    "RegisteredAgents",
]

# StrEnum values drawn directly from the ORM models.
# #ASSUME: StrEnum values in the ORM models are stable; update here if they change.
VALID_ENTITY_TYPES: frozenset[str] = frozenset(
    [
        "llc",
        "corporation",
        "s_corporation",
        "partnership",
        "sole_proprietorship",
        "trust",
        "non_profit",
        "other",
    ]
)
VALID_OWNERSHIP_TYPES: frozenset[str] = frozenset(
    [
        "member",
        "managing_member",
        "shareholder",
        "general_partner",
        "limited_partner",
        "beneficiary",
        "trustee",
        "director",
        "officer",
    ]
)
VALID_REGISTRATION_STATUSES: frozenset[str] = frozenset(
    [
        "active",
        "pending",
        "expired",
        "withdrawn",
        "revoked",
        "suspended",
        "reinstated",
    ]
)
VALID_REGISTRATION_TYPES: frozenset[str] = frozenset(
    ["domestic", "foreign", "assumed_name", "professional", "specialty"]
)
VALID_ACCOUNT_TYPES: frozenset[str] = frozenset(
    [
        "checking",
        "savings",
        "money_market",
        "cd",
        "business_checking",
        "business_savings",
        "merchant_account",
        "payroll",
        "other",
    ]
)
VALID_TAX_FILING_TYPES: frozenset[str] = frozenset(
    [
        "federal_income",
        "state_income",
        "franchise_tax",
        "sales_tax",
        "payroll_tax",
        "property_tax",
        "estimated_tax",
        "annual_report",
        "k1",
        "other",
    ]
)
VALID_FILING_FREQUENCIES: frozenset[str] = frozenset(
    ["annual", "quarterly", "monthly", "semi_annual", "one_time"]
)
VALID_FILING_STATUSES: frozenset[str] = frozenset(
    ["pending", "filed", "extended", "late", "not_required"]
)

# EIN format: XX-XXXXXXX (2 digits, hyphen, 7 digits)
EIN_PATTERN = re.compile(r"^\d{2}-\d{7}$")

# ---------------------------------------------------------------------------
# Severity levels
# ---------------------------------------------------------------------------

LEVELS = ("ERROR", "WARNING", "INFO")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ValidationMessage:
    """A single validation finding."""

    level: str  # "ERROR" | "WARNING" | "INFO"
    tab: str
    row: int
    field: str
    message: str


@dataclass
class ImportResult:
    """Summary of one import run."""

    messages: list[ValidationMessage] = field(default_factory=list)
    inserted: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    updated: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    skipped: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    @property
    def error_count(self) -> int:
        """Number of ERROR-level messages."""
        return sum(1 for m in self.messages if m.level == "ERROR")

    @property
    def warning_count(self) -> int:
        """Number of WARNING-level messages."""
        return sum(1 for m in self.messages if m.level == "WARNING")

    @property
    def info_count(self) -> int:
        """Number of INFO-level messages."""
        return sum(1 for m in self.messages if m.level == "INFO")


# ---------------------------------------------------------------------------
# ExcelReader
# ---------------------------------------------------------------------------


class ExcelReader:
    """Reads an Excel workbook and returns rows per tab as list[dict].

    Args:
        path: Path to the .xlsx workbook.
    """

    def __init__(self, path: Path) -> None:
        """Initialise with the workbook path."""
        self._path = path
        # #ASSUME: openpyxl is available; already in pyproject.toml dependencies.
        self._wb: dict[str, pd.DataFrame] | None = None

    def load(self) -> None:
        """Load all sheets from the workbook into memory."""
        # #CRITICAL: External resource - file must exist and be readable.
        # #VERIFY: Validate path before this call; click handles missing-file error.
        self._wb = pd.read_excel(
            self._path,
            sheet_name=None,  # Load all sheets
            dtype=str,  # Keep everything as strings; coercion is done in FieldMapper
            keep_default_na=False,
        )

    def tabs(self) -> list[str]:
        """Return the list of sheet names present in the workbook."""
        if self._wb is None:
            raise RuntimeError("Call load() before tabs()")
        return list(self._wb.keys())

    def rows(self, tab_name: str) -> list[dict[str, Any]]:
        """Return rows from a named tab as a list of raw dicts.

        Args:
            tab_name: The exact sheet name.

        Returns:
            List of row dicts; each key is the column header.
        """
        if self._wb is None:
            raise RuntimeError("Call load() before rows()")
        if tab_name not in self._wb:
            return []
        df: pd.DataFrame = self._wb[tab_name]
        records: list[dict[str, Any]] = df.to_dict(orient="records")
        # Skip rows where every cell is empty/whitespace.
        return [
            r
            for r in records
            if any(str(v).strip() for v in r.values() if v is not None)
        ]


# ---------------------------------------------------------------------------
# FieldMapper
# ---------------------------------------------------------------------------

# Column aliases: human-friendly header names -> ORM field names.
# These are the common variant headers that appear in "real-world" spreadsheets.
_ENTITY_ALIASES: dict[str, str] = {
    "Company Name": "legal_name",
    "LLC Name": "legal_name",
    "Legal Name": "legal_name",
    "EIN": "ein",
    "Tax ID": "ein",
    "Entity Type": "entity_type",
    "Formation State": "formation_state",
    "State of Formation": "formation_state",
    "Formation Date": "formation_date",
    "Date of Formation": "formation_date",
    "Fiscal Year End": "fiscal_year_end",
    "FYE": "fiscal_year_end",
    "Active": "is_active",
    "Is Active": "is_active",
    "DBA Names": "dba_names",
    "DBA": "dba_names",
}

_OWNER_ALIASES: dict[str, str] = {
    "Entity Name": "entity_legal_name",
    "Owner Name": "owner_name",
    "Ownership Type": "ownership_type",
    "Ownership %": "ownership_percentage",
    "Ownership Percentage": "ownership_percentage",
    "Start Date": "start_date",
    "End Date": "end_date",
    "EIN/SSN": "ein_or_ssn",
    "Active": "is_active",
}

_STATE_REG_ALIASES: dict[str, str] = {
    "Entity Name": "entity_legal_name",
    "State": "state",
    "Registration Type": "registration_type",
    "Status": "status",
    "File Number": "file_number",
    "Registration Date": "registration_date",
    "Good Standing": "is_good_standing",
    "Is Good Standing": "is_good_standing",
}

_BANK_ACCOUNT_ALIASES: dict[str, str] = {
    "Entity Name": "entity_legal_name",
    "Bank Name": "bank_name",
    "Institution Name": "bank_name",
    "Account Type": "account_type",
    "Account Number Last 4": "account_number_last4",
    "Last 4": "account_number_last4",
    "Routing Number": "routing_number",
    "Opened Date": "opened_date",
    "Closed Date": "closed_date",
    "Primary": "is_primary",
    "Is Primary": "is_primary",
    "Active": "is_active",
}

_TAX_FILING_ALIASES: dict[str, str] = {
    "Entity Name": "entity_legal_name",
    "Filing Type": "filing_type",
    "Jurisdiction": "jurisdiction",
    "Tax Year": "tax_year",
    "Frequency": "frequency",
    "Status": "status",
    "Tax Period": "tax_period",
    "Due Date": "due_date",
    "Filed Date": "filed_date",
    "Form Number": "form_number",
}

_REGISTERED_AGENT_ALIASES: dict[str, str] = {
    "Entity Name": "entity_legal_name",
    "State": "state",
    "Agent Name": "agent_name",
    "Agent Company": "agent_company",
    "Effective Date": "effective_date",
    "Expiration Date": "expiration_date",
    "Renewal Date": "renewal_date",
    "Annual Cost": "annual_cost",
    "Account Number": "account_number",
    "Active": "is_active",
}

_TAB_ALIAS_MAPS: dict[str, dict[str, str]] = {
    "Entities": _ENTITY_ALIASES,
    "Owners": _OWNER_ALIASES,
    "StateRegistrations": _STATE_REG_ALIASES,
    "BankAccounts": _BANK_ACCOUNT_ALIASES,
    "TaxFilings": _TAX_FILING_ALIASES,
    "RegisteredAgents": _REGISTERED_AGENT_ALIASES,
}


class FieldMapper:
    """Maps raw spreadsheet column names to ORM field names and normalises values.

    Args:
        tab_name: The sheet name being processed.
    """

    def __init__(self, tab_name: str) -> None:
        """Initialise for the given tab."""
        self._alias_map: dict[str, str] = _TAB_ALIAS_MAPS.get(tab_name, {})

    def map_row(self, raw_row: dict[str, Any]) -> dict[str, Any]:
        """Translate raw column keys to ORM field names and normalise values.

        Args:
            raw_row: Row dict keyed by spreadsheet column headers.

        Returns:
            Dict with ORM field names; empty strings converted to None.
        """
        mapped: dict[str, Any] = {}
        for col, value in raw_row.items():
            key = self._alias_map.get(col, col)  # apply alias or keep as-is
            mapped[key] = self._normalise(value)
        return mapped

    @staticmethod
    def _normalise(value: Any) -> Any:
        """Strip whitespace from strings; convert empty strings to None."""
        if isinstance(value, str):
            return value.strip() or None
        return value

    @staticmethod
    def coerce_bool(value: Any) -> bool | None:
        """Coerce a spreadsheet boolean cell to Python bool.

        Args:
            value: Raw cell value (string or None).

        Returns:
            True/False, or None if value is absent.
        """
        if value is None:
            return None
        s = str(value).strip().lower()
        if s in ("true", "1", "yes"):
            return True
        if s in ("false", "0", "no"):
            return False
        return None

    @staticmethod
    def coerce_date(value: Any) -> date | None:
        """Parse a YYYY-MM-DD date string into a date object.

        Args:
            value: Raw cell value.

        Returns:
            Parsed date, or None if value is absent.

        Raises:
            ValueError: If the string cannot be parsed.
        """
        if value is None:
            return None
        s = str(value).strip()
        if not s:
            return None
        return date.fromisoformat(s)

    @staticmethod
    def coerce_decimal(value: Any) -> Decimal | None:
        """Parse a numeric string into a Decimal.

        Args:
            value: Raw cell value.

        Returns:
            Decimal, or None if value is absent.

        Raises:
            InvalidOperation: If the string cannot be parsed.
        """
        if value is None:
            return None
        s = str(value).strip()
        if not s:
            return None
        return Decimal(s)

    @staticmethod
    def coerce_int(value: Any) -> int | None:
        """Parse an integer string.

        Args:
            value: Raw cell value.

        Returns:
            int, or None if value is absent.

        Raises:
            ValueError: If the string cannot be parsed.
        """
        if value is None:
            return None
        s = str(value).strip()
        if not s:
            return None
        return int(s)


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class Validator:
    """Validates a row against per-field business rules.

    Appends ValidationMessage objects to a shared ImportResult.

    Args:
        result: The shared ImportResult accumulator.
    """

    def __init__(self, result: ImportResult) -> None:
        """Initialise with the shared result accumulator."""
        self._result = result
        # Track ownership percentages per entity for sum-to-100 check.
        # #ASSUME: Data integrity - all owner rows for an entity may not be in
        # contiguous rows; accumulate and check at validate_ownership_sums().
        self._ownership_buckets: dict[str, list[tuple[int, Decimal]]] = defaultdict(
            list
        )

    def _add(
        self, level: str, tab: str, row: int, field_name: str, message: str
    ) -> None:
        self._result.messages.append(
            ValidationMessage(
                level=level,
                tab=tab,
                row=row,
                field=field_name,
                message=message,
            )
        )

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _validate_required(
        self, value: Any, tab: str, row: int, field_name: str
    ) -> bool:
        """Return True if value is present; add ERROR and return False otherwise."""
        if value is None or str(value).strip() == "":
            self._add("ERROR", tab, row, field_name, f"{field_name} is required")
            return False
        return True

    def _validate_enum(
        self,
        value: Any,
        allowed: frozenset[str],
        tab: str,
        row: int,
        field_name: str,
    ) -> bool:
        """Return True if value is in the allowed set, else ERROR."""
        if value is None:
            return True  # Absence is checked by _validate_required separately.
        s = str(value).strip().lower()
        if s not in allowed:
            self._add(
                "ERROR",
                tab,
                row,
                field_name,
                f"Invalid {field_name} '{value}'. Allowed: {sorted(allowed)}",
            )
            return False
        return True

    def _validate_ein(self, value: Any, tab: str, row: int, field_name: str) -> bool:
        """Validate EIN format XX-XXXXXXX.

        Args:
            value: Raw EIN string.
            tab: Sheet name.
            row: 1-based row number.
            field_name: Field label for messages.

        Returns:
            True if valid or absent.
        """
        if value is None:
            return True
        s = str(value).strip()
        # #CRITICAL: Data integrity - EIN format enforced via regex to prevent
        # malformed identifiers reaching the database.
        if not EIN_PATTERN.fullmatch(s):
            self._add(
                "ERROR",
                tab,
                row,
                field_name,
                f"EIN '{s}' must match format XX-XXXXXXX (e.g. 12-3456789)",
            )
            return False
        return True

    def _validate_date_not_future(
        self, value: Any, tab: str, row: int, field_name: str
    ) -> bool:
        """Check that a date is not in the future (for formation dates).

        Args:
            value: Raw date string.
            tab: Sheet name.
            row: 1-based row number.
            field_name: Field label for messages.

        Returns:
            True if valid or absent.
        """
        if value is None:
            return True
        try:
            parsed = date.fromisoformat(str(value).strip())
        except ValueError:
            self._add(
                "ERROR",
                tab,
                row,
                field_name,
                f"Cannot parse date '{value}'; expected YYYY-MM-DD",
            )
            return False
        if parsed > datetime.now(UTC).date():
            self._add(
                "WARNING",
                tab,
                row,
                field_name,
                f"{field_name} '{parsed}' is in the future",
            )
        return True

    def _validate_date_parseable(
        self, value: Any, tab: str, row: int, field_name: str
    ) -> bool:
        """Verify a date string is parseable as YYYY-MM-DD.

        Args:
            value: Raw date string.
            tab: Sheet name.
            row: 1-based row number.
            field_name: Field label for messages.

        Returns:
            True if valid or absent.
        """
        if value is None:
            return True
        try:
            date.fromisoformat(str(value).strip())
        except ValueError:
            self._add(
                "ERROR",
                tab,
                row,
                field_name,
                f"Cannot parse date '{value}'; expected YYYY-MM-DD",
            )
            return False
        return True

    def _validate_percentage(
        self, value: Any, tab: str, row: int, field_name: str
    ) -> bool:
        """Validate a percentage is between 0.00 and 100.00.

        Args:
            value: Raw percentage string.
            tab: Sheet name.
            row: 1-based row number.
            field_name: Field label for messages.

        Returns:
            True if valid or absent.
        """
        if value is None:
            return True
        try:
            pct = Decimal(str(value).strip())
        except InvalidOperation:
            self._add(
                "ERROR",
                tab,
                row,
                field_name,
                f"'{value}' is not a valid decimal for {field_name}",
            )
            return False
        if not (Decimal("0.00") <= pct <= Decimal("100.00")):
            self._add(
                "ERROR",
                tab,
                row,
                field_name,
                f"{field_name} {pct} is outside the allowed range 0.00-100.00",
            )
            return False
        return True

    # ------------------------------------------------------------------
    # Per-tab validators
    # ------------------------------------------------------------------

    def validate_entity_row(self, row_dict: dict[str, Any], row_idx: int) -> bool:
        """Validate one row from the Entities tab.

        Args:
            row_dict: Mapped row dict.
            row_idx: 1-based row number for messages.

        Returns:
            True if no ERRORs were added for this row.
        """
        tab = "Entities"
        ok = True
        ok &= self._validate_required(
            row_dict.get("legal_name"), tab, row_idx, "legal_name"
        )
        ok &= self._validate_required(
            row_dict.get("entity_type"), tab, row_idx, "entity_type"
        )
        ok &= self._validate_enum(
            row_dict.get("entity_type"), VALID_ENTITY_TYPES, tab, row_idx, "entity_type"
        )
        ok &= self._validate_required(row_dict.get("ein"), tab, row_idx, "ein")
        ok &= self._validate_ein(row_dict.get("ein"), tab, row_idx, "ein")
        ok &= self._validate_date_not_future(
            row_dict.get("formation_date"), tab, row_idx, "formation_date"
        )
        return ok

    def validate_owner_row(
        self,
        row_dict: dict[str, Any],
        row_idx: int,
        known_entity_names: frozenset[str],
    ) -> bool:
        """Validate one row from the Owners tab.

        Args:
            row_dict: Mapped row dict.
            row_idx: 1-based row number for messages.
            known_entity_names: Set of legal_name values already accepted in Entities.

        Returns:
            True if no ERRORs were added for this row.
        """
        tab = "Owners"
        ok = True
        entity_name = row_dict.get("entity_legal_name")
        ok &= self._validate_required(entity_name, tab, row_idx, "entity_legal_name")
        if entity_name and entity_name not in known_entity_names:
            self._add(
                "ERROR",
                tab,
                row_idx,
                "entity_legal_name",
                f"No entity found with legal_name '{entity_name}'",
            )
            ok = False

        ok &= self._validate_required(
            row_dict.get("owner_name"), tab, row_idx, "owner_name"
        )
        ok &= self._validate_required(
            row_dict.get("ownership_percentage"), tab, row_idx, "ownership_percentage"
        )
        ok &= self._validate_enum(
            row_dict.get("ownership_type"),
            VALID_OWNERSHIP_TYPES,
            tab,
            row_idx,
            "ownership_type",
        )
        ok &= self._validate_percentage(
            row_dict.get("ownership_percentage"), tab, row_idx, "ownership_percentage"
        )
        ok &= self._validate_date_parseable(
            row_dict.get("start_date"), tab, row_idx, "start_date"
        )
        ok &= self._validate_date_parseable(
            row_dict.get("end_date"), tab, row_idx, "end_date"
        )

        # Accumulate ownership percentages for sum check.
        # #CRITICAL: Data integrity - ownership percentages must sum to 100% per entity.
        if entity_name and row_dict.get("ownership_percentage") is not None:
            try:
                pct = Decimal(str(row_dict["ownership_percentage"]).strip())
                self._ownership_buckets[entity_name].append((row_idx, pct))
            except InvalidOperation:
                pass  # Already reported above.

        return ok

    def validate_state_registration_row(
        self,
        row_dict: dict[str, Any],
        row_idx: int,
        known_entity_names: frozenset[str],
    ) -> bool:
        """Validate one row from the StateRegistrations tab.

        Args:
            row_dict: Mapped row dict.
            row_idx: 1-based row number for messages.
            known_entity_names: Set of accepted entity names.

        Returns:
            True if no ERRORs were added for this row.
        """
        tab = "StateRegistrations"
        ok = True
        entity_name = row_dict.get("entity_legal_name")
        ok &= self._validate_required(entity_name, tab, row_idx, "entity_legal_name")
        if entity_name and entity_name not in known_entity_names:
            self._add(
                "ERROR",
                tab,
                row_idx,
                "entity_legal_name",
                f"No entity found with legal_name '{entity_name}'",
            )
            ok = False
        ok &= self._validate_required(row_dict.get("state"), tab, row_idx, "state")
        ok &= self._validate_enum(
            row_dict.get("registration_type"),
            VALID_REGISTRATION_TYPES,
            tab,
            row_idx,
            "registration_type",
        )
        ok &= self._validate_enum(
            row_dict.get("status"),
            VALID_REGISTRATION_STATUSES,
            tab,
            row_idx,
            "status",
        )
        ok &= self._validate_date_parseable(
            row_dict.get("registration_date"), tab, row_idx, "registration_date"
        )
        return ok

    def validate_bank_account_row(
        self,
        row_dict: dict[str, Any],
        row_idx: int,
        known_entity_names: frozenset[str],
    ) -> bool:
        """Validate one row from the BankAccounts tab.

        Args:
            row_dict: Mapped row dict.
            row_idx: 1-based row number for messages.
            known_entity_names: Set of accepted entity names.

        Returns:
            True if no ERRORs were added for this row.
        """
        tab = "BankAccounts"
        ok = True
        entity_name = row_dict.get("entity_legal_name")
        ok &= self._validate_required(entity_name, tab, row_idx, "entity_legal_name")
        if entity_name and entity_name not in known_entity_names:
            self._add(
                "ERROR",
                tab,
                row_idx,
                "entity_legal_name",
                f"No entity found with legal_name '{entity_name}'",
            )
            ok = False
        ok &= self._validate_required(
            row_dict.get("bank_name"), tab, row_idx, "bank_name"
        )
        ok &= self._validate_enum(
            row_dict.get("account_type"),
            VALID_ACCOUNT_TYPES,
            tab,
            row_idx,
            "account_type",
        )
        return ok

    def validate_tax_filing_row(
        self,
        row_dict: dict[str, Any],
        row_idx: int,
        known_entity_names: frozenset[str],
    ) -> bool:
        """Validate one row from the TaxFilings tab.

        Args:
            row_dict: Mapped row dict.
            row_idx: 1-based row number for messages.
            known_entity_names: Set of accepted entity names.

        Returns:
            True if no ERRORs were added for this row.
        """
        tab = "TaxFilings"
        ok = True
        entity_name = row_dict.get("entity_legal_name")
        ok &= self._validate_required(entity_name, tab, row_idx, "entity_legal_name")
        if entity_name and entity_name not in known_entity_names:
            self._add(
                "ERROR",
                tab,
                row_idx,
                "entity_legal_name",
                f"No entity found with legal_name '{entity_name}'",
            )
            ok = False
        ok &= self._validate_required(
            row_dict.get("filing_type"), tab, row_idx, "filing_type"
        )
        ok &= self._validate_enum(
            row_dict.get("filing_type"),
            VALID_TAX_FILING_TYPES,
            tab,
            row_idx,
            "filing_type",
        )
        ok &= self._validate_required(
            row_dict.get("jurisdiction"), tab, row_idx, "jurisdiction"
        )
        ok &= self._validate_required(
            row_dict.get("tax_year"), tab, row_idx, "tax_year"
        )
        ok &= self._validate_enum(
            row_dict.get("frequency"),
            VALID_FILING_FREQUENCIES,
            tab,
            row_idx,
            "frequency",
        )
        ok &= self._validate_enum(
            row_dict.get("status"), VALID_FILING_STATUSES, tab, row_idx, "status"
        )
        ok &= self._validate_date_parseable(
            row_dict.get("due_date"), tab, row_idx, "due_date"
        )
        return ok

    def validate_registered_agent_row(
        self,
        row_dict: dict[str, Any],
        row_idx: int,
        known_entity_names: frozenset[str],
    ) -> bool:
        """Validate one row from the RegisteredAgents tab.

        Args:
            row_dict: Mapped row dict.
            row_idx: 1-based row number for messages.
            known_entity_names: Set of accepted entity names.

        Returns:
            True if no ERRORs were added for this row.
        """
        tab = "RegisteredAgents"
        ok = True
        entity_name = row_dict.get("entity_legal_name")
        ok &= self._validate_required(entity_name, tab, row_idx, "entity_legal_name")
        if entity_name and entity_name not in known_entity_names:
            self._add(
                "ERROR",
                tab,
                row_idx,
                "entity_legal_name",
                f"No entity found with legal_name '{entity_name}'",
            )
            ok = False
        ok &= self._validate_required(row_dict.get("state"), tab, row_idx, "state")
        ok &= self._validate_required(
            row_dict.get("agent_name"), tab, row_idx, "agent_name"
        )
        return ok

    def validate_ownership_sums(self) -> None:
        """Emit warnings where total ownership percentage for an entity is not 100%.

        Iterates over accumulated ownership buckets collected during owner-row
        validation and checks that the sum equals exactly 100.00 for each entity.
        """
        for entity_name, entries in self._ownership_buckets.items():
            total = sum(pct for _, pct in entries)
            if total != Decimal("100.00"):
                # Report against the first owner row of this entity.
                first_row = entries[0][0] if entries else 0
                self._result.messages.append(
                    ValidationMessage(
                        level="WARNING",
                        tab="Owners",
                        row=first_row,
                        field="ownership_percentage",
                        message=(
                            f"Ownership percentages for '{entity_name}' "
                            f"sum to {total}, expected 100.00"
                        ),
                    )
                )


# ---------------------------------------------------------------------------
# Importer
# ---------------------------------------------------------------------------


class Importer:
    """Async SQLAlchemy importer using ON CONFLICT DO UPDATE (upsert).

    Args:
        dry_run: If True, operations are validated but never committed.
    """

    def __init__(self, dry_run: bool = False) -> None:
        """Initialise the importer."""
        self._dry_run = dry_run

    async def run(
        self,
        entity_rows: list[dict[str, Any]],
        owner_rows: list[dict[str, Any]],
        state_reg_rows: list[dict[str, Any]],
        bank_account_rows: list[dict[str, Any]],
        tax_filing_rows: list[dict[str, Any]],
        registered_agent_rows: list[dict[str, Any]],
        result: ImportResult,
    ) -> None:
        """Execute the full import in a single async session.

        Args:
            entity_rows: Validated mapped rows from Entities tab.
            owner_rows: Validated mapped rows from Owners tab.
            state_reg_rows: Validated mapped rows from StateRegistrations tab.
            bank_account_rows: Validated mapped rows from BankAccounts tab.
            tax_filing_rows: Validated mapped rows from TaxFilings tab.
            registered_agent_rows: Validated mapped rows from RegisteredAgents tab.
            result: ImportResult accumulator for row counts.
        """
        # #CRITICAL: External resource - DB connection required; fail fast with
        # a readable error if the DB is not reachable.
        async with AsyncSessionLocal() as session:
            try:
                # --- Entities (upsert on legal_name + ein) ---
                entity_id_map: dict[str, UUID] = {}
                for row in entity_rows:
                    row_data = self._prepare_entity(row)
                    if not row_data:
                        result.skipped["Entities"] += 1
                        continue

                    stmt = pg_insert(Entity).values(**row_data)
                    # #CRITICAL: Data integrity - EIN is required per the import format
                    # spec. The (legal_name, ein) pair uniquely identifies an entity for
                    # upsert purposes; a legal_name-only match is not sufficient because
                    # an EIN change indicates a different tax entity. Rows missing EIN
                    # are rejected by the Validator before reaching this point.
                    conflict_target = ["legal_name", "ein"]
                    update_cols = {
                        k: stmt.excluded[k]
                        for k in row_data
                        if k not in ("legal_name", "ein")
                    }
                    stmt = stmt.on_conflict_do_update(
                        index_elements=conflict_target,
                        set_=update_cols,
                    )
                    stmt = stmt.returning(Entity.id, Entity.legal_name)

                    if not self._dry_run:
                        cursor = await session.execute(stmt)
                        row_result = cursor.fetchone()
                        if row_result:
                            entity_id_map[row_result[1]] = row_result[0]
                        result.inserted["Entities"] += 1
                    else:
                        result.inserted["Entities"] += 1

                if not self._dry_run:
                    # Flush entities so child FK lookups can resolve UUIDs.
                    await session.flush()
                    # Reload entity UUID map from DB for accurate FK resolution.
                    legal_names = [
                        r.get("legal_name") for r in entity_rows if r.get("legal_name")
                    ]
                    if legal_names:
                        stmt_q = select(Entity.id, Entity.legal_name).where(
                            Entity.legal_name.in_(legal_names)
                        )
                        rows_q = await session.execute(stmt_q)
                        entity_id_map = {name: eid for eid, name in rows_q.fetchall()}

                # --- Owners ---
                for row in owner_rows:
                    entity_name = row.get("entity_legal_name")
                    entity_id = entity_id_map.get(entity_name) if entity_name else None
                    if entity_id is None and not self._dry_run:
                        result.skipped["Owners"] += 1
                        continue
                    row_data = self._prepare_owner(row)
                    if entity_id is not None:
                        row_data["entity_id"] = entity_id
                    if not self._dry_run:
                        existing_owner = (
                            await session.execute(
                                select(Owner).where(
                                    Owner.entity_id == row_data["entity_id"],
                                    Owner.owner_name == row_data["owner_name"],
                                    Owner.ownership_type == row_data["ownership_type"],
                                )
                            )
                        ).scalar_one_or_none()
                        if existing_owner:
                            result.skipped["Owners"] += 1
                            continue
                        session.add(Owner(**row_data))
                    result.inserted["Owners"] += 1

                # --- StateRegistrations ---
                for row in state_reg_rows:
                    entity_name = row.get("entity_legal_name")
                    entity_id = entity_id_map.get(entity_name) if entity_name else None
                    if entity_id is None and not self._dry_run:
                        result.skipped["StateRegistrations"] += 1
                        continue
                    row_data = self._prepare_state_registration(row)
                    if entity_id is not None:
                        row_data["entity_id"] = entity_id
                    if not self._dry_run:
                        stmt = pg_insert(StateRegistration).values(**row_data)
                        stmt = stmt.on_conflict_do_update(
                            index_elements=["entity_id", "state", "registration_type"],
                            set_={
                                k: stmt.excluded[k]
                                for k in row_data
                                if k not in ("entity_id", "state", "registration_type")
                            },
                        )
                        await session.execute(stmt)
                    result.inserted["StateRegistrations"] += 1

                # --- BankAccounts ---
                for row in bank_account_rows:
                    entity_name = row.get("entity_legal_name")
                    entity_id = entity_id_map.get(entity_name) if entity_name else None
                    if entity_id is None and not self._dry_run:
                        result.skipped["BankAccounts"] += 1
                        continue
                    row_data = self._prepare_bank_account(row)
                    if entity_id is not None:
                        row_data["entity_id"] = entity_id
                    if not self._dry_run:
                        existing_bank = (
                            await session.execute(
                                select(BankAccount).where(
                                    BankAccount.entity_id == row_data["entity_id"],
                                    BankAccount.bank_name == row_data["bank_name"],
                                    BankAccount.account_number_last4
                                    == row_data["account_number_last4"],
                                )
                            )
                        ).scalar_one_or_none()
                        if existing_bank:
                            result.skipped["BankAccounts"] += 1
                            continue
                        session.add(BankAccount(**row_data))
                    result.inserted["BankAccounts"] += 1

                # --- TaxFilings ---
                for row in tax_filing_rows:
                    entity_name = row.get("entity_legal_name")
                    entity_id = entity_id_map.get(entity_name) if entity_name else None
                    if entity_id is None and not self._dry_run:
                        result.skipped["TaxFilings"] += 1
                        continue
                    row_data = self._prepare_tax_filing(row)
                    if entity_id is not None:
                        row_data["entity_id"] = entity_id
                    if not self._dry_run:
                        existing_filing = (
                            await session.execute(
                                select(TaxFiling).where(
                                    TaxFiling.entity_id == row_data["entity_id"],
                                    TaxFiling.tax_year == row_data["tax_year"],
                                    TaxFiling.filing_type == row_data["filing_type"],
                                )
                            )
                        ).scalar_one_or_none()
                        if existing_filing:
                            result.skipped["TaxFilings"] += 1
                            continue
                        session.add(TaxFiling(**row_data))
                    result.inserted["TaxFilings"] += 1

                # --- RegisteredAgents ---
                for row in registered_agent_rows:
                    entity_name = row.get("entity_legal_name")
                    entity_id = entity_id_map.get(entity_name) if entity_name else None
                    if entity_id is None and not self._dry_run:
                        result.skipped["RegisteredAgents"] += 1
                        continue
                    row_data = self._prepare_registered_agent(row)
                    if entity_id is not None:
                        row_data["entity_id"] = entity_id
                    if not self._dry_run:
                        stmt = pg_insert(RegisteredAgent).values(**row_data)
                        stmt = stmt.on_conflict_do_update(
                            index_elements=["entity_id", "state", "is_active"],
                            set_={
                                k: stmt.excluded[k]
                                for k in row_data
                                if k not in ("entity_id", "state", "is_active")
                            },
                        )
                        await session.execute(stmt)
                    result.inserted["RegisteredAgents"] += 1

                if not self._dry_run:
                    await session.commit()
                else:
                    await session.rollback()

            except Exception:
                await session.rollback()
                raise

    # ------------------------------------------------------------------
    # Row preparation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _prepare_entity(row: dict[str, Any]) -> dict[str, Any]:
        """Coerce and clean a mapped entity row for DB insertion.

        Args:
            row: Mapped row dict from FieldMapper.

        Returns:
            Dict of column values ready for SQLAlchemy insert.
        """
        fm = FieldMapper("Entities")
        return {
            "legal_name": row.get("legal_name"),
            "dba_names": row.get("dba_names"),
            "ein": row.get("ein"),
            "entity_type": str(row.get("entity_type", "llc")).strip().lower(),
            "formation_state": row.get("formation_state"),
            "formation_date": fm.coerce_date(row.get("formation_date")),
            "fiscal_year_end": row.get("fiscal_year_end"),
            "business_address": row.get("business_address"),
            "business_city": row.get("business_city"),
            "business_state": row.get("business_state"),
            "business_zip": row.get("business_zip"),
            "mailing_address": row.get("mailing_address"),
            "mailing_city": row.get("mailing_city"),
            "mailing_state": row.get("mailing_state"),
            "mailing_zip": row.get("mailing_zip"),
            "accounting_record_id": row.get("accounting_record_id"),
            "purpose": row.get("purpose"),
            "notes": row.get("notes"),
            "is_active": fm.coerce_bool(row.get("is_active"))
            if row.get("is_active") is not None
            else True,
        }

    @staticmethod
    def _prepare_owner(row: dict[str, Any]) -> dict[str, Any]:
        """Coerce and clean a mapped owner row for DB insertion.

        Args:
            row: Mapped row dict from FieldMapper.

        Returns:
            Dict of column values (without entity_id) ready for SQLAlchemy insert.
        """
        fm = FieldMapper("Owners")
        pct_raw = row.get("ownership_percentage")
        try:
            pct = (
                Decimal(str(pct_raw).strip())
                if pct_raw is not None
                else Decimal("0.00")
            )
        except InvalidOperation:
            pct = Decimal("0.00")

        return {
            "owner_name": row.get("owner_name"),
            "ownership_type": str(row.get("ownership_type", "member")).strip().lower(),
            "ownership_percentage": pct,
            "capital_contribution": fm.coerce_decimal(row.get("capital_contribution")),
            "profit_share_percentage": fm.coerce_decimal(
                row.get("profit_share_percentage")
            ),
            "loss_share_percentage": fm.coerce_decimal(
                row.get("loss_share_percentage")
            ),
            "voting_percentage": fm.coerce_decimal(row.get("voting_percentage")),
            "start_date": fm.coerce_date(row.get("start_date")),
            "end_date": fm.coerce_date(row.get("end_date")),
            # ein_or_ssn format (EIN or SSN) is not validated at import time.
            "ein_or_ssn": row.get("ein_or_ssn"),
            "address": row.get("address"),
            "city": row.get("city"),
            "state": row.get("state"),
            "zip_code": row.get("zip_code"),
            "email": row.get("email"),
            "phone": row.get("phone"),
            "notes": row.get("notes"),
            "is_active": fm.coerce_bool(row.get("is_active"))
            if row.get("is_active") is not None
            else True,
        }

    @staticmethod
    def _prepare_state_registration(row: dict[str, Any]) -> dict[str, Any]:
        """Coerce and clean a mapped state registration row for DB insertion.

        Args:
            row: Mapped row dict from FieldMapper.

        Returns:
            Dict of column values (without entity_id) ready for SQLAlchemy insert.
        """
        fm = FieldMapper("StateRegistrations")
        return {
            "state": row.get("state"),
            "registration_type": str(row.get("registration_type", "domestic"))
            .strip()
            .lower(),
            "status": str(row.get("status", "active")).strip().lower(),
            "file_number": row.get("file_number"),
            "registered_name": row.get("registered_name"),
            "registration_date": fm.coerce_date(row.get("registration_date")),
            "effective_date": fm.coerce_date(row.get("effective_date")),
            "expiration_date": fm.coerce_date(row.get("expiration_date")),
            "annual_report_due": fm.coerce_date(row.get("annual_report_due")),
            "last_annual_report": fm.coerce_date(row.get("last_annual_report")),
            "next_renewal_date": fm.coerce_date(row.get("next_renewal_date")),
            "filing_fee": row.get("filing_fee"),
            "annual_fee": row.get("annual_fee"),
            "notes": row.get("notes"),
            "is_good_standing": fm.coerce_bool(row.get("is_good_standing"))
            if row.get("is_good_standing") is not None
            else True,
        }

    @staticmethod
    def _prepare_bank_account(row: dict[str, Any]) -> dict[str, Any]:
        """Coerce and clean a mapped bank account row for DB insertion.

        Args:
            row: Mapped row dict from FieldMapper.

        Returns:
            Dict of column values (without entity_id) ready for SQLAlchemy insert.
        """
        fm = FieldMapper("BankAccounts")
        return {
            "bank_name": row.get("bank_name"),
            "account_name": row.get("account_name"),
            "account_type": str(row.get("account_type", "business_checking"))
            .strip()
            .lower(),
            "account_number_last4": row.get("account_number_last4"),
            "routing_number": row.get("routing_number"),
            "account_nickname": row.get("account_nickname"),
            "opened_date": fm.coerce_date(row.get("opened_date")),
            "closed_date": fm.coerce_date(row.get("closed_date")),
            "primary_contact": row.get("primary_contact"),
            "contact_phone": row.get("contact_phone"),
            "contact_email": row.get("contact_email"),
            "branch_address": row.get("branch_address"),
            "online_banking_url": row.get("online_banking_url"),
            "notes": row.get("notes"),
            "is_primary": fm.coerce_bool(row.get("is_primary"))
            if row.get("is_primary") is not None
            else False,
            "is_active": fm.coerce_bool(row.get("is_active"))
            if row.get("is_active") is not None
            else True,
        }

    @staticmethod
    def _prepare_tax_filing(row: dict[str, Any]) -> dict[str, Any]:
        """Coerce and clean a mapped tax filing row for DB insertion.

        Args:
            row: Mapped row dict from FieldMapper.

        Returns:
            Dict of column values (without entity_id) ready for SQLAlchemy insert.
        """
        fm = FieldMapper("TaxFilings")
        tax_year_raw = row.get("tax_year")
        try:
            tax_year = int(str(tax_year_raw).strip()) if tax_year_raw is not None else 0
        except ValueError:
            tax_year = 0

        return {
            "filing_type": str(row.get("filing_type", "other")).strip().lower(),
            "jurisdiction": row.get("jurisdiction"),
            "tax_year": tax_year,
            "tax_period": row.get("tax_period"),
            "frequency": str(row.get("frequency", "annual")).strip().lower(),
            "due_date": fm.coerce_date(row.get("due_date")),
            "extended_due_date": fm.coerce_date(row.get("extended_due_date")),
            "filed_date": fm.coerce_date(row.get("filed_date")),
            "status": str(row.get("status", "pending")).strip().lower(),
            "form_number": row.get("form_number"),
            "confirmation_number": row.get("confirmation_number"),
            "preparer": row.get("preparer"),
            "amount_due": row.get("amount_due"),
            "amount_paid": row.get("amount_paid"),
            "notes": row.get("notes"),
        }

    @staticmethod
    def _prepare_registered_agent(row: dict[str, Any]) -> dict[str, Any]:
        """Coerce and clean a mapped registered agent row for DB insertion.

        Args:
            row: Mapped row dict from FieldMapper.

        Returns:
            Dict of column values (without entity_id) ready for SQLAlchemy insert.
        """
        fm = FieldMapper("RegisteredAgents")
        return {
            "state": row.get("state"),
            "agent_name": row.get("agent_name"),
            "agent_company": row.get("agent_company"),
            "address": row.get("address"),
            "city": row.get("city"),
            "state_address": row.get("state_address"),
            "zip_code": row.get("zip_code"),
            "phone": row.get("phone"),
            "email": row.get("email"),
            "effective_date": fm.coerce_date(row.get("effective_date")),
            "expiration_date": fm.coerce_date(row.get("expiration_date")),
            "renewal_date": fm.coerce_date(row.get("renewal_date")),
            "annual_cost": row.get("annual_cost"),
            "account_number": row.get("account_number"),
            "notes": row.get("notes"),
            "is_active": fm.coerce_bool(row.get("is_active"))
            if row.get("is_active") is not None
            else True,
        }


# ---------------------------------------------------------------------------
# Reporter
# ---------------------------------------------------------------------------


class Reporter:
    """Formats and outputs validation and reconciliation results.

    Args:
        result: The populated ImportResult from validation and import.
    """

    def __init__(self, result: ImportResult) -> None:
        """Initialise with the import result."""
        self._result = result

    def summary_lines(self) -> list[str]:
        """Build a human-readable summary as a list of text lines.

        Returns:
            List of formatted lines suitable for printing or writing to a file.
        """
        r = self._result
        lines: list[str] = []
        lines.append("=" * 60)
        lines.append("Import Validation Summary")
        lines.append("=" * 60)
        lines.append(
            f"  Errors   : {r.error_count}"
            f"   Warnings : {r.warning_count}"
            f"   Info     : {r.info_count}"
        )
        lines.append("")

        if r.messages:
            lines.append("Validation Messages:")
            for lvl in LEVELS:
                msgs = [m for m in r.messages if m.level == lvl]
                if not msgs:
                    continue
                lines.append(f"  [{lvl}]")
                lines.extend(
                    f"    {m.tab} row {m.row} / {m.field}: {m.message}" for m in msgs
                )
            lines.append("")

        lines.append("Reconciliation:")
        all_tabs = set(r.inserted) | set(r.updated) | set(r.skipped)
        for tab in EXPECTED_TABS:
            if tab not in all_tabs:
                continue
            ins = r.inserted.get(tab, 0)
            upd = r.updated.get(tab, 0)
            skp = r.skipped.get(tab, 0)
            lines.append(f"  {tab:<22}  inserted={ins}  updated={upd}  skipped={skp}")

        lines.append("=" * 60)
        return lines

    def print_summary(self) -> None:
        """Print the summary to stdout."""
        for line in self.summary_lines():
            click.echo(line)

    def write_summary(self, output_path: Path) -> None:
        """Write the summary to a file.

        Args:
            output_path: Destination file path.
        """
        output_path.write_text("\n".join(self.summary_lines()) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------


def _run_validation_and_import(
    workbook_path: Path,
    dry_run: bool,
    do_import: bool,
) -> ImportResult:
    """Orchestrate read, validate, and optionally import pipeline.

    Args:
        workbook_path: Path to the Excel workbook.
        dry_run: If True, skip DB writes.
        do_import: If False, only validate (implies dry_run=True).

    Returns:
        Populated ImportResult.
    """
    result = ImportResult()

    # 1. Read workbook.
    reader = ExcelReader(workbook_path)
    reader.load()

    present_tabs = reader.tabs()
    missing = [t for t in EXPECTED_TABS if t not in present_tabs]
    if missing:
        for tab in missing:
            result.messages.append(
                ValidationMessage(
                    level="WARNING",
                    tab=tab,
                    row=0,
                    field="tab",
                    message=f"Tab '{tab}' not found in workbook; skipping.",
                )
            )

    # 2. Map columns.
    def _map_rows(tab: str) -> list[dict[str, Any]]:
        mapper = FieldMapper(tab)
        return [mapper.map_row(r) for r in reader.rows(tab)]

    entity_rows = _map_rows("Entities")
    owner_rows = _map_rows("Owners")
    state_reg_rows = _map_rows("StateRegistrations")
    bank_account_rows = _map_rows("BankAccounts")
    tax_filing_rows = _map_rows("TaxFilings")
    registered_agent_rows = _map_rows("RegisteredAgents")

    # 3. Validate.
    validator = Validator(result)

    # Entities must be validated first to build the known-names set.
    valid_entity_names: list[str] = []
    for idx, row in enumerate(entity_rows, start=2):  # Row 1 is header.
        if validator.validate_entity_row(row, idx):
            legal_name = row.get("legal_name")
            if legal_name:
                valid_entity_names.append(legal_name)

    known_names = frozenset(valid_entity_names)

    for idx, row in enumerate(owner_rows, start=2):
        validator.validate_owner_row(row, idx, known_names)

    for idx, row in enumerate(state_reg_rows, start=2):
        validator.validate_state_registration_row(row, idx, known_names)

    for idx, row in enumerate(bank_account_rows, start=2):
        validator.validate_bank_account_row(row, idx, known_names)

    for idx, row in enumerate(tax_filing_rows, start=2):
        validator.validate_tax_filing_row(row, idx, known_names)

    for idx, row in enumerate(registered_agent_rows, start=2):
        validator.validate_registered_agent_row(row, idx, known_names)

    # Check ownership percentage sums after all owner rows are processed.
    validator.validate_ownership_sums()

    # 4. Abort import if there are validation errors.
    if result.error_count > 0:
        result.messages.append(
            ValidationMessage(
                level="INFO",
                tab="",
                row=0,
                field="",
                message=f"Import aborted: {result.error_count} validation error(s) found.",
            )
        )
        return result

    # 5. Import (unless validate-only mode).
    if do_import:
        # Filter only valid entity rows for import.
        valid_entity_rows = [
            r for r in entity_rows if r.get("legal_name") in known_names
        ]
        importer = Importer(dry_run=dry_run)
        asyncio.run(
            importer.run(
                entity_rows=valid_entity_rows,
                owner_rows=owner_rows,
                state_reg_rows=state_reg_rows,
                bank_account_rows=bank_account_rows,
                tax_filing_rows=tax_filing_rows,
                registered_agent_rows=registered_agent_rows,
                result=result,
            )
        )
        if dry_run:
            result.messages.append(
                ValidationMessage(
                    level="INFO",
                    tab="",
                    row=0,
                    field="",
                    message="Dry-run mode: no data written to the database.",
                )
            )

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.group()
def cli() -> None:
    """LLC Manager Excel data importer.

    Import LLC entity data from a formatted Excel workbook into the database.
    See docs/development/data-import-format.md for the workbook layout.
    """


@cli.command()
@click.argument("workbook", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Validate and stage data without writing to the database.",
)
@click.option(
    "--report",
    is_flag=True,
    default=False,
    help="Print a validation and reconciliation report after import.",
)
@click.option(
    "--output-file",
    type=click.Path(path_type=Path),
    default=None,
    help="Write the report to this file instead of (or in addition to) stdout.",
)
def import_data(
    workbook: Path,
    dry_run: bool,
    report: bool,
    output_file: Path | None,
) -> None:
    """Import entity data from WORKBOOK into the database.

    WORKBOOK must be an .xlsx file following the format at
    docs/development/data-import-format.md.
    """
    result = _run_validation_and_import(
        workbook_path=workbook,
        dry_run=dry_run,
        do_import=True,
    )

    reporter = Reporter(result)
    if report or dry_run or result.error_count > 0:
        reporter.print_summary()

    if output_file is not None:
        reporter.write_summary(output_file)
        click.echo(f"Report written to {output_file}")

    if result.error_count > 0:
        sys.exit(1)


@cli.command(name="validate-only")
@click.argument("workbook", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output-file",
    type=click.Path(path_type=Path),
    default=None,
    help="Write the validation report to this file.",
)
def validate_only(workbook: Path, output_file: Path | None) -> None:
    """Validate WORKBOOK without importing any data.

    Equivalent to running 'import --dry-run' but never touches the database.
    """
    result = _run_validation_and_import(
        workbook_path=workbook,
        dry_run=True,
        do_import=False,
    )
    reporter = Reporter(result)
    reporter.print_summary()
    if output_file is not None:
        reporter.write_summary(output_file)
        click.echo(f"Report written to {output_file}")
    if result.error_count > 0:
        sys.exit(1)


@cli.command()
@click.argument("workbook", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output-file",
    type=click.Path(path_type=Path),
    default=None,
    help="Write the report to this file.",
)
def report(workbook: Path, output_file: Path | None) -> None:
    """Validate WORKBOOK and print a full report without importing.

    Runs the full validation pipeline and prints errors, warnings,
    and a reconciliation preview. Nothing is written to the database.
    """
    result = _run_validation_and_import(
        workbook_path=workbook,
        dry_run=True,
        do_import=False,
    )
    reporter = Reporter(result)
    reporter.print_summary()
    if output_file is not None:
        reporter.write_summary(output_file)
        click.echo(f"Report written to {output_file}")
    if result.error_count > 0:
        sys.exit(1)


# Make the 'import' command accessible without a subcommand word by registering
# it under the import name and also as the default when called directly.
cli.add_command(import_data, name="import")


if __name__ == "__main__":
    cli()
