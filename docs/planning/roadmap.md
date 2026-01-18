# Development Roadmap: LLC Manager

> **Status**: Active | **Updated**: 2026-01-18

## TL;DR

Build an LLC entity management dashboard in three phases: foundation setup (Week 1), core CRUD with authentication (Weeks 2-4), and compliance calendar with notifications (Weeks 5-6). LLM integration planned for future Phase 3.

## Timeline Overview

```text
Phase 0: Foundation     ████░░░░░░░░░░░░ (1 week)   - Project setup, DB migrations
Phase 1: Core MVP       ░░░░████████░░░░ (3 weeks)  - Entity CRUD, Auth, Dashboard
Phase 2: Compliance     ░░░░░░░░░░░░████ (2 weeks)  - Calendar, Notifications
Phase 3: LLM Integration ░░░░░░░░░░░░░░░░ (Future)  - Vector DB, Document Q&A
```

## Milestones

| Milestone                 | Target | Status     | Dependencies |
| ------------------------- | ------ | ---------- | ------------ |
| M0: Dev Environment Ready | Week 1 | ⏸️ Planned | None         |
| M1: Database & Migrations | Week 1 | ⏸️ Planned | M0           |
| M2: Authentik SSO Working | Week 2 | ⏸️ Planned | M1           |
| M3: Entity CRUD Complete  | Week 3 | ⏸️ Planned | M2           |
| M4: Dashboard & Search    | Week 4 | ⏸️ Planned | M3           |
| M5: Compliance Calendar   | Week 5 | ⏸️ Planned | M4           |
| M6: Apprise Notifications | Week 6 | ⏸️ Planned | M5           |
| M7: Docker Deployment     | Week 6 | ⏸️ Planned | M6           |

---

## Phase 0: Foundation (Week 1)

### Phase 0 Objective

Establish development environment, database schema, and CI/CD pipeline.

### Phase 0 Deliverables

- [ ] Development environment documented and working
- [ ] Database migrations created from existing models
- [ ] CI/CD pipeline configured (lint, type-check, test)
- [ ] Docker development setup working
- [ ] Pre-commit hooks installed

### Phase 0 Success Criteria

- ✅ `uv sync && uv run pytest` passes
- ✅ Alembic migrations apply cleanly to fresh PostgreSQL
- ✅ GitHub Actions CI passes on main branch
- ✅ `docker compose up` starts development environment

### Tasks

| Task                                           | Branch                    | Status |
| ---------------------------------------------- | ------------------------- | ------ |
| Configure Alembic and create initial migration | `feat/phase-0-alembic`    | ⏸️     |
| Add asyncpg and SQLAlchemy async session       | `feat/phase-0-db-async`   | ⏸️     |
| Create docker-compose.yml for local dev        | `feat/phase-0-docker-dev` | ⏸️     |
| Configure GitHub Actions CI workflow           | `feat/phase-0-ci`         | ⏸️     |
| Write local development guide                  | `docs/local-dev-guide`    | ⏸️     |

---

## Phase 1: Core MVP (Weeks 2-4)

### Phase 1 Objective

Implement entity CRUD operations with Authentik authentication and a functional dashboard.

### Phase 1 Deliverables

- [ ] Authentik OIDC authentication working
- [ ] Entity list view with search/filter
- [ ] Entity detail view with all related data
- [ ] Entity create/edit forms (Admin role)
- [ ] Role-based access control (Admin vs Viewer)

### Phase 1 Success Criteria

- ✅ User can log in via Authentik SSO
- ✅ Dashboard displays all entities with search
- ✅ Admin can create/edit entities via HTMX forms
- ✅ Viewer role has read-only access
- ✅ 80% test coverage on entity service layer

### User Stories

#### US-001: SSO Authentication

**As a** family office user
**I want** to log in using our existing Authentik SSO
**So that** I don't need separate credentials

**Acceptance Criteria**:

