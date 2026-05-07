---
title: "Data Import Guide"
schema_type: common
status: published
owner: core-maintainer
purpose: "Step-by-step guide for importing LLC records from Excel into the database using the import_excel.py script."
tags:
  - development
  - guide
---

The `scripts/import_excel.py` script bulk-imports LLC entity data from a formatted Excel workbook
into the PostgreSQL database. It validates every row before writing, supports a dry-run mode to
catch errors before touching the database, and uses idempotent upserts so the script can be
re-run safely after corrections.

See [Data Import Format Specification](data-import-format.md) for the complete column reference.

## Prerequisites

The following must be in place before running the script.

### 1. Start the database

```bash
docker-compose up -d db
```

Verify the container is healthy:

```bash
docker-compose ps db
```

The `State` column must show `running` (or `healthy` if a healthcheck is configured).

### 2. Apply migrations

```bash
uv run alembic upgrade head
```

All migrations must succeed before the script can resolve foreign keys. If you see errors,
check that `LLC_MANAGER_DATABASE_*` environment variables point to the running container.

### 3. Configure the environment

Copy `.env.example` to `.env` (if not already done) and set the database credentials:

```bash
LLC_MANAGER_DATABASE_HOST=localhost
LLC_MANAGER_DATABASE_PORT=5432
LLC_MANAGER_DATABASE_USER=llc_manager
LLC_MANAGER_DATABASE_PASSWORD=<your password>
LLC_MANAGER_DATABASE_NAME=llc_manager
```

The script reads these variables through the application's Pydantic Settings layer; they must
be present at runtime.

### 4. Install dependencies

```bash
uv sync --all-extras
```

The script requires `pandas`, `openpyxl`, and `click`, which are all included in the project's
dependency set.

## Preparing the Excel File

The workbook must be an `.xlsx` file. Older `.xls` format is not supported. The sheet names are
case-sensitive and must match exactly.

### Required tab names

| Tab name | Content |
|---|---|
| `Entities` | Root entity records (LLCs, corporations, etc.) |
| `Owners` | Ownership stakes linked to entities |
| `StateRegistrations` | State registration records per entity |
| `BankAccounts` | Bank account records per entity |
| `TaxFilings` | Tax filing records per entity |
| `RegisteredAgents` | Registered agent records per entity |

Missing tabs produce a `WARNING` and are skipped; they do not abort the import. The `Entities`
tab must be present and have valid rows because all other tabs resolve their entity references
from it.

### Column naming

The script accepts common header aliases. For example, `Company Name`, `LLC Name`, and
`Legal Name` all map to the `legal_name` field. The canonical column names and all accepted
aliases are listed in [Data Import Format Specification](data-import-format.md).

### Formatting rules

- All dates: `YYYY-MM-DD` (e.g., `2024-03-15`).
- Booleans: `TRUE`, `FALSE`, `1`, or `0` (case-insensitive).
- Percentages: decimal notation without a percent sign (e.g., `60.00` for 60%).
- EINs: `XX-XXXXXXX` format, exactly two digits, a hyphen, then seven digits (e.g., `12-3456789`).
- Empty cells are treated as `NULL` for optional fields.
- Rows where every cell is empty are silently skipped.

## Dry Run

Run a dry run to validate the workbook without writing anything to the database. This is the
recommended first step for any new or modified workbook.

```bash
uv run python scripts/import_excel.py import --dry-run path/to/data.xlsx
```

A validation and reconciliation report is printed automatically in dry-run mode. The output
shows errors, warnings, and a preview of how many rows would be inserted, updated, or skipped
per tab.

Example output:

```text
============================================================
Import Validation Summary
============================================================
  Errors   : 0   Warnings : 1   Info     : 1

Validation Messages:
  [WARNING]
    Owners row 3 / ownership_percentage: Ownership percentages for 'Acme Holdings LLC' sum to 90.00, expected 100.00
  [INFO]
    Dry-run mode: no data written to the database.

Reconciliation:
  Entities               inserted=2  updated=0  skipped=0
  Owners                 inserted=3  updated=0  skipped=0
  StateRegistrations     inserted=1  updated=0  skipped=0
  BankAccounts           inserted=2  updated=0  skipped=0
  TaxFilings             inserted=4  updated=0  skipped=0
  RegisteredAgents       inserted=1  updated=0  skipped=0
============================================================
```

The script exits with code `1` if any `ERROR`-level messages are present. Fix all errors before
proceeding to a full import.

### Validate only (no import pipeline)

If you only want validation output without engaging the import pipeline at all, use the
`validate-only` subcommand:

```bash
uv run python scripts/import_excel.py validate-only path/to/data.xlsx
```

Unlike `import --dry-run`, `validate-only` never instantiates the import pipeline and produces
no reconciliation counts. It is the fastest feedback loop for catching format and validation
errors before you are ready to run a full dry run.

## Full Import with Report

Once the dry run shows zero errors, run the full import:

```bash
uv run python scripts/import_excel.py import path/to/data.xlsx
```

By default the script runs silently on success. To print a reconciliation report to stdout,
add `--report`:

```bash
uv run python scripts/import_excel.py import --report path/to/data.xlsx
```

To save the report to a file instead of (or in addition to) printing it, use `--output-file`:

```bash
uv run python scripts/import_excel.py import --report --output-file report.txt path/to/data.xlsx
```

The report file contains the same text as the stdout output.

### What the script does

1. Reads all tabs from the workbook into memory.
2. Maps column headers to ORM field names (applying aliases).
3. Validates every row. If any `ERROR`-level messages are produced, the import is aborted and
   nothing is written to the database.
