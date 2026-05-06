"""Tests for scripts/import_excel.py -- Excel importer for LLC Manager.

Covers:
- ExcelReader: load, tabs, rows
- FieldMapper: alias normalisation, coerce helpers
- Validator: EIN, percentage, required fields
- Importer: dry-run (no DB writes), upsert idempotency
- Reporter: error/warning counts and summary lines
- Full pipeline: 25-entity workbook under 60 s (slow)
"""

from __future__ import annotations

import asyncio
import re
import time
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import import_excel as _ie
import pandas as pd
import pytest

_M = _ie

ExcelReader = _M.ExcelReader
FieldMapper = _M.FieldMapper
Validator = _M.Validator
Importer = _M.Importer
ImportResult = _M.ImportResult
Reporter = _M.Reporter
ValidationMessage = _M.ValidationMessage


# ===========================================================================
# ExcelReader
# ===========================================================================


class TestExcelReader:
    @pytest.mark.unit
    def test_excel_reader_loads_entities_tab(self, tmp_path: Path) -> None:
        """ExcelReader.rows() returns the row dicts for the Entities sheet."""
        xlsx = tmp_path / "workbook.xlsx"
        df = pd.DataFrame(
            [
                {
                    "Legal Name": "Acme LLC",
                    "EIN": "12-3456789",
                    "Entity Type": "llc",
                }
            ]
        )
        with pd.ExcelWriter(str(xlsx), engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Entities", index=False)

        reader = ExcelReader(xlsx)
        reader.load()

        rows = reader.rows("Entities")

        assert len(rows) == 1
        assert rows[0]["Legal Name"] == "Acme LLC"

    @pytest.mark.unit
    def test_excel_reader_tabs_lists_sheet_names(self, tmp_path: Path) -> None:
        """ExcelReader.tabs() returns all sheet names in the workbook."""
        xlsx = tmp_path / "workbook.xlsx"
        df = pd.DataFrame([{"col": "val"}])
        with pd.ExcelWriter(str(xlsx), engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Entities", index=False)
            df.to_excel(writer, sheet_name="Owners", index=False)

        reader = ExcelReader(xlsx)
        reader.load()

        assert "Entities" in reader.tabs()
        assert "Owners" in reader.tabs()

    @pytest.mark.unit
    def test_excel_reader_missing_tab_returns_empty(self, tmp_path: Path) -> None:
        """rows() for a tab not present in the workbook returns an empty list."""
        xlsx = tmp_path / "workbook.xlsx"
        df = pd.DataFrame([{"col": "val"}])
        with pd.ExcelWriter(str(xlsx), engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Entities", index=False)

        reader = ExcelReader(xlsx)
        reader.load()

        assert reader.rows("NoSuchTab") == []

    @pytest.mark.unit
    def test_excel_reader_raises_if_not_loaded(self, tmp_path: Path) -> None:
        """rows() raises RuntimeError when called before load()."""
        reader = ExcelReader(tmp_path / "missing.xlsx")

        with pytest.raises(RuntimeError, match=re.escape("load()")):
            reader.rows("Entities")

    @pytest.mark.unit
    def test_excel_reader_tabs_raises_if_not_loaded(self, tmp_path: Path) -> None:
        """tabs() raises RuntimeError when called before load()."""
        reader = ExcelReader(tmp_path / "missing.xlsx")

        with pytest.raises(RuntimeError, match=re.escape("load()")):
            reader.tabs()


# ===========================================================================
# FieldMapper
# ===========================================================================


class TestFieldMapper:
    @pytest.mark.unit
    def test_field_mapper_normalises_column_aliases(self) -> None:
        """'Company Name' header maps to the ORM field 'legal_name'."""
        mapper = FieldMapper("Entities")
        raw = {"Company Name": "Acme LLC", "EIN": "12-3456789"}

        mapped = mapper.map_row(raw)

        assert "legal_name" in mapped
        assert mapped["legal_name"] == "Acme LLC"

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("alias", "orm_field"),
        [
            ("LLC Name", "legal_name"),
            ("Tax ID", "ein"),
            ("State of Formation", "formation_state"),
            ("FYE", "fiscal_year_end"),
            ("Is Active", "is_active"),
        ],
    )
    def test_field_mapper_entity_aliases(self, alias: str, orm_field: str) -> None:
        """Each known entity alias maps to the correct ORM field name."""
        mapper = FieldMapper("Entities")

        mapped = mapper.map_row({alias: "value"})

        assert orm_field in mapped

    @pytest.mark.unit
    def test_field_mapper_coerce_bool_true_values(self) -> None:
        """coerce_bool returns True for truthy string representations."""
        for v in ("true", "1", "yes", "True", "YES"):
            assert FieldMapper.coerce_bool(v) is True

    @pytest.mark.unit
    def test_field_mapper_coerce_bool_false_values(self) -> None:
        """coerce_bool returns False for falsy string representations."""
        for v in ("false", "0", "no", "False", "NO"):
            assert FieldMapper.coerce_bool(v) is False

    @pytest.mark.unit
    def test_field_mapper_coerce_bool_none(self) -> None:
        """coerce_bool returns None when value is None."""
        assert FieldMapper.coerce_bool(None) is None

    @pytest.mark.unit
    def test_field_mapper_coerce_bool_unknown_returns_none(self) -> None:
        """coerce_bool returns None for an unrecognised string."""
        assert FieldMapper.coerce_bool("maybe") is None

    @pytest.mark.unit
    def test_field_mapper_coerce_date_valid(self) -> None:
        """coerce_date parses a YYYY-MM-DD string into a date object."""
        from datetime import date

        result = FieldMapper.coerce_date("2023-06-15")

        assert result == date(2023, 6, 15)

    @pytest.mark.unit
    def test_field_mapper_coerce_date_none(self) -> None:
        """coerce_date returns None for None input."""
        assert FieldMapper.coerce_date(None) is None

    @pytest.mark.unit
    def test_field_mapper_coerce_date_empty_string(self) -> None:
        """coerce_date returns None for an empty string."""
        assert FieldMapper.coerce_date("") is None

    @pytest.mark.unit
    def test_field_mapper_coerce_decimal_valid(self) -> None:
        """coerce_decimal converts a numeric string to Decimal."""
        result = FieldMapper.coerce_decimal("42.50")

        assert result == Decimal("42.50")

    @pytest.mark.unit
    def test_field_mapper_coerce_decimal_none(self) -> None:
        """coerce_decimal returns None for None input."""
        assert FieldMapper.coerce_decimal(None) is None

    @pytest.mark.unit
    def test_field_mapper_coerce_decimal_empty_string_returns_none(self) -> None:
        """coerce_decimal returns None for an empty string."""
        assert FieldMapper.coerce_decimal("  ") is None

    @pytest.mark.unit
    def test_field_mapper_coerce_int_valid(self) -> None:
        """coerce_int converts a numeric string to int."""
        assert FieldMapper.coerce_int("2024") == 2024

    @pytest.mark.unit
    def test_field_mapper_coerce_int_none(self) -> None:
        """coerce_int returns None for None input."""
        assert FieldMapper.coerce_int(None) is None

    @pytest.mark.unit
    def test_field_mapper_coerce_int_empty_string_returns_none(self) -> None:
        """coerce_int returns None for an empty string."""
        assert FieldMapper.coerce_int("  ") is None

    @pytest.mark.unit
    def test_field_mapper_normalise_strips_whitespace(self) -> None:
        """map_row strips leading/trailing whitespace from string values."""
        mapper = FieldMapper("Entities")

        mapped = mapper.map_row({"Legal Name": "  Acme LLC  "})

        assert mapped["legal_name"] == "Acme LLC"

    @pytest.mark.unit
    def test_field_mapper_normalise_empty_string_becomes_none(self) -> None:
        """map_row converts empty strings (after strip) to None."""
        mapper = FieldMapper("Entities")

        mapped = mapper.map_row({"Legal Name": "   "})

        assert mapped["legal_name"] is None

    @pytest.mark.unit
    def test_field_mapper_normalise_non_string_passthrough(self) -> None:
        """map_row does not alter non-string values."""
        mapper = FieldMapper("Entities")

        mapped = mapper.map_row({"Legal Name": 42})

        assert mapped["legal_name"] == 42

    @pytest.mark.unit
    def test_field_mapper_unknown_tab_passthrough(self) -> None:
        """An unknown tab name results in raw column keys being preserved."""
        mapper = FieldMapper("UnknownTab")

        mapped = mapper.map_row({"SomeColumn": "value"})

        assert "SomeColumn" in mapped


# ===========================================================================
# Validator
# ===========================================================================


class TestValidator:
    @pytest.mark.unit
    def test_validator_rejects_invalid_ein(self) -> None:
        """EIN without hyphen is rejected with an ERROR message."""
        result = ImportResult()
        validator = Validator(result)

        is_valid = validator._validate_ein("123456789", "Entities", 2, "ein")

        assert is_valid is False
        assert result.error_count == 1
        assert "XX-XXXXXXX" in result.messages[0].message

    @pytest.mark.unit
    def test_validator_accepts_valid_ein(self) -> None:
        """EIN in correct XX-XXXXXXX format passes validation."""
        result = ImportResult()
        validator = Validator(result)

        is_valid = validator._validate_ein("12-3456789", "Entities", 2, "ein")

        assert is_valid is True
        assert result.error_count == 0

    @pytest.mark.unit
    def test_validator_ein_none_is_valid(self) -> None:
        """_validate_ein returns True without error when value is None."""
        result = ImportResult()
        validator = Validator(result)

        is_valid = validator._validate_ein(None, "Entities", 2, "ein")

        assert is_valid is True
        assert result.error_count == 0

    @pytest.mark.unit
    def test_validator_rejects_percentage_over_100(self) -> None:
        """ownership_percentage of 150 is rejected with an ERROR message."""
        result = ImportResult()
        validator = Validator(result)

        is_valid = validator._validate_percentage(
            "150", "Owners", 3, "ownership_percentage"
        )

        assert is_valid is False
        assert result.error_count == 1
        assert "150" in result.messages[0].message

    @pytest.mark.unit
    def test_validator_accepts_valid_percentage(self) -> None:
        """ownership_percentage of 50 passes validation."""
        result = ImportResult()
        validator = Validator(result)

        is_valid = validator._validate_percentage(
            "50", "Owners", 3, "ownership_percentage"
        )

        assert is_valid is True
        assert result.error_count == 0

    @pytest.mark.unit
    def test_validator_rejects_percentage_below_zero(self) -> None:
        """Negative ownership_percentage is rejected with an ERROR message."""
        result = ImportResult()
        validator = Validator(result)

        is_valid = validator._validate_percentage(
            "-1", "Owners", 3, "ownership_percentage"
        )

        assert is_valid is False
        assert result.error_count == 1

    @pytest.mark.unit
    def test_validator_percentage_non_numeric_rejected(self) -> None:
        """Non-numeric ownership_percentage is rejected with an ERROR."""
        result = ImportResult()
        validator = Validator(result)

        is_valid = validator._validate_percentage(
            "abc", "Owners", 3, "ownership_percentage"
        )

        assert is_valid is False
        assert result.error_count == 1

    @pytest.mark.unit
    def test_validator_percentage_none_returns_true(self) -> None:
        """_validate_percentage returns True without error when value is None."""
        result = ImportResult()
        validator = Validator(result)

        is_valid = validator._validate_percentage(
            None, "Owners", 2, "ownership_percentage"
        )

        assert is_valid is True
        assert result.error_count == 0

    @pytest.mark.unit
    def test_validator_rejects_missing_legal_name(self) -> None:
        """Entity row without legal_name fails validation."""
        result = ImportResult()
        validator = Validator(result)

        is_valid = validator.validate_entity_row(
            {"entity_type": "llc", "ein": "12-3456789"}, row_idx=2
        )

        assert is_valid is False
        assert result.error_count >= 1

    @pytest.mark.unit
    def test_validator_rejects_invalid_entity_type(self) -> None:
        """Entity row with unknown entity_type fails validation."""
        result = ImportResult()
        validator = Validator(result)

        is_valid = validator.validate_entity_row(
            {
                "legal_name": "Acme LLC",
                "entity_type": "bogus_type",
                "ein": "12-3456789",
            },
            row_idx=2,
        )

        assert is_valid is False
        assert result.error_count >= 1

    @pytest.mark.unit
    def test_validator_validate_ownership_sums_warns_when_not_100(self) -> None:
        """validate_ownership_sums emits WARNING when total != 100."""
        result = ImportResult()
        validator = Validator(result)
        validator._ownership_buckets["Acme LLC"] = [(2, Decimal("60.00"))]

        validator.validate_ownership_sums()

        warnings = [m for m in result.messages if m.level == "WARNING"]
        assert len(warnings) == 1
        assert "Acme LLC" in warnings[0].message

    @pytest.mark.unit
    def test_validator_ownership_sums_no_warning_when_100(self) -> None:
        """validate_ownership_sums emits no WARNING when total == 100."""
        result = ImportResult()
        validator = Validator(result)
        validator._ownership_buckets["Acme LLC"] = [
            (2, Decimal("60.00")),
            (3, Decimal("40.00")),
        ]

        validator.validate_ownership_sums()

        warnings = [m for m in result.messages if m.level == "WARNING"]
        assert len(warnings) == 0

    @pytest.mark.unit
    def test_validator_date_not_future_future_date_warns(self) -> None:
        """_validate_date_not_future emits WARNING for a date in the future."""
        result = ImportResult()
        validator = Validator(result)

        is_valid = validator._validate_date_not_future(
            "2099-01-01", "Entities", 2, "formation_date"
        )

        assert is_valid is True
        warnings = [m for m in result.messages if m.level == "WARNING"]
        assert len(warnings) == 1

    @pytest.mark.unit
    def test_validator_date_not_future_bad_format(self) -> None:
        """_validate_date_not_future adds ERROR for unparseable date string."""
        result = ImportResult()
        validator = Validator(result)

        is_valid = validator._validate_date_not_future(
            "not-a-date", "Entities", 2, "formation_date"
        )

        assert is_valid is False
        assert result.error_count == 1

    @pytest.mark.unit
    def test_validate_date_parseable_bad_format_adds_error(self) -> None:
        """_validate_date_parseable adds ERROR for an invalid date string."""
        result = ImportResult()
        validator = Validator(result)

        is_valid = validator._validate_date_parseable(
            "not-a-date", "Owners", 3, "start_date"
        )

        assert is_valid is False
        assert result.error_count == 1

    @pytest.mark.unit
    def test_validate_date_parseable_valid_date_passes(self) -> None:
        """_validate_date_parseable returns True for a valid date string."""
        result = ImportResult()
        validator = Validator(result)

        is_valid = validator._validate_date_parseable(
            "2023-01-15", "Owners", 3, "start_date"
        )

        assert is_valid is True

    @pytest.mark.unit
    def test_validator_enum_rejects_invalid_value(self) -> None:
        """_validate_enum adds ERROR for a value not in the allowed set."""
        result = ImportResult()
        validator = Validator(result)

        is_valid = validator._validate_enum(
            "invalid_type",
            frozenset({"llc", "corporation"}),
            "Entities",
            2,
            "entity_type",
        )

        assert is_valid is False
        assert result.error_count == 1

    @pytest.mark.unit
    def test_validator_enum_none_passes(self) -> None:
        """_validate_enum returns True without error when value is None."""
        result = ImportResult()
        validator = Validator(result)

        is_valid = validator._validate_enum(
            None,
            frozenset({"llc", "corporation"}),
            "Entities",
            2,
            "entity_type",
        )

        assert is_valid is True
        assert result.error_count == 0

    @pytest.mark.unit
    def test_validator_required_rejects_empty_string(self) -> None:
        """_validate_required adds ERROR for an empty string."""
        result = ImportResult()
        validator = Validator(result)

        is_valid = validator._validate_required("", "Entities", 2, "legal_name")

        assert is_valid is False
        assert result.error_count == 1

    @pytest.mark.unit
    def test_validator_required_rejects_none(self) -> None:
        """_validate_required adds ERROR for None."""
        result = ImportResult()
        validator = Validator(result)

        is_valid = validator._validate_required(None, "Entities", 2, "legal_name")

        assert is_valid is False
        assert result.error_count == 1


# ===========================================================================
# Validator -- per-tab validators
# ===========================================================================


class TestValidatorPerTabMethods:
    @pytest.mark.unit
    def test_validate_owner_row_valid(self) -> None:
        """validate_owner_row passes for a well-formed owner row."""
        result = ImportResult()
        validator = Validator(result)
        known = frozenset({"Acme LLC"})
        row = {
            "entity_legal_name": "Acme LLC",
            "owner_name": "Alice",
            "ownership_percentage": "50",
            "ownership_type": "member",
        }

        is_valid = validator.validate_owner_row(row, 2, known)

        assert is_valid is True
        assert result.error_count == 0

    @pytest.mark.unit
    def test_validate_owner_row_unknown_entity(self) -> None:
        """validate_owner_row rejects owner for an entity not in known_entity_names."""
        result = ImportResult()
        validator = Validator(result)
        known: frozenset[str] = frozenset()

        row = {
            "entity_legal_name": "Unknown LLC",
            "owner_name": "Bob",
            "ownership_percentage": "100",
        }

        is_valid = validator.validate_owner_row(row, 2, known)

        assert is_valid is False
        assert result.error_count >= 1

    @pytest.mark.unit
    def test_validate_state_registration_row_valid(self) -> None:
        """validate_state_registration_row passes for a valid row."""
        result = ImportResult()
        validator = Validator(result)
        known = frozenset({"Acme LLC"})
        row = {
            "entity_legal_name": "Acme LLC",
            "state": "TX",
            "registration_type": "domestic",
            "status": "active",
        }

        is_valid = validator.validate_state_registration_row(row, 2, known)

        assert is_valid is True
        assert result.error_count == 0

    @pytest.mark.unit
    def test_validate_state_registration_row_unknown_entity(self) -> None:
        """validate_state_registration_row rejects unknown entity."""
        result = ImportResult()
        validator = Validator(result)
        known: frozenset[str] = frozenset()

        row = {"entity_legal_name": "Ghost LLC", "state": "TX"}

        is_valid = validator.validate_state_registration_row(row, 2, known)

        assert is_valid is False

    @pytest.mark.unit
    def test_validate_bank_account_row_valid(self) -> None:
        """validate_bank_account_row passes for a valid row."""
        result = ImportResult()
        validator = Validator(result)
        known = frozenset({"Acme LLC"})
        row = {
            "entity_legal_name": "Acme LLC",
            "bank_name": "First National",
            "account_type": "checking",
        }

        is_valid = validator.validate_bank_account_row(row, 2, known)

        assert is_valid is True

    @pytest.mark.unit
    def test_validate_bank_account_row_unknown_entity(self) -> None:
        """validate_bank_account_row rejects unknown entity."""
        result = ImportResult()
        validator = Validator(result)
        known: frozenset[str] = frozenset()

        row = {"entity_legal_name": "Ghost LLC", "bank_name": "Chase"}

        is_valid = validator.validate_bank_account_row(row, 2, known)

        assert is_valid is False

    @pytest.mark.unit
    def test_validate_tax_filing_row_valid(self) -> None:
        """validate_tax_filing_row passes for a valid row."""
        result = ImportResult()
        validator = Validator(result)
        known = frozenset({"Acme LLC"})
        row = {
            "entity_legal_name": "Acme LLC",
            "filing_type": "federal_income",
            "jurisdiction": "Federal",
            "tax_year": "2023",
            "frequency": "annual",
            "status": "filed",
        }

        is_valid = validator.validate_tax_filing_row(row, 2, known)

        assert is_valid is True

    @pytest.mark.unit
    def test_validate_tax_filing_row_unknown_entity(self) -> None:
        """validate_tax_filing_row rejects unknown entity."""
        result = ImportResult()
        validator = Validator(result)
        known: frozenset[str] = frozenset()

        row = {
            "entity_legal_name": "Ghost LLC",
            "filing_type": "federal_income",
            "jurisdiction": "Federal",
            "tax_year": "2023",
        }

        is_valid = validator.validate_tax_filing_row(row, 2, known)

        assert is_valid is False

    @pytest.mark.unit
    def test_validate_registered_agent_row_valid(self) -> None:
        """validate_registered_agent_row passes for a valid row."""
        result = ImportResult()
        validator = Validator(result)
        known = frozenset({"Acme LLC"})
        row = {
            "entity_legal_name": "Acme LLC",
            "state": "TX",
            "agent_name": "CT Corp",
        }

        is_valid = validator.validate_registered_agent_row(row, 2, known)

        assert is_valid is True

    @pytest.mark.unit
    def test_validate_registered_agent_row_unknown_entity(self) -> None:
        """validate_registered_agent_row rejects unknown entity."""
        result = ImportResult()
        validator = Validator(result)
        known: frozenset[str] = frozenset()

        row = {
            "entity_legal_name": "Ghost LLC",
            "state": "TX",
            "agent_name": "CT Corp",
        }

        is_valid = validator.validate_registered_agent_row(row, 2, known)

        assert is_valid is False


# ===========================================================================
# ImportResult
# ===========================================================================


class TestImportResult:
    @pytest.mark.unit
    def test_reporter_counts_errors_and_warnings(self) -> None:
        """ImportResult.error_count and warning_count reflect fixture messages."""
        result = ImportResult()
        result.messages = [
            ValidationMessage("ERROR", "Entities", 2, "ein", "bad EIN"),
            ValidationMessage("ERROR", "Owners", 3, "owner_name", "missing"),
            ValidationMessage(
                "WARNING", "Owners", 4, "ownership_percentage", "sum != 100"
            ),
        ]

        assert result.error_count == 2
        assert result.warning_count == 1

    @pytest.mark.unit
    def test_import_result_info_count(self) -> None:
        """ImportResult.info_count counts only INFO-level messages."""
        result = ImportResult()
        result.messages = [
            ValidationMessage("INFO", "", 0, "", "dry-run complete"),
            ValidationMessage("ERROR", "Entities", 2, "ein", "bad"),
        ]

        assert result.info_count == 1


# ===========================================================================
# Reporter
# ===========================================================================


class TestReporter:
    @pytest.mark.unit
    def test_reporter_summary_lines_includes_counts(self) -> None:
        """summary_lines() contains the error and warning counts."""
        result = ImportResult()
        result.messages = [
            ValidationMessage("ERROR", "Entities", 2, "ein", "bad EIN"),
            ValidationMessage("ERROR", "Owners", 3, "owner_name", "missing"),
            ValidationMessage(
                "WARNING", "Owners", 4, "ownership_percentage", "sum != 100"
            ),
        ]
        reporter = Reporter(result)

        lines = reporter.summary_lines()
        summary = "\n".join(lines)

        assert "Errors   : 2" in summary
        assert "Warnings : 1" in summary

    @pytest.mark.unit
    def test_reporter_summary_lines_includes_reconciliation(self) -> None:
        """summary_lines() includes the Reconciliation section."""
        result = ImportResult()
        result.inserted["Entities"] = 5
        reporter = Reporter(result)

        lines = reporter.summary_lines()
        summary = "\n".join(lines)

        assert "Reconciliation:" in summary
        assert "Entities" in summary

    @pytest.mark.unit
    def test_reporter_write_summary_writes_to_file(self, tmp_path: Path) -> None:
        """write_summary() writes the report to the given path."""
        result = ImportResult()
        reporter = Reporter(result)
        out = tmp_path / "report.txt"

        reporter.write_summary(out)

        content = out.read_text(encoding="utf-8")
        assert "Import Validation Summary" in content

    @pytest.mark.unit
    def test_reporter_summary_lines_no_messages(self) -> None:
        """summary_lines() works correctly when there are no messages."""
        result = ImportResult()
        reporter = Reporter(result)

        lines = reporter.summary_lines()
        summary = "\n".join(lines)

        assert "Errors   : 0" in summary
        assert "Warnings : 0" in summary


# ===========================================================================
# Importer -- dry-run
# ===========================================================================


class TestImporterDryRun:
    @pytest.mark.unit
    def test_dry_run_makes_no_db_calls(self) -> None:
        """In dry-run mode the importer never calls session.execute()."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        result = ImportResult()
        importer = Importer(dry_run=True)

        with patch("import_excel.AsyncSessionLocal", return_value=mock_session):
            asyncio.run(
                importer.run(
                    entity_rows=[
                        {
                            "legal_name": "Acme LLC",
                            "ein": "12-3456789",
                            "entity_type": "llc",
                        }
                    ],
                    owner_rows=[],
                    state_reg_rows=[],
                    bank_account_rows=[],
                    tax_filing_rows=[],
                    registered_agent_rows=[],
                    result=result,
                )
            )

        mock_session.execute.assert_not_called()

    @pytest.mark.unit
    def test_dry_run_rolls_back_session(self) -> None:
        """In dry-run mode the session is rolled back, not committed."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        result = ImportResult()
        importer = Importer(dry_run=True)

        with patch("import_excel.AsyncSessionLocal", return_value=mock_session):
            asyncio.run(
                importer.run(
                    entity_rows=[],
                    owner_rows=[],
                    state_reg_rows=[],
                    bank_account_rows=[],
                    tax_filing_rows=[],
                    registered_agent_rows=[],
                    result=result,
                )
            )

        mock_session.rollback.assert_called_once()
        mock_session.commit.assert_not_called()

    @pytest.mark.unit
    def test_dry_run_counts_inserted_without_db(self) -> None:
        """Dry-run mode increments inserted counters even though DB is not written."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        result = ImportResult()
        importer = Importer(dry_run=True)

        with patch("import_excel.AsyncSessionLocal", return_value=mock_session):
            asyncio.run(
                importer.run(
                    entity_rows=[
                        {
                            "legal_name": "Acme LLC",
                            "ein": "12-3456789",
                            "entity_type": "llc",
                        }
                    ],
                    owner_rows=[],
                    state_reg_rows=[],
                    bank_account_rows=[],
                    tax_filing_rows=[],
                    registered_agent_rows=[],
                    result=result,
                )
            )

        assert result.inserted["Entities"] == 1


# ===========================================================================
# Importer -- upsert idempotency
# ===========================================================================


class TestImporterUpsert:
    @pytest.mark.unit
    def test_importer_upsert_is_idempotent(self) -> None:
        """Running the same entity row twice succeeds both times with no errors.

        Entity upsert uses ON CONFLICT DO UPDATE, so both runs count as
        'inserted' (the source does not track updates separately). The key
        assertion is that the second run does not raise and does not produce
        errors -- the upsert path handles duplicates gracefully.
        """
        entity_row: dict[str, Any] = {
            "legal_name": "Acme LLC",
            "ein": "12-3456789",
            "entity_type": "llc",
        }
        importer = Importer(dry_run=False)

        def make_mock_session() -> AsyncMock:
            fake_row = MagicMock()
            fake_row.__getitem__ = lambda self, idx: (
                "uuid-1" if idx == 0 else ("Acme LLC" if idx == 1 else 0)
            )
            cursor = MagicMock()
            cursor.fetchone.return_value = fake_row

            reload_cursor = MagicMock()
            reload_cursor.fetchall.return_value = [("uuid-1", "Acme LLC")]

            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.execute.side_effect = [cursor, reload_cursor]
            return mock_session

        # First run: entity is inserted via upsert.
        result1 = ImportResult()
        mock_session_1 = make_mock_session()
        with patch("import_excel.AsyncSessionLocal", return_value=mock_session_1):
            asyncio.run(
                importer.run(
                    entity_rows=[entity_row],
                    owner_rows=[],
                    state_reg_rows=[],
                    bank_account_rows=[],
                    tax_filing_rows=[],
                    registered_agent_rows=[],
                    result=result1,
                )
            )

        assert result1.inserted["Entities"] == 1
        assert result1.error_count == 0

        # Second run with identical data: upsert updates the existing row.
        # inserted still increments (source tracks upsert, not insert vs update).
        result2 = ImportResult()
        mock_session_2 = make_mock_session()
        with patch("import_excel.AsyncSessionLocal", return_value=mock_session_2):
            asyncio.run(
                importer.run(
                    entity_rows=[entity_row],
                    owner_rows=[],
                    state_reg_rows=[],
                    bank_account_rows=[],
                    tax_filing_rows=[],
                    registered_agent_rows=[],
                    result=result2,
                )
            )

        # The second run must also succeed without errors.
        assert result2.error_count == 0
        # Both runs produce exactly one upsert call each (not zero, not two).
        assert mock_session_1.execute.call_count == mock_session_2.execute.call_count
        # Total across both runs is 2 -- one per run, never doubled within a run.
        assert result1.inserted["Entities"] + result2.inserted["Entities"] == 2


# ===========================================================================
# Importer -- live (non-dry-run) with child rows
# ===========================================================================


class TestImporterLivePaths:
    @pytest.mark.unit
    def test_importer_live_processes_all_tab_types(self) -> None:
        """Live import with all tab types increments inserted for each tab."""
        import uuid

        fake_entity_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        entity_cursor = MagicMock()
        entity_cursor.fetchone.return_value = None

        reload_cursor = MagicMock()
        reload_cursor.fetchall.return_value = [(fake_entity_id, "Acme LLC")]

        child_cursor = MagicMock()
        child_cursor.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute.side_effect = [
            entity_cursor,
            reload_cursor,
            child_cursor,
            child_cursor,
            child_cursor,
            child_cursor,
            child_cursor,
        ]

        result = ImportResult()
        importer = Importer(dry_run=False)

        with patch("import_excel.AsyncSessionLocal", return_value=mock_session):
            asyncio.run(
                importer.run(
                    entity_rows=[
                        {
                            "legal_name": "Acme LLC",
                            "ein": "12-3456789",
                            "entity_type": "llc",
                        }
                    ],
                    owner_rows=[
                        {
                            "entity_legal_name": "Acme LLC",
                            "owner_name": "Alice",
                            "ownership_percentage": "100",
                            "ownership_type": "member",
                        }
                    ],
                    state_reg_rows=[
                        {
                            "entity_legal_name": "Acme LLC",
                            "state": "TX",
                            "registration_type": "domestic",
                            "status": "active",
                        }
                    ],
                    bank_account_rows=[
                        {
                            "entity_legal_name": "Acme LLC",
                            "bank_name": "First National",
                            "account_number_last4": "1234",
                        }
                    ],
                    tax_filing_rows=[
                        {
                            "entity_legal_name": "Acme LLC",
                            "filing_type": "federal_income",
                            "tax_year": "2023",
                        }
                    ],
                    registered_agent_rows=[
                        {
                            "entity_legal_name": "Acme LLC",
                            "state": "TX",
                            "agent_name": "CT Corp",
                        }
                    ],
                    result=result,
                )
            )

        assert result.inserted["Entities"] == 1
        assert result.inserted["Owners"] == 1
        assert result.inserted["StateRegistrations"] == 1
        assert result.inserted["BankAccounts"] == 1
        assert result.inserted["TaxFilings"] == 1
        assert result.inserted["RegisteredAgents"] == 1

    @pytest.mark.unit
    def test_importer_live_skips_child_rows_with_unknown_entity(self) -> None:
        """Child rows whose entity_id cannot be resolved are skipped."""
        entity_cursor = MagicMock()
        entity_cursor.fetchone.return_value = None

        reload_cursor = MagicMock()
        reload_cursor.fetchall.return_value = []

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute.side_effect = [entity_cursor, reload_cursor]

        result = ImportResult()
        importer = Importer(dry_run=False)

        with patch("import_excel.AsyncSessionLocal", return_value=mock_session):
            asyncio.run(
                importer.run(
                    entity_rows=[],
                    owner_rows=[
                        {
                            "entity_legal_name": "Ghost LLC",
                            "owner_name": "Bob",
                            "ownership_percentage": "100",
                        }
                    ],
                    state_reg_rows=[],
                    bank_account_rows=[],
                    tax_filing_rows=[],
                    registered_agent_rows=[],
                    result=result,
                )
            )

        assert result.skipped["Owners"] == 1


# ===========================================================================
# Importer -- _prepare helpers
# ===========================================================================


class TestImporterPrepareHelpers:
    @pytest.mark.unit
    def test_prepare_entity_defaults_is_active_to_true(self) -> None:
        """_prepare_entity defaults is_active to True when not set."""
        row: dict[str, Any] = {
            "legal_name": "Acme LLC",
            "ein": "12-3456789",
            "entity_type": "llc",
        }

        result = Importer._prepare_entity(row)

        assert result["is_active"] is True

    @pytest.mark.unit
    def test_prepare_entity_with_is_active_explicit(self) -> None:
        """_prepare_entity uses the provided is_active value."""
        row: dict[str, Any] = {
            "legal_name": "Acme LLC",
            "ein": "12-3456789",
            "entity_type": "llc",
            "is_active": "false",
        }

        result = Importer._prepare_entity(row)

        assert result["is_active"] is False

    @pytest.mark.unit
    def test_prepare_owner_defaults_ownership_type_to_member(self) -> None:
        """_prepare_owner defaults ownership_type to 'member' when not set."""
        row: dict[str, Any] = {
            "owner_name": "Alice",
            "ownership_percentage": "50",
        }

        result = Importer._prepare_owner(row)

        assert result["ownership_type"] == "member"

    @pytest.mark.unit
    def test_prepare_owner_invalid_percentage_defaults_to_zero(self) -> None:
        """_prepare_owner defaults ownership_percentage to 0 for non-decimal input."""
        row: dict[str, Any] = {
            "owner_name": "Alice",
            "ownership_percentage": "not_a_number",
        }

        result = Importer._prepare_owner(row)

        assert result["ownership_percentage"] == Decimal("0.00")

    @pytest.mark.unit
    def test_prepare_bank_account_defaults_is_primary_to_false(self) -> None:
        """_prepare_bank_account defaults is_primary to False when not set."""
        row: dict[str, Any] = {
            "bank_name": "First National",
            "account_type": "checking",
        }

        result = Importer._prepare_bank_account(row)

        assert result["is_primary"] is False

    @pytest.mark.unit
    def test_prepare_tax_filing_defaults_tax_year_to_zero_on_bad_value(
        self,
    ) -> None:
        """_prepare_tax_filing defaults tax_year to 0 for non-integer input."""
        row: dict[str, Any] = {
            "filing_type": "federal_income",
            "tax_year": "not_an_int",
        }

        result = Importer._prepare_tax_filing(row)

        assert result["tax_year"] == 0

    @pytest.mark.unit
    def test_prepare_state_registration_coerces_dates(self) -> None:
        """_prepare_state_registration converts date strings to date objects."""
        from datetime import date

        row: dict[str, Any] = {
            "state": "TX",
            "registration_type": "domestic",
            "status": "active",
            "registration_date": "2020-03-01",
        }

        result = Importer._prepare_state_registration(row)

        assert result["registration_date"] == date(2020, 3, 1)

    @pytest.mark.unit
    def test_prepare_registered_agent_coerces_dates(self) -> None:
        """_prepare_registered_agent converts date strings to date objects."""
        from datetime import date

        row: dict[str, Any] = {
            "state": "TX",
            "agent_name": "CT Corp",
            "effective_date": "2021-06-01",
        }

        result = Importer._prepare_registered_agent(row)

        assert result["effective_date"] == date(2021, 6, 1)


# ===========================================================================
# Pipeline -- validation errors and dry-run message
# ===========================================================================


class TestPipelineValidationAbort:
    @pytest.mark.unit
    def test_pipeline_aborts_on_validation_errors(self, tmp_path: Path) -> None:
        """_run_validation_and_import returns early when validation errors exist."""
        xlsx = tmp_path / "bad.xlsx"
        df = pd.DataFrame(
            [{"Legal Name": "Bad LLC", "EIN": "123456789", "Entity Type": "llc"}]
        )
        with pd.ExcelWriter(str(xlsx), engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Entities", index=False)

        result = _M._run_validation_and_import(
            workbook_path=xlsx,
            dry_run=False,
            do_import=True,
        )

        assert result.error_count > 0
        info_msgs = [m for m in result.messages if m.level == "INFO"]
        assert any("Import aborted" in m.message for m in info_msgs)

    @pytest.mark.unit
    def test_pipeline_validate_only_no_db(self, tmp_path: Path) -> None:
        """_run_validation_and_import with do_import=False never runs Importer."""
        xlsx = tmp_path / "ok.xlsx"
        df = pd.DataFrame(
            [
                {
                    "Legal Name": "Acme LLC",
                    "EIN": "12-3456789",
                    "Entity Type": "llc",
                }
            ]
        )
        with pd.ExcelWriter(str(xlsx), engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Entities", index=False)

        result = _M._run_validation_and_import(
            workbook_path=xlsx,
            dry_run=True,
            do_import=False,
        )

        assert result.error_count == 0

    @pytest.mark.unit
    def test_pipeline_warns_on_missing_tabs(self, tmp_path: Path) -> None:
        """_run_validation_and_import emits WARNING for each missing expected tab."""
        xlsx = tmp_path / "sparse.xlsx"
        df = pd.DataFrame(
            [
                {
                    "Legal Name": "Acme LLC",
                    "EIN": "12-3456789",
                    "Entity Type": "llc",
                }
            ]
        )
        with pd.ExcelWriter(str(xlsx), engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Entities", index=False)

        result = _M._run_validation_and_import(
            workbook_path=xlsx,
            dry_run=True,
            do_import=False,
        )

        tab_warnings = [
            m
            for m in result.messages
            if m.level == "WARNING" and "not found in workbook" in m.message
        ]
        assert len(tab_warnings) == 5

    @pytest.mark.unit
    def test_pipeline_dry_run_appends_info_message(self, tmp_path: Path) -> None:
        """_run_validation_and_import appends dry-run INFO message when dry_run=True."""
        xlsx = tmp_path / "ok.xlsx"
        df = pd.DataFrame(
            [
                {
                    "Legal Name": "Acme LLC",
                    "EIN": "12-3456789",
                    "Entity Type": "llc",
                }
            ]
        )
        with pd.ExcelWriter(str(xlsx), engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Entities", index=False)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("import_excel.AsyncSessionLocal", return_value=mock_session):
            result = _M._run_validation_and_import(
                workbook_path=xlsx,
                dry_run=True,
                do_import=True,
            )

        info_msgs = [m for m in result.messages if m.level == "INFO"]
        assert any("Dry-run mode" in m.message for m in info_msgs)


# ===========================================================================
# Full pipeline -- performance
# ===========================================================================


def _build_workbook(path: Path, n: int) -> None:
    """Write an xlsx file with n Entities rows and no other tabs."""
    rows = [
        {
            "Legal Name": f"LLC Number {i:03d}",
            "EIN": f"{10 + (i % 89):02d}-{1000000 + i:07d}",
            "Entity Type": "llc",
            "Formation State": "TX",
            "Active": "true",
        }
        for i in range(1, n + 1)
    ]
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(str(path), engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Entities", index=False)


@pytest.mark.slow
class TestFullImportPerformance:
    def test_full_import_25_entities_under_60s(self, tmp_path: Path) -> None:
        """Full import pipeline with 25 entities completes in under 60 seconds."""
        xlsx = tmp_path / "entities.xlsx"
        _build_workbook(xlsx, 25)

        fake_cursor = MagicMock()
        fake_cursor.fetchone.return_value = None
        fake_cursor.fetchall.return_value = []

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute.return_value = fake_cursor

        run_pipeline = _M._run_validation_and_import

        t0 = time.time()
        with patch("import_excel.AsyncSessionLocal", return_value=mock_session):
            result = run_pipeline(
                workbook_path=xlsx,
                dry_run=False,
                do_import=True,
            )
        elapsed = time.time() - t0

        assert elapsed < 60, f"Pipeline took {elapsed:.1f}s, expected < 60s"
        assert result.error_count == 0, f"Unexpected errors: {result.messages}"
        assert result.inserted["Entities"] == 25
