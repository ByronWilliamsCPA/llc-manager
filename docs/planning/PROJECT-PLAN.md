# PROJECT-PLAN: LLC Manager

> **Status**: Ready for Development | **Version**: 2.0 | **Updated**: 2026-01-18
>
> This document synthesizes the project vision, technical spec, roadmap, and architecture decisions
> into an actionable development plan with git branches for each milestone.
>
> **Validation**: Plan validated via 5-model AI consensus (8.2/10 avg score). See [Consensus Report](#consensus-validation-summary).

## Executive Summary

**LLC Manager** is a web application for a small family office to centralize LLC entity information,
replacing fragmented Excel spreadsheets with a searchable, role-based dashboard that tracks
compliance dates, ownership structures, and entity documentation.

| Attribute | Value |
|-----------|-------|
| **Users** | 5-15 (family office staff and advisors) |
| **Entities** | 15-25 LLCs with ~50 related records each (~1,250 total records) |
| **Architecture** | FastAPI + HTMX/Jinja2 monolith ([ADR-001](adr/adr-001-initial-architecture.md)) |
| **Database** | PostgreSQL 15+ with SQLAlchemy 2.0 async |
| **Auth** | Authentik OIDC (OAuth2/PKCE) |
| **Deployment** | Single Docker container via Portainer |

---

## Current State Assessment

### Existing Codebase

The project already has foundational code in place:

| Component | Status | Location |
|-----------|--------|----------|
| Data Models | Complete | `src/llc_manager/models/` (Entity, Owner, StateRegistration, RegisteredAgent, TaxFiling, Document, BankAccount, EntityRelationship) |
| Pydantic Schemas | Complete | `src/llc_manager/schemas/` |
| Database Session | Complete | `src/llc_manager/db/session.py` |
| Configuration | Complete | `src/llc_manager/core/config.py` |
| Health Endpoint | Complete | `src/llc_manager/api/health.py` |
| Entity API Stub | Partial | `src/llc_manager/api/v1/endpoints/entities.py` |
| Exception Hierarchy | Complete | `src/llc_manager/core/exceptions.py` |
| Middleware (Security, Correlation) | Complete | `src/llc_manager/middleware/` |
| Structured Logging | Complete | `src/llc_manager/utils/logging.py` |

### What Needs Building

- Alembic migrations from existing models
- **Data import from Excel spreadsheets** (CRITICAL)
- Authentik OIDC integration
- Jinja2/HTMX templates and dashboard
- Entity CRUD service layer
- Audit/edit history tracking
- Compliance calendar and notifications
- Production Docker deployment with operational hardening

---

## Development Phases

```text
Phase 0: Foundation     ████░░░░░░░░░░░░  Week 1     - Migrations, Docker dev, CI, Seed Data
Phase 0.5: Data Import  ░░██░░░░░░░░░░░░  Week 1-2   - Excel migration tooling (CRITICAL)
Phase 1: Core MVP       ░░░░████████░░░░  Weeks 2-4  - Auth, CRUD, Dashboard (decomposed)
Phase 2: Compliance     ░░░░░░░░░░░░████  Weeks 5-6  - Calendar, Notifications, Ops Hardening
Phase 3: LLM (Future)   ░░░░░░░░░░░░░░░░  TBD        - Vector DB, Q&A
```

---

## Phase 0: Foundation

**Objective**: Establish development environment, database migrations, CI/CD pipeline, and seed data.

### Milestone M0: Development Environment Ready

**Branch**: `feat/phase-0-foundation`

| Task | Branch | Priority | Dependencies |
|------|--------|----------|--------------|
| Configure Alembic with async support | `feat/phase-0-alembic` | P0 | None |
| Create initial migration from models | `feat/phase-0-alembic` | P0 | Alembic config |
| Add partial unique index for soft deletes | `feat/phase-0-alembic` | P0 | Initial migration |
| Add docker-compose.yml for local dev | `feat/phase-0-docker-dev` | P0 | None |
| Configure Tailwind CSS (standalone CLI) | `feat/phase-0-tailwind` | P0 | None |
| Create seed data generator | `feat/phase-0-seed-data` | P0 | Alembic migrations |
| Configure GitHub Actions CI | `feat/phase-0-ci` | P1 | None |
| Write local development guide | `docs/local-dev-guide` | P2 | Docker dev |

### Seed Data Generator

Create `scripts/seed.py` to generate 10 dummy LLCs with related records for development:

```bash
uv run python scripts/seed.py --entities 10
```

### Soft Delete Unique Constraints

Ensure EIN uniqueness only for active entities:

```sql
CREATE UNIQUE INDEX idx_entity_ein_active ON entity (ein) WHERE is_active = true;
```

### Definition of Done

- [ ] `uv sync && uv run pytest` passes
- [ ] Alembic migrations apply to fresh PostgreSQL
- [ ] Partial unique indexes handle soft deletes correctly
- [ ] `docker compose up` starts dev environment with PostgreSQL
- [ ] Tailwind CSS watcher configured and working
- [ ] `uv run python scripts/seed.py` populates 10 test entities
- [ ] GitHub Actions CI passes (lint, type-check, test)
- [ ] Pre-commit hooks pass

### Key Commands

```bash
# Start Phase 0
git checkout -b feat/phase-0-foundation

# After Alembic setup
uv run alembic revision --autogenerate -m "Initial schema"
uv run alembic upgrade head

# Seed development data
uv run python scripts/seed.py --entities 10

# Docker dev
docker compose up -d
```

---

## Phase 0.5: Data Import (CRITICAL)

**Objective**: Create tooling to migrate existing Excel spreadsheet data to PostgreSQL.

> **Why Critical**: Manual entry of ~1,250 records (25 entities × 50 related records) is error-prone,
> time-consuming, and risks adoption delays. This milestone is essential for "Excel replacement" success.

### Milestone M0.5: Excel Data Import

**Branch**: `feat/data-import`

| Task | Branch | Priority | Dependencies |
|------|--------|----------|--------------|
| Define canonical CSV export format | `feat/data-import-spec` | P0 | None |
| Create field mapping documentation | `feat/data-import-spec` | P0 | CSV format |
| Implement `scripts/import_excel.py` | `feat/data-import` | P0 | Alembic migrations |
| Add validation and error reporting | `feat/data-import` | P0 | Import script |
| Implement dry-run mode | `feat/data-import` | P1 | Import script |
| Add reconciliation report | `feat/data-import` | P1 | Import script |
| Create import runbook documentation | `docs/data-import-guide` | P1 | Import script |

### Import Script Requirements

```python
# scripts/import_excel.py
# - Uses pandas + openpyxl for Excel parsing
# - Maps spreadsheet columns to Pydantic models
# - Validates data before insert (EIN format, dates, percentages)
# - Generates validation report with errors/warnings
# - Supports dry-run mode (--dry-run)
# - Idempotent upserts (can re-run safely)
```

### Acceptance Criteria

- [ ] Import script reads Excel files using pandas/openpyxl
- [ ] Field mapping handles all entity types (Entity, Owner, StateRegistration, etc.)
- [ ] Validation catches common errors (invalid EIN, missing required fields)
- [ ] Dry-run mode shows what would be imported without modifying database
- [ ] Reconciliation report compares imported data against source
- [ ] Successfully imports 25 entities + related records in < 60 seconds
- [ ] Import is idempotent (re-running doesn't create duplicates)

### Import Commands

```bash
# Validate Excel file without importing
uv run python scripts/import_excel.py data/llc_master.xlsx --dry-run

# Import with validation report
uv run python scripts/import_excel.py data/llc_master.xlsx --report

# Full import
uv run python scripts/import_excel.py data/llc_master.xlsx
```

---

## Phase 1: Core MVP

**Objective**: Implement entity CRUD with Authentik authentication and functional dashboard.

> **Note**: Milestones M3 and M4 have been decomposed into vertical slices for sprint-readiness.

### Milestone M1: Authentik SSO Working

**Branch**: `feat/phase-1-auth`

| Task | Branch | Priority | User Story |
|------|--------|----------|------------|
| Implement OIDC client with authlib | `feat/phase-1-oidc` | P0 | US-001 |
| Create auth routes (login, callback, logout) | `feat/phase-1-auth-routes` | P0 | US-001 |
| Add session middleware with secure cookies | `feat/phase-1-sessions` | P0 | US-001 |
| Implement CSRF protection for HTMX forms | `feat/phase-1-csrf` | P0 | US-001 |
| Configure cookie settings (Secure/HttpOnly/SameSite) | `feat/phase-1-sessions` | P0 | US-001 |
| Extract roles from Authentik group claims | `feat/phase-1-rbac` | P0 | US-001 |
| Handle role changes mid-session | `feat/phase-1-rbac` | P1 | US-001 |
| Implement local admin fallback | `feat/phase-1-local-admin` | P2 | - |
| Create Authentik outage runbook | `docs/authentik-outage` | P2 | - |

**Acceptance Criteria**:

- [ ] Login redirects to Authentik and returns with session
- [ ] Logout clears session and redirects
- [ ] CSRF tokens validated on all state-changing requests
- [ ] Cookies set with Secure, HttpOnly, SameSite=Lax
- [ ] `llc-manager-admins` group → admin role
- [ ] `llc-manager-viewers` group → viewer role
- [ ] Role changes in Authentik reflected within session timeout
- [ ] Local admin works when `AUTH_DEV_MODE=true`

### Milestone M2: Entity Dashboard

**Branch**: `feat/phase-1-dashboard`

| Task | Branch | Priority | User Story |
|------|--------|----------|------------|
| Create base Jinja2 layout template | `feat/phase-1-templates` | P0 | US-002 |
| Create HTMX partial templates | `feat/phase-1-templates` | P0 | US-002 |
| Create error page templates (404, 500) | `feat/phase-1-templates` | P0 | US-002 |
| Implement entity list router | `feat/phase-1-entity-list` | P0 | US-002 |
| Add search/filter functionality | `feat/phase-1-search` | P0 | US-002 |
| Add Postgres indexes for search performance | `feat/phase-1-search` | P0 | US-002 |
| Style with Tailwind CSS | `feat/phase-1-styling` | P1 | US-002 |

**Acceptance Criteria**:

- [ ] Dashboard shows entity name, EIN (masked), formation state
- [ ] Search filters by name, EIN, address
- [ ] Search returns results in < 500ms
- [ ] HTMX enables filtering without full page reload
- [ ] Error pages display user-friendly messages
- [ ] Responsive design works on desktop

### Milestone M3: Entity Detail View (Decomposed)

**Branch**: `feat/phase-1-entity-detail`

> Decomposed into vertical slices for 1-week sprints.

#### M3a: Entity Detail Skeleton

| Task | Branch | Priority |
|------|--------|----------|
| Create entity detail page layout | `feat/phase-1-detail-skeleton` | P0 |
| Display core entity fields | `feat/phase-1-detail-skeleton` | P0 |
| Implement entity service with eager loading | `feat/phase-1-entity-service` | P0 |

**Acceptance Criteria (M3a)**:

- [ ] Entity detail page loads in < 1 second
- [ ] Shows legal name, DBAs, EIN (masked), formation state/date
- [ ] Shows business address and accounting record ID

#### M3b: Owners Block

| Task                               | Branch                        | Priority |
|------------------------------------|-------------------------------|----------|
| Create owners section component    | `feat/phase-1-detail-owners`  | P0       |
| Display owner percentages and types| `feat/phase-1-detail-owners`  | P0       |

**Acceptance Criteria (M3b)**:

- [ ] Owners displayed with name, percentage, type
- [ ] Percentages sum validation shown if != 100%

#### M3c: Registrations Block

| Task | Branch | Priority |
|------|--------|----------|
| Create state registrations section | `feat/phase-1-detail-registrations` | P0 |
| Create registered agents section | `feat/phase-1-detail-registrations` | P0 |
| Display renewal dates with urgency indicators | `feat/phase-1-detail-registrations` | P0 |

**Acceptance Criteria (M3c)**:

- [ ] State registrations shown with status and renewal dates
- [ ] Registered agents shown with contact info
- [ ] Upcoming renewals highlighted

#### M3d: Financial & Documents Block

| Task | Branch | Priority |
|------|--------|----------|
| Create bank accounts section (masked) | `feat/phase-1-detail-financial` | P0 |
| Create tax filings section | `feat/phase-1-detail-financial` | P0 |
| Create documents list with download links | `feat/phase-1-detail-documents` | P0 |
| Validate Docker volume permissions for docs | `feat/phase-1-detail-documents` | P0 |

**Acceptance Criteria (M3d)**:

- [ ] Bank accounts hidden by default, reveal on click
- [ ] Tax filing due dates shown with status
- [ ] Documents accessible via 2 clicks from entity detail
- [ ] Docker container can read mounted document share

### Milestone M4: Entity CRUD (Decomposed)

**Branch**: `feat/phase-1-entity-crud`

> Decomposed into vertical slices for 1-week sprints.

#### M4a: Core Entity CRUD

| Task | Branch | Priority |
|------|--------|----------|
| Create entity create/edit forms | `feat/phase-1-entity-forms` | P0 |
| Implement Pydantic validation | `feat/phase-1-entity-forms` | P0 |
| Implement create/update routes | `feat/phase-1-entity-crud-core` | P0 |
| Add admin-only route guards | `feat/phase-1-admin-guards` | P0 |
| Implement soft delete | `feat/phase-1-entity-crud-core` | P0 |

**Acceptance Criteria (M4a)**:

- [ ] Admin can create new entity with validation
- [ ] Admin can edit existing entity
- [ ] Soft delete marks entity inactive
- [ ] Viewer cannot access create/edit forms

#### M4b: Owners CRUD

| Task | Branch | Priority |
|------|--------|----------|
| Create owner add/edit forms | `feat/phase-1-owners-crud` | P0 |
| Implement HTMX inline editing | `feat/phase-1-owners-crud` | P0 |
| Add percentage validation (sum to 100%) | `feat/phase-1-owners-crud` | P1 |

**Acceptance Criteria (M4b)**:

- [ ] Admin can add/edit/remove owners inline
- [ ] HTMX updates without page reload
- [ ] Warning if percentages don't sum to 100%

#### M4c: Registrations CRUD

| Task | Branch | Priority |
|------|--------|----------|
| Create state registration forms | `feat/phase-1-registrations-crud` | P0 |
| Create registered agent forms | `feat/phase-1-registrations-crud` | P0 |
| Implement HTMX inline editing | `feat/phase-1-registrations-crud` | P0 |

**Acceptance Criteria (M4c)**:

- [ ] Admin can add/edit state registrations
- [ ] Admin can add/edit registered agents
- [ ] Renewal dates validated for future dates

#### M4d: Documents & Tax CRUD

| Task | Branch | Priority |
|------|--------|----------|
| Create document metadata forms | `feat/phase-1-documents-crud` | P0 |
| Create tax filing forms | `feat/phase-1-tax-crud` | P0 |
| Validate file paths exist | `feat/phase-1-documents-crud` | P1 |

**Acceptance Criteria (M4d)**:

- [ ] Admin can add/edit document metadata
- [ ] Admin can add/edit tax filings
- [ ] File path validation warns if path doesn't exist

### Milestone M4e: Audit History

**Branch**: `feat/phase-1-audit-history`

> Implements "Edit History" requirement from project vision.

| Task | Branch | Priority |
|------|--------|----------|
| Add `updated_by` field to all models | `feat/phase-1-audit-fields` | P0 |
| Create change log table | `feat/phase-1-audit-log` | P0 |
| Implement audit logging middleware | `feat/phase-1-audit-log` | P0 |
| Add recent changes UI view | `feat/phase-1-audit-ui` | P1 |

**Acceptance Criteria (M4e)**:

- [ ] All create/update operations record actor and timestamp
- [ ] Change log captures field-level diffs for core tables
- [ ] Recent changes viewable in entity detail
- [ ] Audit log queryable by entity, user, or date range

### Phase 1 Definition of Done

- [ ] User can log in via Authentik SSO
- [ ] Dashboard displays all entities with search (< 500ms)
- [ ] Entity detail shows all related data (< 1s load)
- [ ] Admin can create/edit entities and all related records
- [ ] Viewer has read-only access
- [ ] Edit history tracked for all changes
- [ ] 80% test coverage on entity service layer
- [ ] CSRF protection verified on all forms

---

## Phase 2: Compliance & Notifications

**Objective**: Add compliance calendar with Apprise notifications, operational hardening, and production deployment.

### Milestone M5: Compliance Dashboard

**Branch**: `feat/phase-2-compliance`

| Task | Branch | Priority | User Story |
|------|--------|----------|------------|
| Create compliance service (aggregate deadlines) | `feat/phase-2-compliance-svc` | P0 | US-005 |
| Build 90-day grouped list component | `feat/phase-2-deadline-list` | P0 | US-005 |
| Add deadline filtering and sorting | `feat/phase-2-deadline-filter` | P1 | US-005 |

**Acceptance Criteria**:

- [ ] 90-day grouped list view by deadline type (RA, state, tax)
- [ ] Color-coded urgency indicators
- [ ] Click deadline to view entity detail

### Milestone M6: Apprise Notifications (Decomposed)

**Branch**: `feat/phase-2-notifications`

> Decomposed for sprint-readiness.

#### M6a: Notification Infrastructure

| Task | Branch | Priority |
|------|--------|----------|
| Implement Apprise client | `feat/phase-2-apprise` | P0 |
| Create notification log model | `feat/phase-2-notif-log` | P0 |
| Add retry/backoff for failed sends | `feat/phase-2-apprise` | P0 |

#### M6b: Scheduler Integration

| Task | Branch | Priority |
|------|--------|----------|
| Configure APScheduler | `feat/phase-2-scheduler` | P0 |
| Implement dedupe service | `feat/phase-2-scheduler` | P0 |
| Handle DST/timezone transitions | `feat/phase-2-scheduler` | P0 |
| Add scheduler restart recovery | `feat/phase-2-scheduler` | P1 |

#### M6c: Notification UI

| Task | Branch | Priority |
|------|--------|----------|
| Create notification templates | `feat/phase-2-notif-templates` | P0 |
| Build notification log UI | `feat/phase-2-notif-ui` | P1 |
| Add notification preferences UI | `feat/phase-2-notif-prefs` | P2 |

**Acceptance Criteria (M6)**:

- [ ] Configurable alerts at 7, 14, 30 days before deadline
- [ ] Idempotent notifications (deduped by entity/deadline/days_before)
- [ ] Failed notifications retry with exponential backoff
- [ ] Scheduler survives container restarts
- [ ] DST transitions don't cause missed/duplicate notifications
- [ ] Notification log viewable in UI
- [ ] Overdue items notify daily until resolved

### Milestone M6.5: Operational Hardening

**Branch**: `feat/phase-2-ops-hardening`

| Task | Branch | Priority |
|------|--------|----------|
| Document PostgreSQL backup procedure | `docs/backup-restore` | P0 |
| Define RPO/RTO targets | `docs/backup-restore` | P0 |
| Add pre-migration backup step to Dockerfile | `feat/phase-2-dockerfile` | P0 |
| Create Portainer rollback guide | `docs/portainer-rollback` | P1 |
| Add Prometheus metrics endpoint | `feat/phase-2-observability` | P1 |
| Configure basic alerting thresholds | `feat/phase-2-observability` | P2 |
| Create admin runbook (Authentik, docs mount) | `docs/admin-runbook` | P2 |

**Acceptance Criteria (M6.5)**:

- [ ] Backup procedure documented with RPO < 24h, RTO < 4h
- [ ] Pre-migration backup runs before `alembic upgrade head`
- [ ] Rollback procedure documented for Portainer
- [ ] Metrics exposed at `/metrics` (request latency, DB pool, scheduler runs)
- [ ] Admin runbook covers common operational tasks

### Milestone M7: Docker Deployment

**Branch**: `feat/phase-2-deployment`

| Task | Branch | Priority | User Story |
|------|--------|----------|------------|
| Create production Dockerfile | `feat/phase-2-dockerfile` | P0 | US-007 |
| Configure PUID/PGID for document mount | `feat/phase-2-dockerfile` | P0 | US-007 |
| Configure GHCR publish workflow | `feat/phase-2-ghcr` | P0 | US-007 |
| Add health check endpoint | `feat/phase-2-health` | P0 | US-007 |
| Write Portainer deployment guide | `docs/portainer-deploy` | P1 | US-007 |
| Create end-user quickstart guide | `docs/user-quickstart` | P2 | - |

**Acceptance Criteria**:

- [ ] Dockerfile builds optimized image with health check
- [ ] Container can read mounted document share (PUID/PGID configured)
- [ ] GitHub Actions pushes to ghcr.io on tag
- [ ] Portainer deployment guide documented
- [ ] Container starts with backup, migrations, and Uvicorn
- [ ] Health check endpoint returns 200

### Phase 2 Definition of Done

- [ ] Compliance dashboard shows 90-day deadlines
- [ ] Notifications fire via Apprise on schedule
- [ ] Scheduler handles DST and restarts correctly
- [ ] Backup/restore procedures documented and tested
- [ ] Rollback procedure documented
- [ ] Metrics exposed and monitored
- [ ] Docker image deploys to Portainer from ghcr.io
- [ ] Health check endpoint returns 200

---

## Phase 3: LLM Integration (Future)

Detailed planning after Phase 2 completion. Scope includes:

- Vector database (Qdrant) for semantic search
- PDF ingestion and document parsing
- LLM Q&A interface for natural language queries
- Document semantic search across ingested content

> **Note**: Schema evolution strategy needed for Phase 3 (vector embeddings, document chunks).

---

## Technical Reference

### Environment Variables

| Variable | Purpose | Required |
|----------|---------|----------|
| `DATABASE_URL` | PostgreSQL connection | Yes |
| `AUTHENTIK_ISSUER` | OIDC issuer URL | Yes |
| `AUTHENTIK_CLIENT_ID` | OAuth client ID | Yes |
| `AUTHENTIK_CLIENT_SECRET` | OAuth client secret | Yes |
| `SECRET_KEY` | Session encryption (32+ bytes) | Yes |
| `APPRISE_URL` | Apprise notification URL | Phase 2 |
| `LOCAL_ADMIN_USERNAME` | Local admin username | Optional |
| `LOCAL_ADMIN_PASSWORD` | Local admin password (argon2) | Optional |
| `AUTH_DEV_MODE` | Bypass OIDC for local dev | Dev only |
| `TZ` | Timezone for scheduler (use UTC internally) | Optional |
| `PUID` | User ID for document mount | Production |
| `PGID` | Group ID for document mount | Production |

### API Endpoints Summary

| Category | Method | Path | Auth |
|----------|--------|------|------|
| Dashboard | GET | `/` | Yes |
| Entities | GET | `/entities` | Yes |
| Entity Detail | GET | `/entities/{id}` | Yes |
| Entity Create | GET/POST | `/entities/new` | Admin |
| Entity Edit | GET/PUT | `/entities/{id}/edit` | Admin |
| Compliance | GET | `/compliance` | Yes |
| Search | GET | `/search` | Yes |
| Auth | GET | `/auth/login`, `/auth/callback` | No |
| Auth | POST | `/auth/logout` | Yes |
| Health | GET | `/api/v1/health` | No |
| Metrics | GET | `/metrics` | No |
| Documents | GET | `/api/v1/documents/{id}/download` | Yes |

### Performance Targets

| Metric | Target |
|--------|--------|
| Dashboard load | < 2 seconds |
| Entity detail | < 1 second |
| Search results | < 500ms |
| Document download | < 2 seconds |
| Memory usage | < 512MB |
| DB connections | ≤ 10 |

---

## Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Excel migration bottleneck** | High | High | Add import script in Phase 0.5 (CRITICAL) |
| **Data quality from import** | Medium | High | Validation report, dry-run mode, reconciliation |
| Authentik OIDC config complexity | Medium | High | Validate claims in first sprint of Phase 1 |
| Scheduler DST/timezone drift | Medium | Medium | Use UTC internally, test DST transitions |
| Document link rot | Medium | Medium | Store relative paths, validate on display |
| HTMX partial failures | Low | Medium | Add error handling templates |
| PostgreSQL connection pool exhaustion | Low | High | Set pool limits (10), add monitoring |
| Apprise service unavailable | Low | Medium | Retry with backoff, dead-letter logging |
| Observability gap | Low | High | Add Prometheus metrics endpoint |

---

## Getting Started

```bash
# 1. Check current branch (should be main)
git branch --show-current

# 2. Create foundation branch
git checkout -b feat/phase-0-foundation

# 3. Install dependencies
uv sync --all-extras

# 4. Run tests to verify setup
uv run pytest -v

# 5. Start development with first task
# (Configure Alembic, create migrations, seed data, etc.)
```

---

## Related Documents

- [Project Vision](project-vision.md) - Problem statement, scope, success metrics
- [Technical Spec](tech-spec.md) - Architecture, data model, API design
- [Development Roadmap](roadmap.md) - Timeline, user stories, tasks
- [ADR-001](adr/adr-001-initial-architecture.md) - FastAPI + HTMX architecture decision

---

## Assumptions to Validate

Before starting development, verify:

- [ ] Authentik instance supports OIDC with group claims for role-based access
- [ ] Apprise instance is accessible from Docker network
- [ ] PostgreSQL database is provisioned and accessible
- [ ] Document file paths reference accessible network storage
- [ ] Docker container can access network share with correct UID/GID
- [ ] GitHub Container Registry is configured for Portainer pulls
- [ ] Excel spreadsheet format is documented for import script

---

## Consensus Validation Summary

This plan was validated by a 5-model AI consensus analysis on 2026-01-18.

### Models Consulted

| Model | Stance | Score |
|-------|--------|-------|
| Gemini 2.5 Pro | Advocate | 8/10 |
| Gemini 3 Pro Preview | Critic | 9/10 |
| GPT-5.2 | Neutral | 8/10 |
| DeepSeek R1 | Critic (Risk) | 8/10 |
| Grok-4 | Neutral (Execution) | 8/10 |

**Average Score**: 8.2/10

### Key Findings Addressed

1. **Data Migration** (CRITICAL) - Added Phase 0.5 with Excel import tooling
2. **Milestone Granularity** - Decomposed M3, M4, M6 into sprint-sized slices
3. **Audit History** - Added M4e to implement "edit history" from vision
4. **Operational Hardening** - Added M6.5 with backup, rollback, observability
5. **Auth Edge Cases** - Added CSRF, session hardening tasks to M1
6. **Seed Data** - Added to Phase 0 for parallel development
7. **Risk Register** - Expanded with data quality, scheduler, observability risks