- [ ] Login redirects to Authentik
- [ ] Successful auth creates session
- [ ] Logout clears session and redirects
- [ ] Unauthenticated users redirected to login

**Tasks**:

| Task                                         | Branch                     | Status |
| -------------------------------------------- | -------------------------- | ------ |
| Implement OIDC client with authlib           | `feat/phase-1-oidc`        | ⏸️     |
| Create auth routes (login, callback, logout) | `feat/phase-1-auth-routes` | ⏸️     |
| Add session middleware with secure cookies   | `feat/phase-1-sessions`    | ⏸️     |
| Create role extraction from group claims     | `feat/phase-1-rbac`        | ⏸️     |

#### US-002: Entity Dashboard

**As a** user
**I want** to see all LLC entities in a searchable list
**So that** I can quickly find entity information

**Acceptance Criteria**:

- [ ] Dashboard shows entity name, EIN (masked), formation state
- [ ] Search filters by name, EIN, address
- [ ] Sort by name, formation date, active status
- [ ] HTMX enables filtering without full page reload

**Tasks**:

| Task                                   | Branch                     | Status |
| -------------------------------------- | -------------------------- | ------ |
| Create base Jinja2 templates with HTMX | `feat/phase-1-templates`   | ⏸️     |
| Implement entity list router           | `feat/phase-1-entity-list` | ⏸️     |
| Add search/filter functionality        | `feat/phase-1-search`      | ⏸️     |
| Style with Tailwind CSS                | `feat/phase-1-styling`     | ⏸️     |

#### US-003: Entity Detail View

**As a** user
**I want** to view complete entity details
**So that** I can answer questions about specific LLCs

**Acceptance Criteria**:

- [ ] Shows all entity fields (legal name, DBAs, EIN, addresses)
- [ ] Displays owners with percentages
- [ ] Lists state registrations with renewal dates
- [ ] Shows registered agent information
- [ ] Lists bank accounts (masked by default)
- [ ] Shows tax filing due dates
- [ ] Links to documents

**Tasks**:

| Task                                        | Branch                        | Status |
| ------------------------------------------- | ----------------------------- | ------ |
| Create entity detail template               | `feat/phase-1-entity-detail`  | ⏸️     |
| Implement entity service with eager loading | `feat/phase-1-entity-service` | ⏸️     |
| Add collapsible sections for related data   | `feat/phase-1-detail-ui`      | ⏸️     |

#### US-004: Entity CRUD (Admin)

**As an** admin
**I want** to create and edit entity records
**So that** I can keep information current

**Acceptance Criteria**:

- [ ] Create entity form with validation
- [ ] Edit entity with inline HTMX updates
- [ ] Add/remove owners, registrations, bank accounts
- [ ] Soft delete entities (mark inactive)

**Tasks**:

| Task                                         | Branch                      | Status |
| -------------------------------------------- | --------------------------- | ------ |
| Create entity forms with Pydantic validation | `feat/phase-1-entity-forms` | ⏸️     |
| Implement create/update routes               | `feat/phase-1-entity-crud`  | ⏸️     |
| Add inline editing for related entities      | `feat/phase-1-inline-edit`  | ⏸️     |
| Implement admin-only route guards            | `feat/phase-1-admin-guards` | ⏸️     |

---

## Phase 2: Compliance & Notifications (Weeks 5-6)

### Phase 2 Objective

Add compliance calendar showing upcoming deadlines with Apprise notifications.

### Phase 2 Deliverables

- [ ] Compliance dashboard (90-day grouped list)
- [ ] Apprise notification integration
- [ ] Configurable notification schedules (7, 14, 30 days)
- [ ] Production Docker deployment

### Phase 2 Success Criteria

- ✅ Dashboard shows all upcoming deadlines in grouped list (RA, state, tax)
- ✅ Notifications fire via Apprise on schedule
- ✅ Users can configure notification preferences
- ✅ Docker image deploys to Portainer from ghcr.io

