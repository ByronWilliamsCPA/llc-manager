---
title: "Template Feedback"
schema_type: common
status: published
owner: core-maintainer
purpose: "Document template issues for upstream fixes."
tags:
  - feedback
  - template
---

> **Purpose**: Document issues discovered in this project that should be addressed in the [cookiecutter-python-template](https://github.com/ByronWilliamsCPA/cookiecutter-python-template).
>
> **Generated From**: cookiecutter-python-template v0.1.0
> **Project Created**: __PROJECT_CREATION_DATE__

---

## How to Use This File

When working on this project, if you discover any issue that originates from the template itself (not project-specific), add it here with the following format:

```markdown
### [Short Title]

- **Priority**: Critical / High / Medium / Low
- **Category**: [Configuration / Documentation / Tooling / Structure / CI/CD / Security / Other]
- **Discovered**: YYYY-MM-DD

**Issue**: [Clear description of what's wrong or missing]

**Context**: [How was this discovered? What were you trying to do?]

**Suggested Fix**: [What should the template do differently?]

**Affected Files**: [List template files that need changes]
```

---

## Feedback Items

<!-- Add your feedback below this line -->

### Missing authentication / authorization scaffolding for tenant-isolated CRUD

- **Priority**: High
- **Category**: Security
- **Discovered**: 2026-05-15

**Issue**: The template ships CRUD endpoints (e.g. `Entity` in this project) and
SQLAlchemy models that use `AuditMixin`, but there is no user model, no
authentication middleware, and no ownership column (`user_id` / `tenant_id`) on
the resource tables. As a result, any caller can read, update, or soft-delete
any row -- there is no way to enforce "user A cannot access user B's
entities".

**Context**: Discovered while writing pytest coverage for the entity CRUD
routes. Tests under `tests/integration/test_entities_api.py::TestEntityOwnershipIsolation`
document the gap by asserting current (unauthenticated) behavior and pinning
the absence of an owner column, so a future auth layer will cause those
assertions to flip explicitly.

**Suggested Fix**: Provide an opt-in template flag (or example module) that
adds:

- A `User` model and JWT/session-based auth dependency
- A `tenant_id` or `owner_user_id` column on resource tables via a mixin
- A FastAPI dependency that filters all CRUD queries by the authenticated
  caller's identity, with 403/404 responses for cross-tenant access

**Affected Files**:

- `src/{{ project_slug }}/api/v1/endpoints/*.py` (add ownership filter)
- `src/{{ project_slug }}/models/*.py` (add owner FK mixin)
- `src/{{ project_slug }}/db/base.py` (new `OwnedMixin`)
- New: `src/{{ project_slug }}/api/auth.py`

---

## Submitting Feedback

Once you've collected feedback, you can:

1. **Create an issue** in the [cookiecutter-python-template repository](https://github.com/ByronWilliamsCPA/cookiecutter-python-template/issues)
2. **Submit a PR** if you have fixes for the template
3. **Share this file** with the template maintainers

When submitting, reference this project as the source of the feedback.
