# ADR-001: Initial Architecture - FastAPI Monolith with HTMX Frontend

> **Status**: Accepted
> **Date**: 2026-01-18
> **Supersedes**: None

## TL;DR

We will use a FastAPI monolith with HTMX/Jinja2 templating for the frontend because it provides the simplest deployment model (single container), excellent Python ecosystem integration, and sufficient capability for our small user base without JavaScript build complexity.

## Context

### Problem

LLC Manager needs a web architecture that:

- Displays entity data from PostgreSQL in a searchable, filterable dashboard
- Provides CRUD operations with role-based access control
- Integrates with Authentik OIDC for authentication
- Deploys as a single Docker container to Portainer
- Supports future Phase 2 LLM integration without major refactoring

### Constraints

- **Technical**: Must integrate with existing PostgreSQL, Authentik, and Apprise infrastructure
- **Business**: Small team, 5-15 users, minimal frontend complexity preferred
- **Operational**: Single container deployment requirement for Portainer

### Significance

This decision affects every aspect of development: codebase structure, developer experience, deployment pipeline, and future extensibility. The wrong choice could require a complete rewrite.

## Decision

**We will use FastAPI with HTMX/Jinja2 templating because it provides the best balance of simplicity, Python-native development, and future extensibility for LLM integration.**

### Rationale

- FastAPI's async support is ideal for future LLM streaming responses
- HTMX eliminates JavaScript build tooling while providing dynamic UX
- Single codebase, single container, single language (Python)
- SQLAlchemy 2.0 models already exist in the codebase
- Authentik integration well-documented for FastAPI OIDC

## Options Considered

### Option 1: FastAPI + HTMX/Jinja2 ✓

**Pros**:

- ✅ Single Python codebase, no JS build pipeline
- ✅ Native async for LLM streaming (Phase 2)
- ✅ Excellent OpenAPI documentation auto-generation
- ✅ Simple single-container deployment
- ✅ HTMX provides modern UX without SPA complexity

**Cons**:

- ❌ Less interactive than full SPA for complex UIs
- ❌ Server-side rendering adds latency vs client-side

### Option 2: FastAPI + React/Vue SPA

**Pros**:

- ✅ Rich interactive UI capabilities
- ✅ Clear API/frontend separation

**Cons**:

- ❌ Requires Node.js build tooling and expertise
- ❌ Two containers or complex build process
- ❌ Overkill for data-display dashboard

### Option 3: Django + Django Templates

**Pros**:

- ✅ Batteries-included (admin, auth, ORM)
- ✅ Mature ecosystem

**Cons**:

- ❌ ORM migration from SQLAlchemy 2.0 models
- ❌ Sync-first architecture complicates LLM streaming
- ❌ Django admin overkill for custom dashboard

## Consequences

### Positive

- ✅ **Fast development**: Single language, familiar Python patterns
- ✅ **Simple deployment**: One Docker image, no frontend build
- ✅ **LLM-ready**: Async architecture supports streaming responses
- ✅ **Low maintenance**: No npm dependencies or JavaScript security updates

### Trade-offs

- ⚠️ **Limited interactivity**: HTMX handles most cases, but complex widgets may need Alpine.js additions
- ⚠️ **Server load**: Every interaction hits the server (mitigated by small user count)

### Technical Debt

- None introduced; architecture aligns with existing codebase patterns

## Implementation

### Components Affected

1. **`src/llc_manager/api/`**: FastAPI routers for both API and HTML endpoints
2. **`src/llc_manager/templates/`**: Jinja2 templates with HTMX attributes
3. **`src/llc_manager/static/`**: CSS (Tailwind or minimal) + HTMX library
4. **`Dockerfile`**: Single-stage Python image with Uvicorn

### Testing Strategy

- Unit: 80% coverage on business logic and API endpoints
- Integration: Authentik OIDC flow, database operations
- E2E: Playwright tests for critical user flows (login, entity CRUD)

## Validation

### Success Criteria

- [ ] Dashboard loads in < 2 seconds with 25 entities
- [ ] CRUD operations work without full page reloads (HTMX)
- [ ] Single container deploys successfully to Portainer
- [ ] Authentik SSO login/logout functional

### Review Schedule

- Initial: After Phase 1 MVP completion
- Ongoing: Before Phase 2 LLM integration begins

## Related

- [Tech Spec](../tech-spec.md): Implementation details
- [Project Vision](../project-vision.md): Scope and constraints