### Phase 2 User Stories

#### US-005: Compliance Dashboard

**As a** user **I want** to see upcoming deadlines **So that** I never miss a filing date

**Acceptance Criteria**:

- [ ] 90-day grouped list view (list MVP; calendar grid post-MVP)
- [ ] Color-coded by type (RA, state, tax) with urgency indicators
- [ ] Click deadline to view entity detail

**Tasks**:

| Task                                            | Branch                         | Status |
| ----------------------------------------------- | ------------------------------ | ------ |
| Create compliance service (aggregate deadlines) | `feat/phase-2-compliance-svc`  | ⏸️     |
| Build 90-day grouped list component             | `feat/phase-2-deadline-list`   | ⏸️     |
| Add deadline filtering and sorting              | `feat/phase-2-deadline-filter` | ⏸️     |

#### US-006: Apprise Notifications

**As a** user **I want** notifications for deadlines **So that** I'm proactively alerted

**Acceptance Criteria**:

- [ ] Configurable alerts (7, 14, 30 days before) via Apprise
- [ ] Enable/disable by type; notification log viewable

**Tasks**:

| Task                                             | Branch                     | Status |
| ------------------------------------------------ | -------------------------- | ------ |
| Implement Apprise client                         | `feat/phase-2-apprise`     | ⏸️     |
| Create notification scheduler (background task)  | `feat/phase-2-scheduler`   | ⏸️     |
| Build notification preferences UI                | `feat/phase-2-notif-prefs` | ⏸️     |
| Add notification history log                     | `feat/phase-2-notif-log`   | ⏸️     |

#### US-007: Docker Deployment

**As an** operator **I want** to deploy via Portainer **So that** the app runs in existing infrastructure

**Acceptance Criteria**:

- [ ] Dockerfile builds optimized image with health check
- [ ] GitHub Actions pushes to ghcr.io; Portainer guide documented

**Tasks**:

| Task                             | Branch                    | Status |
| -------------------------------- | ------------------------- | ------ |
| Create production Dockerfile     | `feat/phase-2-dockerfile` | ⏸️     |
| Configure GHCR publish workflow  | `feat/phase-2-ghcr`       | ⏸️     |
| Write Portainer deployment guide | `docs/portainer-deploy`   | ⏸️     |
| Add health check endpoint        | `feat/phase-2-health`     | ⏸️     |

---

## Phase 3: LLM Integration (Future)

Vector DB, PDF ingestion, LLM Q&A interface, document semantic search. *Detailed planning after Phase 2.*

---

## Data Entry Strategy

Data entry via **manual user input** with inline editing (admin role). PDF extraction planned for Phase 3.

- Fields display read-only by default; click edit icon to unlock (admin only)
- HTMX partial updates on save; all edits logged with timestamp/user

---

## Risk Register

| Risk                                  | Probability | Impact | Mitigation                          |
| ------------------------------------- | ----------- | ------ | ----------------------------------- |
| Authentik OIDC config complexity      | M           | H      | Test auth flow early in Phase 1     |
| HTMX learning curve                   | L           | M      | Use simple patterns, reference docs |
| Apprise connectivity from Docker      | M           | M      | Test network config in Phase 0      |
| PostgreSQL connection pool exhaustion | L           | H      | Set pool limits, add monitoring     |
| Manual data entry volume              | M           | L      | Prioritize critical entities first  |

## Definition of Done

A feature is complete when:

- [ ] Code reviewed and approved
- [ ] Tests written and passing (80% coverage)
- [ ] Type checking passes (BasedPyright strict)
- [ ] Linting passes (Ruff)
- [ ] Documentation updated
- [ ] Merged to main via PR

## Related Documents

- [Project Vision](./project-vision.md)
- [Technical Spec](./tech-spec.md)
- [Architecture Decisions](./adr/README.md)
