---
title: "System Overview"
schema_type: common
status: published
owner: core-maintainer
purpose: "High-level system context and component layout for LLC Manager."
---

## System Context

LLC Manager is a single-tenant web application for managing LLC entities, tracking
compliance dates, ownership structures, and associated documentation. It serves a
small team of 5-15 users authenticated via Authentik OIDC. The system runs as a
single Docker container deployed to Portainer and communicates with a PostgreSQL 16
database over an internal network.

External dependencies:

- **PostgreSQL 16**: primary data store for all entity, ownership, and compliance data
- **Authentik**: OIDC identity provider handling login and session management
- **Apprise**: notification backend for compliance date alerts (future Phase 2)

The system exposes two endpoint surfaces from a single process:

- A REST API under `/api/v1/` for programmatic access and health probes
- Server-rendered HTML pages under `/` served via Jinja2 templates

## Component Layout

```text
Browser
  |
  | HTTP (HTMX + Alpine.js partial requests)
  v
FastAPI (Uvicorn)  [src/llc_manager/]
  |-- main.py              app factory, middleware registration
  |-- api/v1/endpoints/    REST endpoints (entities CRUD, pagination)
  |-- api/health.py        Kubernetes liveness / readiness / startup probes
  |-- middleware/
  |     |-- correlation.py X-Correlation-ID propagation across requests
  |     `-- security.py    SSRF protection, blocked host enforcement
  |-- templates/           Jinja2 HTML templates (base + page layouts)
  |-- static/css/          Tailwind CSS (built artifact: output.css)
  |-- models/              SQLAlchemy 2.0 ORM models (Entity, Owner, ...)
  |-- schemas/             Pydantic request/response schemas
  |-- db/
  |     |-- base.py        declarative Base + UUID / Audit mixins
  |     `-- session.py     async engine factory, get_async_session() DI dep
  `-- core/
        |-- config.py      Pydantic Settings (env prefix LLC_MANAGER_)
        `-- exceptions.py  typed exception hierarchy
  |
  | asyncpg (async) / psycopg (sync, Alembic only)
  v
PostgreSQL 16
```

Key design decisions and their rationale are recorded in
[ADR-001](../planning/adr/adr-001-initial-architecture.md).
