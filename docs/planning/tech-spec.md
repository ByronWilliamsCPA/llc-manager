# Technical Implementation Spec: LLC Manager

> **Status**: Draft | **Version**: 1.0 | **Updated**: 2026-01-18

## TL;DR

FastAPI monolith with HTMX/Jinja2 frontend, PostgreSQL database via SQLAlchemy 2.0 async, Authentik OIDC authentication, deployed as a single Docker container behind Traefik. See [ADR-001](./adr/adr-001-initial-architecture.md) for architecture rationale.

## Technology Stack

### Core

- **Language**: Python 3.12
- **Package Manager**: UV
- **Framework**: FastAPI 0.115+
- **Templating**: Jinja2 with HTMX
- **ASGI Server**: Uvicorn

### Code Quality

- **Linter/Formatter**: Ruff (88 chars, PyStrict rules)
- **Type Checker**: BasedPyright (strict mode)
- **Testing**: pytest with pytest-asyncio

### Data Layer

- **Database**: PostgreSQL 15+ (existing infrastructure)
- **ORM**: SQLAlchemy 2.0 (async with asyncpg)
- **Migrations**: Alembic
- **Caching**: None (small dataset, not needed for MVP)

### Infrastructure

- **CI/CD**: GitHub Actions
- **Container**: Docker (single image)
- **Registry**: GitHub Container Registry (ghcr.io)
- **Deployment**: Portainer stack from GitHub
- **Reverse Proxy**: Traefik (Pangolin front-end)

## Architecture

### Pattern

Server-rendered monolith with progressive enhancement via HTMX - See [ADR-001](./adr/adr-001-initial-architecture.md)

### Component Diagram

```text
┌─────────────────────────────────────────────────────────────────┐
│                         Traefik (Pangolin)                      │
└───────────────────────────────┬─────────────────────────────────┘
                                │ HTTPS
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LLC Manager Container                         │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │   FastAPI   │  │   Jinja2    │  │      Static Files       │  │
│  │   Routers   │──│  Templates  │──│   (HTMX, CSS, Icons)    │  │
│  └──────┬──────┘  └─────────────┘  └─────────────────────────┘  │
│         │                                                        │
│  ┌──────┴──────────────────────────────────────────────────┐    │
│  │                    Service Layer                         │    │
│  │  (EntityService, ComplianceService, NotificationService) │    │
│  └──────┬───────────────────────────────┬──────────────────┘    │
│         │                               │                        │
│  ┌──────▼──────┐                 ┌──────▼──────┐                │
│  │  SQLAlchemy │                 │   Apprise   │                │
│  │    Async    │                 │   Client    │                │
│  └──────┬──────┘                 └──────┬──────┘                │
└─────────┼───────────────────────────────┼───────────────────────┘
          │                               │
          ▼                               ▼
    ┌───────────┐                  ┌────────────┐
    │ PostgreSQL│                  │  Apprise   │
    │  Database │                  │  Instance  │
    └───────────┘                  └────────────┘

    ┌───────────┐
    │ Authentik │◄──── OIDC auth requests from LLC Manager
    │   OIDC    │
    └───────────┘
```

### Component Responsibilities

| Component | Purpose | Key Functions |
| --------- | ------- | ------------- |
| FastAPI Routers | HTTP handling | Route requests, auth guards, validation |
| Jinja2 Templates | UI rendering | HTML generation, HTMX partials |
| Service Layer | Business logic | CRUD operations, compliance checks |
| SQLAlchemy | Data access | Async queries, transactions |
| Apprise Client | Notifications | Send deadline alerts |
| Authentik | Authentication | OIDC login, token validation |

## Data Model

### Core Entities

The data model is already implemented in `src/llc_manager/models/`. Key entities:

```python
# Entity (LLC) - Core business entity
class Entity:
    id: UUID
    legal_name: str
    dba_names: str | None
    ein: str | None
    entity_type: EntityType  # LLC, Corporation, etc.
    formation_state: str | None
    formation_date: date | None
    business_address: str | None
    accounting_record_id: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

# Owner - Ownership records
class Owner:
    id: UUID
    entity_id: UUID  # FK to Entity
    name: str
    ownership_percentage: Decimal
    ownership_type: OwnershipType  # MEMBER, MANAGER, etc.

# StateRegistration - State filing records
class StateRegistration:
    id: UUID
    entity_id: UUID
    state_code: str
    registration_date: date
    renewal_date: date | None
    status: str

# RegisteredAgent - RA information
class RegisteredAgent:
    id: UUID
    entity_id: UUID
    agent_name: str
    address: str
    renewal_date: date | None

# TaxFiling - Tax due dates
class TaxFiling:
    id: UUID
    entity_id: UUID
    filing_type: TaxFilingType  # FEDERAL, STATE, etc.
    due_date: date
    filed_date: date | None

# Document - Document metadata
class Document:
    id: UUID
    entity_id: UUID
    document_type: DocumentType
    title: str
    file_path: str
    notes: str | None
```

