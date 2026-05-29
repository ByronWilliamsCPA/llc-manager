---
title: "Phase 0.5 Implementation Plan: Excel Data Import"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Executable task plan for Phase 0.5 -- Excel-to-PostgreSQL migration tooling for LLC Manager."
tags:
  - planning
  - project_management
component: Context
source: "Phase 0.5 gate review 2026-05-05"
---

> **Phase**: 0.5 -- Data Import (CRITICAL)
> **Branch**: `feat/data-import`
> **Base**: `main` (post Phase 0 merge)
> **Acceptance criteria**: `docs/planning/PROJECT-PLAN.md` lines 170-176

---

## Objective

Build a standalone import script that reads an existing Excel spreadsheet of LLC records and
upserts them into PostgreSQL using the ORM models already established in Phase 0. This unblocks
adoption: manual entry of ~1,250 records is the stated adoption risk.

---

## Context

### Models that the import must handle

| Model | Key fields |
|---|---|
| `Entity` | `legal_name`, `ein` (XX-XXXXXXX), `entity_type`, `formation_state`, `formation_date`, `fiscal_year_end`, addresses, `is_active` |
| `Owner` | `owner_name`, `ownership_type`, `ownership_percentage`, `ein_or_ssn`, `start_date`, `end_date` |
| `StateRegistration` | FK to Entity; state, reg date, status |
| `BankAccount` | FK to Entity; institution, account type |
| `TaxFiling` | FK to Entity; tax year, filing type, due date, status |
| `RegisteredAgent` | FK to Entity; agent name, address, state |

### Import script requirements (from PROJECT-PLAN.md)

- Uses `pandas` + `openpyxl` for Excel parsing
- Maps spreadsheet columns to Pydantic models before DB insert
- Validates data before insert (EIN format, dates, percentages)
- Generates validation report with errors/warnings
- Supports `--dry-run` (shows what would happen, no DB writes)
- Idempotent upserts (safe to re-run on same file)

---

## Task List

### Task 1: Add dependencies and pyproject.toml extras

**Deliverable**: `pyproject.toml` updated, `uv.lock` regenerated

- Add `pandas>=2.2` and `openpyxl>=3.1` to the `import` extras group in `[project.optional-dependencies]`
- Add `click>=8.1` (CLI argument parsing, already used in seed.py pattern)
- Run `uv sync --all-extras` to lock
- Run `uv run basedpyright src/` and `uv run ruff check .` to confirm no regressions

**Acceptance**: `uv run python -c "import pandas, openpyxl"` exits 0

---

### Task 2: CSV/Excel format specification

**Deliverable**: `docs/development/data-import-format.md`

Document the canonical spreadsheet layout the import script expects. One tab per entity type:

- **Entities** tab: columns mapping to `Entity` fields (legal_name, ein, entity_type, etc.)
- **Owners** tab: columns mapping to `Owner` fields; `entity_legal_name` FK lookup column
- **StateRegistrations** tab: FK lookup + state-specific fields
- **BankAccounts** tab: FK lookup + account fields
- **TaxFilings** tab: FK lookup + filing fields
- **RegisteredAgents** tab: FK lookup + agent fields

Include: column name, required/optional, validation rule, example value.

---

### Task 3: Implement `scripts/import_excel.py`

**Deliverable**: `scripts/import_excel.py`

Structure:

```python
# Entry point: click CLI
# Commands: import (default), validate-only (--dry-run), report

# Modules within the script:
# - ExcelReader: reads each tab via pandas
# - FieldMapper: maps column names -> ORM field names (handles aliases/variants)
# - Validator: validates EIN format, date ranges, percentage bounds, required fields
# - Importer: async SQLAlchemy upsert (conflict on legal_name + ein for Entity)
# - Reporter: prints/writes validation + reconciliation results
```

Implementation order within the file:

