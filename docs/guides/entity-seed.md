---
title: "Entity Seed"
schema_type: common
status: published
owner: core-maintainer
purpose: "How to create and update entities from a private JSON seed file."
tags:
  - guide
  - usage
---

The entity seed command creates or updates entities from a JSON file you keep
outside this repository. It is how `individual` and `household` entities are
created (the Excel importer rejects those types), and it gives every entity a
UUID that stays the same across re-seeds and database rebuilds. The design is
recorded in [ADR-002](../planning/adr/adr-002-individual-household-entities.md).

## Quick start

```bash
# Check a file without touching the database
uv run python -m llc_manager.cli.seed_entities --file ~/private/entity-seed.json --validate-only

# Apply it, and write the key-to-UUID mapping for other seeds to read
uv run python -m llc_manager.cli.seed_entities \
  --file ~/private/entity-seed.json \
  --mapping-out ~/private/entity-map.json
```

The file path may also come from `LLC_MANAGER_ENTITY_SEED_FILE`. The command
prints counts and value-free problems only. It never prints names, EINs,
UUIDs, or tenant IDs, and it names a database error by its class and
constraint only.

## File format

```json
{
  "version": 1,
  "namespace": "<a random UUID you generate once and keep>",
  "entities": [
    {"key": "household", "entity_type": "household", "legal_name": "..."},
    {"key": "person-a", "entity_type": "individual", "legal_name": "..."},
    {
      "key": "holding-llc",
      "entity_type": "llc",
      "legal_name": "...",
      "ein": "00-0000000",
      "xero_tenant_id": "..."
    }
  ]
}
```

| Field | Required | Meaning |
| --- | --- | --- |
| `version` | No | Seed format version. Only `1` exists. |
| `namespace` | Yes, for a real seed | UUID used to derive entity IDs. Generate it once (for example with `python -c "import uuid; print(uuid.uuid4())"`) and never change it. |
| `synthetic` | No | `true` marks test data. See [Synthetic files](#synthetic-files). |
| `entities` | Yes | At least one entry. |

Each entry takes every field the entity API accepts, plus:

| Field | Required | Meaning |
| --- | --- | --- |
| `key` | Yes | Private stable key: lower case letters, digits, `.`, `_`, `-`. Never change it once used. |
| `entity_type` | Yes | Any entity type, including `individual` and `household`. |
| `id` | No | Pin an existing entity's UUID instead of deriving one (for entities created before the seed). |

Rules checked before anything is written:

- Keys, resolved IDs, EINs, and Xero tenant IDs are unique within the file.
- There is exactly one `household` and at least one `individual`.
- An `individual` or `household` has no `ein`, `formation_state`, or
  `formation_date`.
- A real (non-synthetic) file sets its own `namespace`.
- An empty `ein` is stored as null.

## Stable IDs

An entity's UUID is `uuid5(namespace, key)`, or its pinned `id`. Re-running
the seed never changes an ID. Changing the `namespace` or a `key` produces a
different UUID, which breaks every system that stored the old one, so treat
both as permanent.

## What a re-seed changes

- Missing entities are created.
- Existing entities get only the fields the file names; fields set later in
  the UI are kept. A field set to `null` in the file is cleared.
- An entity that was soft-deleted is left alone, reported as a problem by its
  entry number, and left out of the mapping file. Remove the entry from the
  file, or restore the entity, to clear it.
- An EIN or Xero tenant ID may move between entities in the same file.

## Mapping file

`--mapping-out` writes `{"namespace": ..., "entities": {key: {"id",
"entity_type", "xero_tenant_id"}}}`. It is written after the database
commit, atomically, with owner-only permissions on POSIX systems (on Windows
it takes the directory's access control list). The path must be outside the
repository and must resolve under your home directory, or under
`LLC_MANAGER_MAPPING_DIR` when that is set; any other path is refused before
the database is touched. With `--validate-only` the mapping is computed from the file
alone, so soft-deleted entities are not detected.

## Synthetic files

A file inside the repository is refused unless it is under `data/examples/`
and marked `"synthetic": true`, like `data/examples/entity_seed.example.json`.
A synthetic file is applied to a database only with `--allow-synthetic`, so
example data does not reach a real database by accident.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success. |
| 1 | The file is invalid; nothing applied. |
| 2 | Usage, path, or location error; nothing applied. |
| 3 | Database error; nothing committed. |
| 4 | Applied, but some entries name a soft-deleted entity. |
| 5 | Applied and committed, but the mapping file could not be written. |

## Security notes

Until the entity API requires authentication, do not load real `individual`
or `household` data into a database that API serves beyond localhost: entity
responses include personal names and bank account last-4 digits.
