---
title: "Checking a Document Manifest (Dry Run)"
schema_type: common
status: published
owner: core-maintainer
purpose: "How to check a document import manifest before importing, and how to read the per-row report."
tags:
  - guide
  - api
---

Run a dry run before every import. It reads the manifest and every source file,
prints one status line per row, and exits non-zero if anything is wrong. It
does not open a database session, copy a file, or create the documents root.

## Start from the template

`data/examples/document_manifest_template.example.csv` holds the header and two
made-up rows. Copy it outside the repository, replace the rows, and keep the
header unchanged. The command refuses a manifest inside the checkout unless its
name ends in `.example.csv`.

```bash
cp data/examples/document_manifest_template.example.csv ~/private/manifest.csv
```

The column meanings are in the [documents guide](documents.md#the-manifest).

## Run it

```bash
python -m llc_manager.cli.import_documents \
  --manifest ~/private/manifest.csv \
  --source-root ~/private/scans \
  --entity-map ~/private/entity-map.json \
  --dry-run
```

`--dry-run` and `--validate-only` are the same option.

## What it checks

| Check | Reported as |
| --- | --- |
| Required columns present, no unknown or duplicate columns | `problem: header: ...` |
| The manifest has at least one data row | `problem: manifest has no rows` |
| A row has no more cells than the header has columns | `more cells than header columns` |
| `entity` is a UUID or a key in the entity map | `column 'entity': ...` |
| `file` is present, inside the source root, a supported type | `column 'file': ...` |
| `file` is readable | `column 'file': file could not be read` |
| No two rows point at the same file, or at files with identical bytes (SHA-256) | `column 'file': same bytes (SHA-256) as line N` |
| `confidential` and `consent_on_file` are `true`/`false` (also `yes`/`no`, `y`/`n`, `1`/`0`) or blank | `column '...': expected true or false` |
| `consent_on_file` is true only on `Tax Returns` rows | `column 'consent_on_file': ...` |
| `document_date` and `effective_date` are `YYYY-MM-DD` or blank | `column '...': expected a YYYY-MM-DD date` |
| `document_type` and `category` are known values; `title` is 1 to 255 characters | `column '...': ...` |

Entity existence in the database is not checked: the dry run has no database
access. The import checks it before copying any file.

The dry run is stricter than the import about duplicate bytes. An import does
not fail on a new row whose bytes match a document already stored, or an
earlier row in the same run: it skips the row and lists its line in
`duplicate_lines=`. The dry run fails on identical bytes within one manifest,
so a manifest can pass the import yet fail the dry run. The skipped row's
metadata would never be stored, so decide which row you want: remove one, or
point it at the correct file.

## Reading the report

This is a real run on the template plus one extra row whose file does not
exist:

```text
rows=2
category[Estate Planning]=1
category[Tax Returns]=1
tax_returns_without_consent=0
line 2: ok
line 3: ok
line 4: error
  column 'file': file not found
checked=3 ok=2 errors=1
```

The first four lines summarize the valid rows only, so `rows=2` here, not 3.
Lines after that are manifest line numbers (the header is line 1), one per
row. `checked`, `ok` and `errors` count rows; `errors` also counts problems
that belong to no row, such as a header problem or an empty manifest, which
print as `problem: ...` and give `checked=0 ok=0 errors=1` (or more). The
report never prints titles, file paths, or IDs. Only the first problem in a
row is shown, so fix it and run again until every row is `ok`.

Exit codes: 0 when every row is ok, 1 when any row or the header has a
problem, 2 when the manifest or entity map cannot be opened or decoded.

## Document IDs

Document IDs are unchanged by the dry run: each is derived from the file path
relative to the source root, so a re-import updates rows in place. Do not move
or rename source files between imports unless you intend new documents.
