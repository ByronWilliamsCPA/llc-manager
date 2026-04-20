# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Global Settings**: Baseline development standards live in `~/.claude/CLAUDE.md` v1.4.0 (user-level). This project-level file contains **project-specific** guidance only. Global rules (RAD, security, git workflow, package selection, supervisor patterns) are not duplicated here.

## Project Overview

**LLC Manager** is a full-stack web application for managing LLC entities, tracking compliance dates, ownership structures, and associated documentation.

- **Backend**: FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL 16
- **Frontend**: React 19 + TypeScript + Vite
- **Package Manager**: UV (Python), npm (frontend)
- **Author**: Byron Williams <byron@williamscpa.com>
- **Repository**: <https://github.com/ByronWilliamsCPA/llc-manager>
- **Python**: 3.12

---

## Template Feedback Requirement (CRITICAL)

This project was generated from the [cookiecutter-python-template](https://github.com/ByronWilliamsCPA/cookiecutter-python-template) using cruft.

**MANDATORY**: When working on this project, if you identify any issue that should have been addressed in the template (missing files, incorrect configurations, documentation gaps, tooling issues, etc.), you MUST:

1. Add the feedback to [docs/template_feedback.md](docs/template_feedback.md)
2. Include:
   - **Issue**: Clear description of what's wrong or missing
   - **Context**: How you discovered it
   - **Suggested Fix**: What the template should do differently
   - **Priority**: Critical / High / Medium / Low

This feedback is shared with the template team to improve the cookiecutter template for future projects.

---

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

### Documentation

```bash
uv run mkdocs serve            # Local preview on :8000
uv run mkdocs build            # Build static site
```

---

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

---

## Code Conventions

**Project-specific patterns**:

- Configuration: Pydantic Settings with `.env` files; env var prefix `LLC_MANAGER_`
- Logging: Structured logging via `src/llc_manager/utils/logging.py`
- Error Handling: Custom exceptions in `src/llc_manager/core/exceptions.py`
- Correlation: Request tracing via `src/llc_manager/middleware/correlation.py`
- Docstrings: Google style (enforced by darglint)

### Exception Hierarchy

Use the centralized exception hierarchy for consistent error handling:

```python
from llc_manager.core.exceptions import (
    ValidationError,
    ResourceNotFoundError,
    ConfigurationError,
    AuthenticationError,
    AuthorizationError,
    ExternalServiceError,
    APIError,
    DatabaseError,
    BusinessLogicError,
)

raise ValidationError(
    "Invalid email format",
    field="email",
    value=user_input,
)
```

| Exception | Use Case |
|-----------|----------|
| `ConfigurationError` | Missing/invalid config |
| `ValidationError` | Input validation failures |
| `ResourceNotFoundError` | Missing resources (404) |
| `AuthenticationError` | Auth failures (401) |
| `AuthorizationError` | Permission denied (403) |
| `ExternalServiceError` | Third-party service failures |
| `APIError` | External API errors |
| `DatabaseError` | Database operation errors |
| `BusinessLogicError` | Domain rule violations |

### Correlation ID Patterns (Observability)

Request correlation enables distributed tracing and log correlation:

```python
from fastapi import FastAPI
from llc_manager.middleware import (
    CorrelationMiddleware,
    get_correlation_id,
    add_security_middleware,
)

app = FastAPI()
app.add_middleware(CorrelationMiddleware)   # Add first
add_security_middleware(app)

@app.get("/")
async def root():
    return {"correlation_id": get_correlation_id()}
```

| Header | Purpose |
|--------|---------|
| `X-Correlation-ID` | Primary correlation header |
| `X-Request-ID` | Unique request identifier |
| `X-Trace-ID` | Distributed tracing ID |
| `X-Span-ID` | Span ID for tracing |

Structured logs auto-include the correlation ID when `setup_logging(include_correlation=True)` is configured. For background jobs, call `set_correlation_id(generate_correlation_id())` explicitly.

---

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

---

## Project Planning Documents

> **First-Time Setup**: If planning documents show "Awaiting Generation", see the [Project Setup Guide](docs/PROJECT_SETUP.md#project-planning-with-claude-code).

**Planning documents** (in `docs/planning/`):

- [project-vision.md](docs/planning/project-vision.md) - Problem, solution, scope, success metrics
- [tech-spec.md](docs/planning/tech-spec.md) - Architecture, data model, APIs, security
- [roadmap.md](docs/planning/roadmap.md) - Phased implementation plan
- [adr/](docs/planning/adr/) - Architecture decisions with rationale
- [PROJECT-PLAN.md](docs/planning/PROJECT-PLAN.md) - Synthesized plan with git branches

**References**:

- **Complete Workflow**: [Project Setup Guide](docs/PROJECT_SETUP.md#project-planning-with-claude-code)
- **Skill Reference**: `.claude/skills/project-planning/`

### Quick Start

```bash
# 1. Generate planning documents
/plan <your project description>

# 2. Synthesize into project plan
"Synthesize my planning documents into a project plan"

# 3. Review docs/planning/PROJECT-PLAN.md

# 4. Start development
/git/milestone start feat/phase-0-foundation
```

---

## CI/CD Pipeline

**GitHub Actions workflows**:

1. **CI** (`.github/workflows/ci.yml`): tests, linting, type checking
2. **Security** (`.github/workflows/security-analysis.yml`): CodeQL, Bandit, Safety
3. **Docs** (`.github/workflows/docs.yml`): build and deploy documentation
4. **Publish** (`.github/workflows/publish-pypi.yml`): PyPI release automation
5. **SonarCloud** (`.github/workflows/sonarcloud.yml`): code quality analysis
6. **FIPS compatibility** (`.github/workflows/fips-compatibility.yml`): crypto algorithm audit

Project-level gates (must all pass in CI):

- All tests pass with 80% line coverage minimum
- Ruff lint clean
- BasedPyright strict mode clean
- Bandit and pip-audit: no high/critical findings
- Pre-commit hooks pass

---

## Third-Party Integrations

### CodeRabbit (AI Code Reviews)

CodeRabbit runs an automated review on every pull request.

- **Configuration**: `.coderabbit.yaml`
- **Features**: automatic review on PR creation, security vulnerability detection, code quality suggestions, path-specific review instructions
- **Commands**: in PR comments, `@coderabbitai summary`, `@coderabbitai review`, `@coderabbitai help`
- **Setup**: install the [CodeRabbit GitHub App](https://github.com/apps/coderabbitai)

---

## Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| Test suite | <30s | Full suite with coverage |
| CI pipeline | <5min | All checks |
| Code coverage | 80% line / 70% branch / 90% critical / 90% patch | Enforced via Codecov tiers |

---

## Troubleshooting

### Pre-commit hooks failing

```bash
pre-commit run --all-files           # Run manually
pre-commit clean                     # Clean cache
pre-commit install --install-hooks   # Reinstall
```

### UV lock issues

```bash
uv lock                          # Regenerate lock
uv sync --all-extras             # Reinstall dependencies (includes dev tools)
```

### BasedPyright type errors

```bash
uv run basedpyright src/  # Show type errors
# For unavoidable suppressions, add `# pyright: ignore[error-code]` with a ticket reference
```

---

## Cruft Template Updates

This project uses a **two-part standards system** for safe template updates:

1. **Baseline files** in `.standards/` are updated automatically by cruft
2. **Root files** (`CLAUDE.md`, `REUSE.toml`) contain customizations
3. Merge agent integrates baseline changes into the root files

### Update workflow

```bash
# 1. Check for template updates
cruft check

# 2. View what would change
cruft diff

# 3. Update (baselines in .standards/ updated automatically)
cruft update --skip CLAUDE.md --skip REUSE.toml --skip docs/template_feedback.md

# 4. Check if baselines changed
git diff .standards/

# 5. If baselines changed, merge them into the root files
/merge-standards
```

### Files to ALWAYS skip during cruft update

These contain project-specific customizations:

- `CLAUDE.md` (merge from `.standards/CLAUDE.baseline.md`)
- `REUSE.toml` (merge from `.standards/REUSE.baseline.toml`)
- `docs/template_feedback.md` (project-specific template feedback)
- `docs/planning/*` (project planning documents)
- `.env` (environment configuration)

### Baseline files reference

| Baseline | Merges into | Purpose |
|----------|-------------|---------|
| `.standards/CLAUDE.baseline.md` | `CLAUDE.md` | Development standards |
| `.standards/REUSE.baseline.toml` | `REUSE.toml` | SPDX licensing |

See `.standards/README.md` for detailed merge instructions.

---

## Additional Resources

- **Project README**: [README.md](README.md)
- **Contributing Guide**: [CONTRIBUTING.md](CONTRIBUTING.md)
- **Security Policy**: [SECURITY.md](SECURITY.md)
- **Project Setup Guide**: [docs/PROJECT_SETUP.md](docs/PROJECT_SETUP.md)
- **Template Feedback**: [docs/template_feedback.md](docs/template_feedback.md)
- **Global Standards**: `~/.claude/CLAUDE.md` (RAD, security, git workflow, package selection)
- **UV Documentation**: <https://docs.astral.sh/uv/>
- **Ruff Documentation**: <https://docs.astral.sh/ruff/>
