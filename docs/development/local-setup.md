---
title: "Local Development Setup"
schema_type: common
status: published
owner: core-maintainer
purpose: "Step-by-step guide to running LLC Manager locally: Python environment, database, Tailwind CSS, and the dev server."
tags:
  - development
  - guide
---

This guide covers everything needed to run LLC Manager locally: Python environment, database,
Tailwind CSS, and the dev server.

---

## Prerequisites

| Tool | Required | Notes |
|------|----------|-------|
| Python 3.12 | Yes | Managed via `uv` |
| [uv](https://docs.astral.sh/uv/) | Yes | Python package manager |
| Docker + Compose | Yes | PostgreSQL runs in Docker |
| curl | Yes | Tailwind binary download (first run only) |

Node.js and npm are **not required**. Tailwind CSS uses a standalone binary.

---

## First-Time Setup

```bash
# 1. Clone and enter the repo
git clone https://github.com/ByronWilliamsCPA/llc-manager.git
cd llc-manager

# 2. Install Python dependencies (creates .venv automatically)
uv sync --all-extras

# 3. Install pre-commit hooks
uv run pre-commit install

# 4. Copy environment config
cp .env.example .env          # Edit DB_PASSWORD and other secrets as needed
```

---

## Running the Stack

### Start PostgreSQL

```bash
docker compose up -d db
```

This starts `llc_manager-db` on port 5432 with persistent volume `postgres-data`.

### Apply Database Migrations

```bash
uv run alembic upgrade head
```

Run this once on first setup and after pulling commits that add new migrations.

### Start the API + UI Dev Server

```bash
uv run uvicorn llc_manager.main:app --reload --host 0.0.0.0 --port 8000
```

The app is now available at <http://localhost:8000>.

- Dashboard: <http://localhost:8000/>
- API docs: <http://localhost:8000/api/docs>
- Health: <http://localhost:8000/api/health/live>

The `--reload` flag restarts the server on any Python or template file change.

---

## Tailwind CSS

### Development (watch mode)

In a separate terminal, run the Tailwind watcher. On first run it downloads the standalone
CLI binary (~12 MB); subsequent runs skip the download.

```bash
bash scripts/tailwind-watch.sh
```

The watcher rebuilds `src/llc_manager/static/css/output.css` whenever a template or
`input.css` changes. Keep it running alongside the dev server.

### One-off build

```bash
./tailwindcss \
  -i src/llc_manager/static/css/input.css \
  -o src/llc_manager/static/css/output.css
```

### Production build (minified)

```bash
./tailwindcss \
  -i src/llc_manager/static/css/input.css \
  -o src/llc_manager/static/css/output.css \
  --minify
```

`output.css` is git-ignored. It must be present for the UI to render correctly.
The Docker image build step runs the minified build automatically via the Dockerfile.

---

## Templates

Jinja2 templates live in `src/llc_manager/templates/`.

```text
templates/
├── base.html       # Layout: nav, flash messages, Tailwind link, HTMX + Alpine CDNs
└── index.html      # Dashboard (extends base.html)
```

To add a new page:

1. Create `templates/<page>.html` extending `base.html`
2. Add a route in the appropriate `api/` file (or a new `ui/` router) using `templates.TemplateResponse`
3. Add a nav link in `base.html`

---

## Frontend Stack

LLC Manager uses a server-side HTML approach: no JavaScript bundler or SPA framework.

| Library | How it loads | Purpose |
|---------|--------------|---------|
| HTMX 2 | CDN in `base.html` | Server-driven partial updates (`hx-get`, `hx-post`, etc.) |
| Alpine.js 3 | CDN in `base.html` | Inline reactivity (dropdowns, toggles, `x-show`, `x-data`) |
| Tailwind CSS | Standalone CLI | Utility-first styling; zero runtime overhead |

CDN integrity hashes are pinned in `base.html`. Update them when bumping versions.

---

## Code Quality

All checks must pass before committing:

```bash
uv run ruff format .               # Auto-format
uv run ruff check . --fix          # Lint + auto-fix
uv run basedpyright src/           # Type check
uv run bandit -r src               # Security scan
pre-commit run --all-files         # All hooks (includes the above + more)
```

### Running Tests

```bash
uv run pytest -v                              # All tests
uv run pytest --cov=src --cov-report=html     # With HTML coverage report
uv run pytest tests/unit/test_main.py -v      # Single file
```

Coverage target: 80% line, 70% branch.

---

## Database Migrations

```bash
# Apply all pending migrations
uv run alembic upgrade head

# Generate a new migration from model changes
uv run alembic revision --autogenerate -m "add column X to entity"

# Check current migration version
uv run alembic current

# Downgrade one step
uv run alembic downgrade -1
```

Always review auto-generated migrations before applying. Alembic does not detect all
schema changes (column type changes, constraints) correctly.

---

## Common Issues

### `output.css` not found / UI unstyled

Run `bash scripts/tailwind-watch.sh` to build Tailwind output. It is git-ignored and
must be generated locally.

### `tailwindcss` binary not found

The `tailwind-watch.sh` script downloads it automatically. If it fails:

```bash
# Manual download (Linux x86_64)
curl -sL https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-x64 \
  -o tailwindcss && chmod +x tailwindcss
```

### Database connection refused

```bash
docker compose ps db          # Check if container is healthy
docker compose up -d db       # Start if stopped
docker compose logs db        # View PostgreSQL logs
```

### Pre-commit hook failures

```bash
pre-commit clean              # Clear hook cache
pre-commit install            # Reinstall hooks
pre-commit run --all-files    # Run manually to see errors
```