1. `ExcelReader` -- load workbook, iterate tabs, return `list[dict]` per tab
2. `FieldMapper` -- column alias map (e.g. "Company Name" -> "legal_name"), normalise types
3. `Validator` -- per-field rules:
   - EIN: `re.fullmatch(r"\d{2}-\d{7}", value)` (XX-XXXXXXX)
   - Dates: parseable, not in the future for formation date
   - Percentages: 0.0-100.0, sum of ownership for an entity = 100%
4. `Importer` -- async context, uses `get_async_session()`, upsert via `ON CONFLICT DO UPDATE`
5. `Reporter` -- validation summary table (errors/warnings/info), reconciliation row counts
6. CLI entrypoint -- `click` group with flags: `--dry-run`, `--report`, `--output-file`

**Acceptance**: `uv run python scripts/import_excel.py --help` exits 0

---

### Task 4: Add tests

**Deliverable**: `tests/unit/test_import_excel.py`

Test cases (use `pytest` + `unittest.mock` -- no live DB required for unit tests):

1. `test_excel_reader_loads_entities_tab` -- mock workbook, assert rows returned
2. `test_field_mapper_normalises_column_aliases` -- "Company Name" maps to `legal_name`
3. `test_validator_rejects_invalid_ein` -- "123456789" raises `ValidationError`
4. `test_validator_accepts_valid_ein` -- "12-3456789" passes
5. `test_validator_rejects_percentage_over_100` -- `ownership_percentage=150` raises
6. `test_dry_run_makes_no_db_calls` -- mock session, assert `session.execute` never called
7. `test_reporter_counts_errors_and_warnings` -- fixture with 2 errors, 1 warning
8. `test_importer_upsert_is_idempotent` -- insert same row twice, assert DB row count stays at 1
9. `test_full_import_25_entities_under_60s` -- `@pytest.mark.slow` integration test; fixture builds 25-entity workbook, runs full import against in-memory SQLite or test DB, asserts `elapsed < 60`

Coverage target for `scripts/import_excel.py`: 80% line minimum.

---

### Task 5: Create import runbook

**Deliverable**: `docs/development/data-import-guide.md`

Sections:

1. Prerequisites (db running, migrations applied, `.env` configured)
2. Preparing the Excel file (format spec reference, tab names, required columns)
3. Dry run (verify before touching DB)
4. Full import with report
5. Re-running after corrections (idempotency guarantee)
6. Troubleshooting (EIN errors, missing FK, duplicate detection)

---

## Definition of Done

All acceptance criteria from PROJECT-PLAN.md lines 170-176 met:

- [ ] `pandas`/`openpyxl` in `import` extras, lockfile updated
- [ ] `scripts/import_excel.py` exists, passes ruff + basedpyright + bandit
- [ ] `--dry-run` flag produces output without writing to DB
- [ ] `--report` flag produces reconciliation summary
- [ ] Tests pass at >= 80% line coverage for the script
- [ ] `test_importer_upsert_is_idempotent` passes (AC7)
- [ ] `test_full_import_25_entities_under_60s` passes with `pytest -m slow` (AC6)
- [ ] `docs/development/data-import-format.md` documents the spreadsheet schema
- [ ] `docs/development/data-import-guide.md` runbook complete with frontmatter
- [ ] `pre-commit run --all-files` passes
- [ ] All 131+ existing tests continue to pass

---

## Execution order

```text
Task 1 (deps)  --> Task 3 (script) --> Task 4 (tests)
Task 2 (spec)  -->                 --> Task 5 (runbook)
```

Tasks 1 and 2 are independent and can run in parallel. Task 3 depends on both.
Tasks 4 and 5 depend on Task 3 and can run in parallel with each other.

> Note: The three `#VERIFY (pending)` RAD markers in `correlation.py`, `security.py`, and
> `db/session.py` are out of scope for Phase 0.5. They will be resolved as a standalone
> chore commit before the Phase 1 gate.