### Relationships

- Entity → Owner: One-to-Many
- Entity → StateRegistration: One-to-Many
- Entity → RegisteredAgent: One-to-Many
- Entity → TaxFiling: One-to-Many
- Entity → Document: One-to-Many
- Entity → Entity (via EntityRelationship): Many-to-Many (parent/child)

## API Specification

### HTML Endpoints (Browser)

| Method | Path | Purpose | Auth |
| ------ | ---- | ------- | ---- |
| GET | `/` | Dashboard with entity list | Yes |
| GET | `/entities` | Entity list (HTMX partial) | Yes |
| GET | `/entities/{id}` | Entity detail view | Yes |
| GET | `/entities/new` | New entity form | Admin |
| POST | `/entities` | Create entity | Admin |
| GET | `/entities/{id}/edit` | Edit entity form | Admin |
| PUT | `/entities/{id}` | Update entity | Admin |
| DELETE | `/entities/{id}` | Delete entity | Admin |
| GET | `/compliance` | Compliance calendar | Yes |
| GET | `/search` | Search results (HTMX) | Yes |

### Auth Endpoints

| Method | Path | Purpose | Auth |
| ------ | ---- | ------- | ---- |
| GET | `/auth/login` | Redirect to Authentik | No |
| GET | `/auth/callback` | OIDC callback | No |
| POST | `/auth/logout` | Logout, clear session | Yes |

### API Endpoints (JSON)

| Method | Path | Purpose | Auth |
| ------ | ---- | ------- | ---- |
| GET | `/api/v1/health` | Health check | No |
| GET | `/api/v1/entities` | List entities JSON | Yes |
| GET | `/api/v1/entities/{id}` | Entity detail JSON | Yes |
| GET | `/api/v1/compliance/upcoming` | Upcoming deadlines | Yes |

### Response Format (JSON API)

```json
{
  "data": {
    "id": "uuid",
    "type": "entity",
    "attributes": {
      "legal_name": "string",
      "ein": "string"
    }
  },
  "meta": {
    "timestamp": "ISO8601"
  }
}
```

## Document Serving Strategy

Browsers block local file system links (`file://`) for security. Documents must be served via HTTP.

### Implementation

- **Storage**: Mount network storage to `/data/docs` in Docker container
- **Endpoint**: `GET /api/v1/documents/{id}/download` streams file content
- **Access Control**: Require authenticated session; check entity access permissions
- **Metadata Only**: Database stores `file_path` relative to mount point, not absolute paths

### Docker Volume Mount

```yaml
volumes:
  - /path/to/network/share:/data/docs:ro
```

### Document Endpoint

| Method | Path                               | Purpose                | Auth |
| ------ | ---------------------------------- | ---------------------- | ---- |
| GET    | `/api/v1/documents/{id}/download`  | Stream document file   | Yes  |
| GET    | `/api/v1/documents/{id}/metadata`  | Get document metadata  | Yes  |

## Notification Scheduler

### Library

**APScheduler** with `AsyncIOScheduler` - integrates natively with FastAPI/Uvicorn without separate worker container.

### Configuration

- **Run Frequency**: Daily at 06:00 system timezone
- **Timezone**: System timezone (configurable via `TZ` env var)
- **Dedupe Key**: `(entity_id, deadline_type, deadline_date, days_before)`
- **Idempotency**: Check notification log before sending; skip if already sent

### Notification Log Schema

```python
class NotificationLog:
    id: UUID
    entity_id: UUID
    deadline_type: str  # "ra_renewal", "state_filing", "tax_due"
    deadline_date: date
    days_before: int  # 7, 14, or 30
    sent_at: datetime
    apprise_response: str | None
```

### Alert Triggers

| Days Before | Alert Type |
|-------------|------------|
| 30 | Early warning |
| 14 | Reminder |
| 7 | Urgent |
| 0 | Due today |
| -N | Overdue (daily until resolved) |

## Security

### Authentication

