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

### React Scaffold Conflicts with HTMX/Jinja2 Architecture Decision

- **Priority**: High
- **Category**: Structure / Tooling
- **Discovered**: 2026-05-05

**Issue**: The template unconditionally generates a React 19 + TypeScript + Vite frontend scaffold
under `frontend/`. When the project's architecture decision (ADR-001) selects HTMX + Jinja2 instead
of React, the generated scaffold creates a contradiction: `CLAUDE.md`, `docker-compose.yml`, and
the project overview all reference React, but the ADR and actual design intent use server-side
rendering. The React scaffold had to be fully removed (`rm -rf frontend/`) and multiple generated
files updated to remove React-specific references (docker-compose frontend service, CORS origins,
npm commands in CLAUDE.md).

**Context**: Discovered during Phase 0 gate review. The phase reviewer flagged that the project's
`CLAUDE.md` described "React 19 + TypeScript + Vite" while `ADR-001` (accepted 2026-01-18) had
explicitly rejected React/Vue SPAs in favor of FastAPI + HTMX/Jinja2. Root cause: the template
generates the React scaffold regardless of the cookiecutter frontend selection variable, so the
generated file state and the ADR were out of sync from day one.

**Suggested Fix**: Add a `frontend_framework` cookiecutter variable with options `react`, `htmx`,
and `none`. When `htmx` is selected: (1) skip generating `frontend/`; (2) generate
`src/{{ project_slug }}/templates/base.html` with HTMX CDN, Alpine.js CDN, and Tailwind link;
(3) generate `src/{{ project_slug }}/static/css/input.css` with Tailwind v4 directives;
(4) generate `scripts/tailwind-watch.sh` for the standalone CLI download/watch pattern;
(5) update `CLAUDE.md` to show `HTMX + Jinja2 + Tailwind CSS` in the frontend line;
(6) exclude the npm commands section from `CLAUDE.md`; (7) set CORS origins to only the API
port in `docker-compose.yml`.

**Affected Files**:

- `{{cookiecutter.project_slug}}/frontend/` (entire directory)
- `{{cookiecutter.project_slug}}/docker-compose.yml`
- `{{cookiecutter.project_slug}}/CLAUDE.md`
- `{{cookiecutter.project_slug}}/pyproject.toml` (jinja2 dependency missing from api extras)

---

## Submitting Feedback

Once you've collected feedback, you can:

1. **Create an issue** in the [cookiecutter-python-template repository](https://github.com/ByronWilliamsCPA/cookiecutter-python-template/issues)
2. **Submit a PR** if you have fixes for the template
3. **Share this file** with the template maintainers

When submitting, reference this project as the source of the feedback.
