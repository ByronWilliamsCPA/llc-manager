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
