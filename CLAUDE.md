# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**LLC Manager** is a full-stack web application for managing LLC entities, tracking compliance dates, ownership structures, and associated documentation.

- **Backend**: FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL 16
- **Frontend**: React 19 + TypeScript + Vite
- **Package Manager**: UV (Python), npm (frontend)

## Commands

### Backend Development

```bash
# Setup
uv sync --all-extras
uv run pre-commit install

# Run API server (development)
docker-compose up -d db                    # Start PostgreSQL
uv run python -m llc_manager.main          # Or: uvicorn llc_manager.main:app --reload

# Testing
uv run pytest -v                           # All tests
uv run pytest tests/unit/test_file.py::test_name -v  # Single test
uv run pytest --cov=src --cov-report=html  # With coverage

# Code quality (all must pass before commit)
uv run ruff format .                       # Format
uv run ruff check . --fix                  # Lint
uv run basedpyright src/                   # Type check
uv run bandit -r src                       # Security scan
pre-commit run --all-files                 # All hooks

# Database migrations
uv run alembic upgrade head                # Apply migrations
uv run alembic revision --autogenerate -m "description"  # Generate migration
```

### Frontend Development

```bash
cd frontend
npm install
npm run dev                    # Dev server on :3000
npm run build                  # Production build
npm run test                   # Vitest tests
npm run lint:fix               # ESLint
npm run typecheck              # TypeScript check
npm run generate-client        # Generate API client from OpenAPI (backend must be running)
```

### Docker

```bash
docker-compose up -d           # Full stack (API :8000, frontend :3000, PostgreSQL :5432)
docker build -t llc_manager .  # Production image
```

## Architecture

### Backend Layer Structure

```text
src/llc_manager/
├── main.py                 # FastAPI app factory with create_app()
├── core/
│   ├── config.py          # Pydantic Settings (env: LLC_MANAGER_*)
│   └── exceptions.py      # Exception hierarchy (ValidationError, etc.)
├── db/
│   ├── base.py            # SQLAlchemy Base + mixins (UUIDPrimaryKeyMixin, AuditMixin)
│   └── session.py         # Async engine, get_async_session() dependency
├── models/                 # SQLAlchemy ORM models
│   ├── entity.py          # Core Entity (LLC) with all relationships
│   ├── owner.py           # Ownership structure
│   ├── state_registration.py
│   ├── bank_account.py
│   ├── document.py
│   ├── tax_filing.py
│   └── entity_relationship.py  # Parent/child entity graph
├── schemas/                # Pydantic request/response schemas
│   ├── base.py            # BaseSchema, FullSchema patterns
│   └── entity.py, owner.py, etc.
├── api/
│   ├── health.py          # Kubernetes probes (/api/health/live, /ready, /startup)
│   └── v1/endpoints/
│       └── entities.py    # CRUD endpoints with pagination, search, filtering
├── middleware/
│   ├── correlation.py     # X-Correlation-ID propagation
│   └── security.py        # SSRF protection
└── utils/
    ├── logging.py         # Structlog with correlation ID injection
    └── financial.py       # Decimal precision utilities
```

### Key Patterns

**Dependency Injection for DB Sessions**:

```python
from llc_manager.db.session import get_async_session
DBSession = Annotated[AsyncSession, Depends(get_async_session)]

@router.get("")
async def list_entities(db: DBSession) -> EntityListResponse:
    ...
```

**Model Mixins** (in `db/base.py`):

- `UUIDPrimaryKeyMixin`: UUID primary keys
- `TimestampMixin`: Auto-managed `created_at`, `updated_at`
- `AuditMixin`: Soft delete with `deleted_at`, `deleted_by`

**Entity Relationships**: The `Entity` model has relationships to `Owner`, `StateRegistration`, `BankAccount`, `Document`, `TaxFiling`. Entity hierarchies use `EntityRelationship` junction table.

### Frontend Structure

```text
frontend/src/
├── main.tsx               # Entry point
├── App.tsx                # Root component
├── components/
│   └── ApiStatus.tsx      # Backend connectivity check
├── hooks/
│   └── useApi.ts          # Axios wrapper hook
└── client/                # Generated from OpenAPI (npm run generate-client)
```

### API Endpoints

- `GET/POST /api/v1/entities` - List (paginated, searchable) / Create
- `GET/PATCH/DELETE /api/v1/entities/{id}` - Read / Update / Soft Delete
- `GET /api/health/live|ready|startup` - Kubernetes probes

### Database

- PostgreSQL 16 with async driver (asyncpg)
- All tables use UUID primary keys and soft delete
- Migrations via Alembic (sync driver: psycopg)

## Configuration

Environment variables prefixed with `LLC_MANAGER_`:

```bash
LLC_MANAGER_DATABASE_HOST=localhost
LLC_MANAGER_DATABASE_PORT=5432
LLC_MANAGER_DATABASE_USER=llc_manager
LLC_MANAGER_DATABASE_PASSWORD=...
LLC_MANAGER_DATABASE_NAME=llc_manager
LLC_MANAGER_API_PORT=8000
LLC_MANAGER_LOG_LEVEL=INFO
```

## Template Feedback

This project uses cookiecutter. Report template issues to [docs/template_feedback.md](docs/template_feedback.md).