4. Upserts entities using the partial unique index on `ein` where `is_active = true AND deleted_at IS NULL` as the conflict target. `legal_name` is never overwritten on conflict.
5. Inserts, updates, or skips child records (owners, registrations, bank accounts, tax filings,
   registered agents) based on per-table duplicate detection (see [Re-running After Corrections](#re-running-after-corrections)).
6. Commits the transaction. On any unhandled exception the transaction is rolled back.

The process is wrapped in a single async session. Either all writes succeed together, or none
are committed.

## Re-running After Corrections

The script is designed to be re-run safely. Correcting your workbook and running again will not
create duplicates.

### Entity upsert

Entities use PostgreSQL `ON CONFLICT DO UPDATE` on the partial unique index on `ein` where
`is_active = true AND deleted_at IS NULL`. Re-importing an entity row updates all columns
**except `legal_name`** with the current workbook values. `legal_name` is excluded from the
conflict update to prevent silently overwriting the stored name when an EIN collision occurs.
This means EIN is required for each entity row; a row missing EIN is rejected by validation
before it reaches the database.

### Child record deduplication

All tabs use upsert or pre-insert duplicate detection:

| Tab | Deduplication strategy |
|---|---|
| `Entities` | `ON CONFLICT DO UPDATE` on the partial unique index on `ein` where `is_active = true AND deleted_at IS NULL` |
| `StateRegistrations` | `ON CONFLICT DO UPDATE` on `(entity_id, state, registration_type)` |
| `RegisteredAgents` | `ON CONFLICT DO UPDATE` on `(entity_id, state, is_active)` |
| `Owners` | Pre-check SELECT on same `entity_id`, `owner_name`, and `ownership_type`; skipped if found |
| `BankAccounts` | Pre-check SELECT on same `entity_id`, `bank_name`, and `account_number_last4`; skipped if found |
| `TaxFilings` | Pre-check SELECT on same `entity_id`, `tax_year`, `filing_type`, and `jurisdiction`; skipped if found |

Tabs that use `ON CONFLICT DO UPDATE` (Entities, StateRegistrations, RegisteredAgents) apply the
latest workbook values on re-run; their rows are counted as `updated` in the reconciliation
report. Tabs that use pre-check SELECT (Owners, BankAccounts, TaxFilings) skip existing rows
without modifying them; those rows are counted as `skipped`. To force an update to a skipped
child record, update it directly in the application UI or remove it from the database and
re-run.

## Troubleshooting

### EIN format error

**Symptom:**

```text
ERROR: Entities row 3 / ein: EIN '123456789' must match format XX-XXXXXXX (e.g. 12-3456789)
```

**Cause:** The EIN cell is missing the hyphen or has the wrong digit grouping.

**Fix:** EINs must be formatted as two digits, a hyphen, then seven digits: `12-3456789`.
In Excel, format the column as `Text` to prevent leading-zero truncation. If the IRS-issued
EIN is `123456789`, enter it as `12-3456789`.

The import aborts when any `ERROR` is present. Fix all EIN cells and re-run.

### Missing foreign key (entity not found)

**Symptom:**

```text
ERROR: Owners row 5 / entity_legal_name: No entity found with legal_name 'Acme Holdings LLC'
```

**Cause:** The value in `entity_legal_name` on the child tab does not match any `legal_name`
value in the `Entities` tab. The match is exact: capitalization, spacing, and punctuation must
be identical.

**Fix:** Check both the `Entities` tab and the child tab for subtle differences such as extra
spaces, different capitalization, or punctuation variants (`LLC` vs `L.L.C.`). The safest
approach is to copy the value directly from the `Entities` tab into the child tab cell.

If the entity itself has an `ERROR` on the `Entities` tab (for example, a bad EIN), it is
excluded from the known-names set used for FK validation, which will also cause this error on
all child rows for that entity. Fix the entity row first.

### Duplicate detection and re-run safety

**Scenario:** You run the import, notice a data issue, correct the workbook, and run again.

**Behavior:** The script uses upsert semantics throughout. Entities, StateRegistrations, and
RegisteredAgents use `ON CONFLICT DO UPDATE`; re-running applies the latest workbook values.
Owners, BankAccounts, and TaxFilings use pre-check SELECT to avoid duplicates; matched rows are
counted as `skipped` and left unchanged.

If you need to force an update to a skipped child record (Owner, BankAccount, or TaxFiling),
update it directly in the application or remove it from the database before re-running.

### Ownership percentage warning

**Symptom:**

```text
WARNING: Owners row 2 / ownership_percentage: Ownership percentages for 'Acme Holdings LLC' sum to 90.00, expected 100.00
```

**Cause:** The total of all `ownership_percentage` values for a single entity is not exactly
`100.00`. This is a `WARNING`, not an `ERROR`; the import proceeds.

**Fix:** Review all owner rows for the named entity and ensure the percentages sum to `100.00`.
Common causes: a row with a missing percentage, a rounding error (e.g., `33.33` + `33.33` +
`33.33` = `99.99`), or an owner row that was accidentally left out of the workbook.

### Database connection error

**Symptom:**

```text
sqlalchemy.exc.OperationalError: (asyncpg.exceptions.ConnectionRefusedError) ...
```

**Cause:** The script cannot reach the database.

**Fix:**

1. Confirm the container is running: `docker-compose ps db`.
2. Check that `.env` contains the correct `LLC_MANAGER_DATABASE_*` values.
3. On WSL2, ensure Docker Desktop's WSL integration is enabled and port `5432` is forwarded.
