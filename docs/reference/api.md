---
title: "API Reference"
schema_type: common
status: published
owner: core-maintainer
purpose: "REST API reference for the LLC Manager application."
tags:
  - api
  - reference
---

LLC Manager exposes a REST API built with FastAPI. All endpoints are versioned
under `/api/v1/`.

## Interactive Documentation

When running locally, the interactive Swagger UI is available at:

- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
- OpenAPI JSON schema: <http://localhost:8000/openapi.json>

## Endpoint Groups

### Entities (`/api/v1/entities`)

CRUD operations for LLC entities.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/entities` | List entities (paginated, searchable) |
| POST | `/api/v1/entities` | Create a new entity |
| GET | `/api/v1/entities/{id}` | Retrieve a single entity by UUID |
| PATCH | `/api/v1/entities/{id}` | Partially update an entity |
| DELETE | `/api/v1/entities/{id}` | Soft-delete an entity |

#### Compliance summary on entity responses

Every entity response (list, detail, create, update) carries a read-only
`compliance` object, computed on each read from the entity's state
registrations and tax filings. It adds no query to the list endpoint and
changes no existing field.

```json
{
  "compliance": {
    "next_due_date": "2026-04-01",
    "status": "due_soon",
    "registered_agent_name": "Example Registered Agents Inc"
  }
}
```

| Field | Meaning |
|-------|---------|
| `next_due_date` | Earliest outstanding date (UTC calendar date); in the past when overdue; `null` when nothing outstanding has a date |
| `status` | `overdue`, `due_soon` (due today through 60 days ahead), `current` (later than that), or `unknown` (nothing outstanding to judge). The worst status across obligations wins |
| `registered_agent_name` | Service company name when recorded, otherwise the agent name, of the active registered agent; `null` when none |

Rules: soft-deleted records and inactive entities are ignored; registrations
that are expired, withdrawn or revoked are ignored; an annual report counts as
filed when `last_annual_report` is dated no more than 90 days before
`annual_report_due` (or later), so filing early does not leave it overdue;
filed or not-required tax filings are ignored; a tax filing with status
`extended` uses its extended due date straight away, and any other filing
uses its original due date until that date has passed, then its extended due
date when one exists. See `llc_manager.services.compliance` for the full rule
set.

### Documents (`/api/v1/documents`)

Read-only access to stored document metadata and files. See
[Document Store and Import](../guides/documents.md) for the import command
and the polling rules.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/documents` | List document metadata (paginated; `updated_since`, `entity_id`, `category` filters) |
| GET | `/api/v1/documents/{id}` | Retrieve one document's metadata |
| GET | `/api/v1/documents/{id}/file` | Stream the stored file |

### Authentication

Every `/api/v1` route requires the `X-API-Key` header. A missing or wrong key
returns 401; a server with no key configured returns 503. The health probes
below do not require a key.

### Health Probes (`/api/health`)

Kubernetes liveness, readiness, and startup probes.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health/live` | Liveness check |
| GET | `/api/health/ready` | Readiness check (DB connectivity) |
| GET | `/api/health/startup` | Startup check |

## Full Auto-generated Reference

Comprehensive auto-generated API docs (input/output schemas, validation rules,
and example payloads) are a planned documentation task. Until then, use the
Swagger UI at `/docs` for the complete schema reference.
