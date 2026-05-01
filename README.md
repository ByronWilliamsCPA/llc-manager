# LLC Manager

## Quality & Security

[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/ByronWilliamsCPA/llc-manager/badge)](https://securityscorecards.dev/viewer/?uri=github.com/ByronWilliamsCPA/llc-manager)
[![codecov](https://codecov.io/gh/ByronWilliamsCPA/llc-manager/graph/badge.svg)](https://codecov.io/gh/ByronWilliamsCPA/llc-manager)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=ByronWilliamsCPA_llc-manager&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=ByronWilliamsCPA_llc-manager)
[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=ByronWilliamsCPA_llc-manager&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=ByronWilliamsCPA_llc-manager)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=ByronWilliamsCPA_llc-manager&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=ByronWilliamsCPA_llc-manager)
[![REUSE Compliance](https://github.com/ByronWilliamsCPA/llc-manager/actions/workflows/reuse.yml/badge.svg)](https://github.com/ByronWilliamsCPA/llc-manager/actions/workflows/reuse.yml)

## CI/CD Status

[![CI Pipeline](https://github.com/ByronWilliamsCPA/llc-manager/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ByronWilliamsCPA/llc-manager/actions/workflows/ci.yml?query=branch%3Amain)
[![Security Analysis](https://github.com/ByronWilliamsCPA/llc-manager/actions/workflows/security-analysis.yml/badge.svg?branch=main)](https://github.com/ByronWilliamsCPA/llc-manager/actions/workflows/security-analysis.yml?query=branch%3Amain)
[![Documentation](https://github.com/ByronWilliamsCPA/llc-manager/actions/workflows/docs.yml/badge.svg?branch=main)](https://github.com/ByronWilliamsCPA/llc-manager/actions/workflows/docs.yml?query=branch%3Amain)
[![SBOM & Security Scan](https://github.com/ByronWilliamsCPA/llc-manager/actions/workflows/sbom.yml/badge.svg?branch=main)](https://github.com/ByronWilliamsCPA/llc-manager/actions/workflows/sbom.yml?query=branch%3Amain)
[![PR Validation](https://github.com/ByronWilliamsCPA/llc-manager/actions/workflows/pr-validation.yml/badge.svg)](https://github.com/ByronWilliamsCPA/llc-manager/actions/workflows/pr-validation.yml)
[![Release](https://github.com/ByronWilliamsCPA/llc-manager/actions/workflows/release.yml/badge.svg)](https://github.com/ByronWilliamsCPA/llc-manager/actions/workflows/release.yml)
[![PyPI Publish](https://github.com/ByronWilliamsCPA/llc-manager/actions/workflows/publish-pypi.yml/badge.svg)](https://github.com/ByronWilliamsCPA/llc-manager/actions/workflows/publish-pypi.yml)

## Project Info

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Code style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Contributor Covenant](https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg)](https://github.com/ByronWilliamsCPA/.github/blob/main/CODE_OF_CONDUCT.md)

|                |                                                                               |
| -------------- | ----------------------------------------------------------------------------- |
| **Author**     | Byron Williams                                                                |
| **Created**    | 2026-01-18                                                                    |
| **Repository** | [ByronWilliamsCPA/llc-manager](https://github.com/ByronWilliamsCPA/llc-manager) |

---

## Overview

A web application for managing LLC entities, tracking compliance dates, ownership structures, and associated documentation.

This project provides:

- CRUD API for LLC entities with pagination, search, and filtering
- Production-ready FastAPI backend with async PostgreSQL
- React + TypeScript frontend
- Security-first development practices with SBOM, SLSA provenance, and supply chain hardening

## Features

- **High Quality**: 80%+ test coverage enforced via CI
- **Type Safe**: Full type hints with BasedPyright strict mode
- **Well Documented**: Clear docstrings and full guides
- **Developer Friendly**: Pre-commit hooks, automated formatting, linting
- **Security First**: Dependency scanning, security analysis, SBOM generation

## Quick Start

### Prerequisites

- Python 3.12+
- [UV](https://docs.astral.sh/uv/) for dependency management
- Node.js 20+ and npm (for frontend)
- Docker + Docker Compose (for local PostgreSQL)

**Install UV**:

```bash
# macOS and Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Installation

```bash
# Clone repository
git clone https://github.com/ByronWilliamsCPA/llc-manager.git
cd llc-manager

# Install dependencies (includes dev tools)
uv sync --all-extras

# Setup pre-commit hooks
uv run pre-commit install
```

### Running the API

```bash
# Start PostgreSQL
docker-compose up -d db

# Apply migrations
uv run alembic upgrade head

# Start the API server
uv run uvicorn llc_manager.main:app --reload
# API available at http://localhost:8000
# Docs at http://localhost:8000/api/docs
```

## Frontend Development

The frontend is a React + TypeScript application built with Vite.

### Frontend Quick Start

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at <http://localhost:3000> with hot reload.

### Available Scripts

| Command                      | Description                         |
| ---------------------------- | ----------------------------------- |
| `npm run dev`                | Start dev server with HMR           |
| `npm run build`              | Build for production                |
| `npm run test`               | Run tests                           |
| `npm run lint:fix`           | Lint and auto-fix                   |
| `npm run typecheck`          | Run TypeScript type checking        |
| `npm run generate-client`    | Generate API client from OpenAPI    |

### API Client Generation

Generate a type-safe TypeScript client from the FastAPI OpenAPI schema:

```bash
# Start backend first
uv run uvicorn llc_manager.main:app &

# Generate client
cd frontend && npm run generate-client
```

This creates typed API functions in `frontend/src/client/`.

### Docker

```bash
# Full stack (API :8000, frontend :3000, PostgreSQL :5432)
docker-compose up -d

# Production image
docker build -t llc_manager .
```

## Development

### Setup Development Environment

```bash
# Install all dependencies including dev tools
uv sync --all-extras

# Setup pre-commit hooks
uv run pre-commit install

# Run tests
uv run pytest -v

# Run with coverage
uv run pytest --cov-report=html

# Run all quality checks
uv run pre-commit run --all-files
```

### Code Quality Standards

All code must meet these requirements:

- **Formatting**: Ruff (88 char limit)
- **Linting**: Ruff with PyStrict-aligned rules (see below)
- **Type Checking**: BasedPyright strict mode
- **Testing**: Pytest with 80%+ coverage
- **Security**: Bandit + dependency scanning
- **Documentation**: Docstrings on all public APIs

### PyStrict-Aligned Ruff Configuration

This project uses **PyStrict-aligned Ruff rules** for stricter code quality enforcement beyond standard Python linting:

| Rule | Category | Purpose |
| --- | --- | --- |
| **BLE** | Blind except | Prevent bare `except:` clauses |
| **EM** | Error messages | Enforce descriptive error messages |
| **SLF** | Private access | Prevent access to private members |
| **INP** | Implicit packages | Require explicit `__init__.py` |
| **ISC** | Implicit concatenation | Prevent implicit string concatenation |
| **PGH** | Pygrep hooks | Advanced pattern-based checks |
| **RSE** | Raise statement | Proper exception raising |
| **TID** | Tidy imports | Clean import organization |
| **YTT** | sys.version | Safe version checking |
| **FA** | Future annotations | Modern annotation syntax |
| **T10** | Debugger | No debugger statements in production |
| **G** | Logging format | Safe logging string formatting |

These rules catch bugs that standard linting misses and enforce production-quality code patterns.

### Running Tests

```bash
# Run all tests
uv run pytest -v

# Run specific test file
uv run pytest tests/unit/test_health.py -v

# Run with coverage report
uv run pytest --cov-report=term-missing

# Run tests in parallel
uv run pytest -n auto
```

### Individual Tool Commands

```bash
# Format code
uv run ruff format .

# Lint and auto-fix
uv run ruff check --fix .

# Type checking
uv run basedpyright src

# Security scanning
uv run bandit -r src

# Dependency vulnerabilities
uv run pip-audit
```

## Project Structure

```text
llc-manager/
├── src/llc_manager/
│   ├── main.py                        # FastAPI app factory
│   ├── core/
│   │   ├── config.py                  # Pydantic Settings (env: LLC_MANAGER_*)
│   │   ├── exceptions.py              # Exception hierarchy
│   │   ├── cache.py                   # Redis cache client
│   │   └── sentry.py                  # Sentry error tracking
│   ├── db/
│   │   ├── base.py                    # SQLAlchemy Base + mixins
│   │   └── session.py                 # Async engine + session dependency
│   ├── models/                        # SQLAlchemy ORM models
│   │   ├── entity.py                  # Core LLC entity
│   │   ├── owner.py                   # Ownership structure
│   │   ├── state_registration.py
│   │   ├── bank_account.py
│   │   ├── document.py
│   │   ├── tax_filing.py
│   │   ├── registered_agent.py
│   │   └── entity_relationship.py     # Parent/child entity graph
│   ├── schemas/                       # Pydantic request/response schemas
│   │   ├── base.py
│   │   └── entity.py, owner.py, ...
│   ├── api/
│   │   ├── health.py                  # Kubernetes probes
│   │   └── v1/endpoints/
│   │       └── entities.py            # CRUD endpoints
│   ├── middleware/
│   │   ├── correlation.py             # X-Correlation-ID propagation
│   │   └── security.py               # SSRF protection
│   └── utils/
│       ├── logging.py                 # Structlog with correlation ID
│       └── financial.py              # Decimal precision utilities
├── frontend/                          # React + TypeScript (Vite)
├── tests/
│   ├── unit/
│   └── integration/
├── docs/                              # MkDocs documentation
├── alembic/                           # Database migrations
├── pyproject.toml
└── docker-compose.yml
```

## Documentation

- **[CONTRIBUTING.md](CONTRIBUTING.md)**: How to contribute to the project
- **[docs/planning/](docs/planning/)**: Project planning documents
- **[docs/planning/adr/](docs/planning/adr/)**: Architecture Decision Records

## Testing

### Testing Policy

All new functionality must include tests:

- **Unit tests**: Test individual functions/classes
- **Integration tests**: Test component interactions
- **Coverage**: Maintain 80%+ coverage
- **Markers**: Use pytest markers (`@pytest.mark.unit`, `@pytest.mark.integration`)

### Test Guidelines

```bash
# Run all tests
uv run pytest -v

# Run only unit tests
uv run pytest -v -m unit

# Run only integration tests
uv run pytest -v -m integration

# Run with coverage requirements
uv run pytest
```

## Security

### Security-First Development

- Validate all inputs
- Use secure defaults
- Scan dependencies regularly
- Report vulnerabilities responsibly

### Reporting Security Issues

Please report security vulnerabilities to <byron@williamscpa.com> rather than using the public issue tracker.

See the [ByronWilliamsCPA Security Policy](https://github.com/ByronWilliamsCPA/.github/blob/main/SECURITY.md) for complete disclosure policy and response timelines.

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for:

- Development setup
- Code quality standards
- Testing requirements
- Git workflow and commit conventions
- Pull request process

### Quick Checklist Before Submitting PR

- [ ] Code follows style guide (Ruff format + lint)
- [ ] All tests pass with 80%+ coverage
- [ ] BasedPyright type checking passes
- [ ] Docstrings added for new public APIs
- [ ] CHANGELOG.md updated (if significant change)
- [ ] Commits follow conventional commit format

## Versioning

This project uses [Semantic Versioning](https://semver.org/):

- **MAJOR** version: Incompatible API changes
- **MINOR** version: Backwards-compatible functionality additions
- **PATCH** version: Backwards-compatible bug fixes

Current version: **0.1.0**

### Automated Releases with Semantic Release

This project uses [python-semantic-release](https://python-semantic-release.readthedocs.io/) for automated versioning based on [Conventional Commits](https://www.conventionalcommits.org/).

**How it works:**

1. **Commit messages determine version bumps:**
   - `fix:` commits trigger a **PATCH** release (1.0.0 → 1.0.1)
   - `feat:` commits trigger a **MINOR** release (1.0.0 → 1.1.0)
   - `BREAKING CHANGE:` in commit body or `!` after type triggers **MAJOR** release (1.0.0 → 2.0.0)

2. **On merge to main:**
   - Analyzes commits since last release
   - Determines appropriate version bump
   - Updates version in `pyproject.toml`
   - Generates/updates `CHANGELOG.md`
   - Creates Git tag and GitHub Release
   - Publishes to PyPI (if configured)

**Commit message examples:**

```bash
# Patch release (bug fix)
git commit -m "fix: resolve null pointer in data parser"

# Minor release (new feature)
git commit -m "feat: add CSV export functionality"

# Major release (breaking change)
git commit -m "feat!: redesign API for better ergonomics

BREAKING CHANGE: API has been redesigned for improved usability.
See migration guide in docs/migration/v2.0.0.md"
```

**Configuration:** See `[tool.semantic_release]` in `pyproject.toml` for settings.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Support

- **Issues**: [GitHub Issues](https://github.com/ByronWilliamsCPA/llc-manager/issues)
- **Discussions**: [GitHub Discussions](https://github.com/ByronWilliamsCPA/llc-manager/discussions)
- **Email**: <byron@williamscpa.com>

## Acknowledgments

Thank you to all contributors and the open-source community!

---

**Made with ❤️ by [Byron Williams](https://github.com/ByronWilliamsCPA)**