**Authentik OIDC** - See [Authentik OIDC Provider Docs](https://docs.goauthentik.io/docs/providers/oauth2/)

- Authorization Code Flow with PKCE
- Session cookie after successful auth
- Token refresh handled automatically

### Authorization

**Role-Based Access Control (RBAC)**:

| Role | Permissions |
|------|-------------|
| `admin` | Full CRUD on all entities |
| `viewer` | Read-only access to all entities |

### RBAC Details

**Authentik Group Claims**:

| Authentik Group | Application Role | Notes |
|-----------------|------------------|-------|
| `llc-manager-admins` | `admin` | Full CRUD access |
| `llc-manager-viewers` | `viewer` | Read-only access |

**Claim Extraction**: Roles sourced from `groups` claim in OIDC token. Map group names to application roles.

**Fallback Behavior**:

- No matching group → Deny access (403)
- Multiple groups → Use highest privilege (admin > viewer)
- Missing `groups` claim → Deny access (403)

**Local Admin Account** (Authentik Fallback):

- **Purpose**: Emergency access when Authentik is unavailable
- **Username**: Configured via `LOCAL_ADMIN_USERNAME` env var
- **Password**: Configured via `LOCAL_ADMIN_PASSWORD` env var (hashed with argon2)
- **Access**: Full admin privileges; bypasses OIDC flow
- **Login Path**: `GET /auth/local-login` (hidden from main UI)
- **Audit**: All local admin actions logged with `auth_method: local`

**Local Development**:

- Set `AUTH_DEV_MODE=true` to bypass OIDC
- Auto-login as admin role for local testing

### Data Protection

- **At Rest**: PostgreSQL TDE (if enabled on host)
- **In Transit**: TLS via Traefik termination
- **Sensitive Data**: EIN masked in UI (show last 4), bank accounts hidden by default

### OWASP Considerations

- CSRF protection via SameSite cookies + double-submit token
- XSS prevention via Jinja2 autoescape
- SQL injection prevented by SQLAlchemy parameterization
- Rate limiting via Traefik middleware

## Error Handling

### Strategy

Fail-fast with user-friendly error pages. Log all errors with correlation IDs.

### Error Codes

| Code | Meaning | User Action |
|------|---------|-------------|
| 400 | Validation error | Check form inputs |
| 401 | Not authenticated | Login required |
| 403 | Not authorized | Contact admin for access |
| 404 | Entity not found | Check URL or search |
| 500 | Server error | Retry or contact support |

### Logging

- **Format**: Structured JSON via structlog
- **Levels**: DEBUG, INFO, WARNING, ERROR
- **Correlation**: Request ID in all log entries
- **Sensitive**: Never log EIN, bank account numbers

## Performance Requirements

| Metric | Target | Measurement |
|--------|--------|-------------|
| Dashboard load | < 2s | Time to first contentful paint |
| Entity detail | < 1s | HTMX swap complete |
| Search results | < 500ms | HTMX response time |
| Memory usage | < 512MB | Container limit |
| Database connections | ≤ 10 | Connection pool max |

## Testing Strategy

### Coverage Target

- Minimum: 80%
- Critical paths (auth, entity CRUD): 95%

### Test Types

- **Unit**: Service layer logic, data validation
- **Integration**: Database operations, Authentik mock
- **E2E**: Playwright for login flow, entity CRUD

### Test Configuration

```python
# pytest.ini
[pytest]
asyncio_mode = auto
testpaths = tests
addopts = --cov=src/llc_manager --cov-report=term-missing
```

## Deployment

### Docker Image

```dockerfile
FROM python:3.12-slim
WORKDIR /app

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Install dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application code
COPY src ./src
COPY templates ./templates
COPY static ./static
COPY alembic.ini ./
COPY alembic ./alembic

# Health check (using Python since curl not available in slim image)
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" || exit 1

EXPOSE 8000

# Run migrations then start server
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn llc_manager.main:app --host 0.0.0.0"]
```

### Environment Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `DATABASE_URL` | PostgreSQL connection | `postgresql+asyncpg://user:pass@host/db` |
| `AUTHENTIK_ISSUER` | OIDC issuer URL | `https://auth.example.com/application/o/llc-manager/` |
| `AUTHENTIK_CLIENT_ID` | OAuth client ID | `llc-manager` |
| `AUTHENTIK_CLIENT_SECRET` | OAuth client secret | (secret) |
| `APPRISE_URL` | Apprise notification URL | `http://apprise:8000/notify` |
| `SECRET_KEY` | Session encryption | (32+ byte random) |
| `LOCAL_ADMIN_USERNAME` | Local admin username | `localadmin` |
| `LOCAL_ADMIN_PASSWORD` | Local admin password (argon2 hash) | (secret) |
| `AUTH_DEV_MODE` | Bypass OIDC for local dev | `true` or `false` |
| `TZ` | Timezone for scheduler | `America/New_York` |

## Related Documents

- [Project Vision](./project-vision.md)
- [Architecture Decisions](./adr/README.md)
- [Development Roadmap](./roadmap.md)
