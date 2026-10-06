---
title: "Document Store and Import"
schema_type: common
status: published
owner: core-maintainer
purpose: "How documents are imported from a manifest and served by the read-only API."
tags:
  - guide
  - api
---

LLC Manager keeps one stored file per document under a documents root and
serves document metadata and files through a read-only API. Documents enter
the store through an admin manifest and the `import_documents` command.

## Settings

| Variable | Purpose | Default |
| --- | --- | --- |
| `LLC_MANAGER_API_KEY` | Shared key every `/api/v1` caller sends as `X-API-Key`. At least 32 characters outside development. `LLC_MANAGER_SERVICE_API_KEY` is read when this is unset. | unset or empty (all `/api/v1` requests get 503) |
| `LLC_MANAGER_DOCUMENTS_ROOT` | Directory that holds stored files. | `/data/docs` |
| `LLC_MANAGER_DOCUMENT_MANIFEST` | Manifest path when `--manifest` is not given. | unset |

Supply the API key from your secrets manager. Never commit a real value.

## The manifest

A UTF-8 CSV with a header row. Required columns are `file`, `entity`,
`document_type`, `category`, and `title`; the rest may be blank.

| Column | Meaning |
| --- | --- |
| `file` | Source file, relative to `--source-root` (default: the manifest's folder) or absolute. Supported: `.pdf`, `.png`, `.jpg`, `.jpeg`, `.tif`, `.tiff`, `.txt`. |
| `entity` | Owning entity: a UUID, or a key from the entity map written by `seed_entities --mapping-out`. Every document has an owner; personal documents use an `individual` or `household` entity. |
| `document_type` | A `DocumentType` value, for example `will`, `tax_return`, `operating_agreement`. |
| `category` | One of `Estate Planning`, `LLCs`, `Trusts`, `Tax Returns`, `Insurance`, `Personal records`, `Other` (case does not matter). |
| `title` | 1 to 255 characters. |
| `document_date`, `effective_date` | `YYYY-MM-DD` or blank. |
| `confidential` | `true`/`false` (also `yes`/`no`, `1`/`0`); blank means false. |
| `consent_on_file` | Same values. `true` is only allowed for the `Tax Returns` category. |

A synthetic example lives at `data/examples/document_manifest.example.csv`,
with sample files under `data/examples/documents/`. Real manifests must live
outside the repository; the command refuses any manifest inside the checkout
whose name does not end in `.example.csv`.

## Validate, then import

```bash
# Check the manifest and source files; change nothing.
python -m llc_manager.cli.import_documents \
  --manifest /private/manifest.csv \
  --entity-map /private/entity-map.json \
  --validate-only

# Import.
python -m llc_manager.cli.import_documents \
  --manifest /private/manifest.csv \
  --entity-map /private/entity-map.json
```

The command prints counts and value-free problems only, for example
`rows=4`, `category[Tax Returns]=1`, `tax_returns_without_consent=0`, and
`problem: line 3: column 'category': unknown category`. It never prints
titles, paths, or IDs. Exit codes: 0 success, 1 validation problems, 2 usage
or file errors (including a manifest that cannot be opened or decoded), 3
unexpected failure while importing. An exit-3 run prints only the exception
class name, for example `error: import failed (OSError)`, rolls back the
database transaction, and deletes any staged files. Entity existence is
checked at import time, before any file is copied. When a run skips
duplicates it also prints `duplicate_lines=` with the manifest line numbers.

The manifest, the entity map, and every source file must live outside the
repository's source tree; a `file` entry that resolves outside the source root
(through `..` or a symlink) is reported as a problem and not read.

## What an import does

- **Stable IDs.** A document's ID is `uuid5(namespace, file)`, where `file`
  is the path relative to the source root. Re-importing the same manifest
  updates rows in place.
- **Stage, commit, publish.** Each new or changed file is first copied to a
  hidden temporary name in the documents root with mode `0640`. The database
  transaction commits next, and only then are the staged files renamed to
  `{documents_root}/{document_id}{extension}`. A failure before the commit
  leaves the store untouched. If the process dies between the commit and the
  rename, re-running the import detects a missing or mismatched stored file
  (by re-hashing the stored bytes) and repairs it.
- **Hash.** SHA-256 is computed for every row. A changed file updates
  `sha256`, `file_size`, and `updated_at`.
- **Duplicates.** A new row whose bytes match a document already stored (or
  one earlier in the same run) is skipped and counted as a duplicate.
- **Updates.** Metadata changes (title, entity, category, dates, flags)
  update the existing row. Soft-deleted documents are left alone.

Importing the same manifest twice creates each document once.

## Read-only API

All routes require the `X-API-Key` header. A missing or wrong key returns
401; an unconfigured server returns 503. Requests are rate limited per client
address (60 per minute, 10 per second burst); a limited request gets 429 with
`Retry-After`. Send the key from server-side code only: CORS does not allow
the `X-API-Key` header from a browser.

| Route | Returns |
| --- | --- |
| `GET /api/v1/documents` | `{"items": [...], "total", "page", "size", "pages"}`. Query: `page`, `size` (max 200), `updated_since` (ISO 8601; no zone means UTC), `entity_id`, `category`. Ordered by `updated_at`, then `id`. |
| `GET /api/v1/documents/{id}` | One document's metadata. |
| `GET /api/v1/documents/{id}/file` | The stored file, with its MIME type, `Content-Length`, and `X-Content-Type-Options: nosniff`. 404 for an unknown ID or a missing file. |

Items carry `id`, `title`, `category`, `document_type`, `entity_id`,
`document_date`, `effective_date`, `is_confidential`, `consent_on_file`,
`sha256`, `mime_type`, `file_size`, `created_at`, and `updated_at`. No
filesystem path is ever returned.

The file route locates the file by document ID only. It never uses a path
from the request or the database, and it refuses any resolved path outside
the documents root, including through a symlink.

## Polling for changes

`updated_since` matches any document whose `updated_at` is at or after the
given time; a create, a file replacement, or a metadata edit all move
`updated_at`. Paging is by offset, and `updated_at` is the transaction start
time, so a document edited while a consumer pages (or committed late by a long
import) can land behind the consumer's watermark. A consumer should poll with
a watermark a few minutes behind the newest `updated_at` it has seen and
de-duplicate by `id`. Soft-deleted documents are excluded from the list, so
deletions do not appear in this feed.
