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
> **Project Created**: 2026-01-19

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

### pr-validation.yml Missing `labeled` / `unlabeled` Triggers Breaks Changelog Enforcement

- **Priority**: High
- **Category**: CI/CD
- **Discovered**: 2026-05-25

**Issue**: The generated `.github/workflows/pr-validation.yml` includes a Changelog Check
job that uses `dangoslen/changelog-enforcer` with
`skipLabels: skip-changelog,dependencies,documentation`. However, the workflow only fires
on `types: [opened, synchronize, reopened]`. The changelog-enforcer action reads labels
from `github.event.pull_request.labels` (the frozen event payload), so labels added to a
PR *after* it opens are invisible to the action. `gh run rerun` also does not refresh the
event payload, so the Changelog Check stays red even after the user adds the documented
`dependencies` skip label. Every chore(deps), docs, or trivial PR that shouldn't need a
CHANGELOG entry gets stuck on this check until contributors learn the "push an empty
commit to refresh the event payload" workaround.

**Context**: Discovered during a `/pr-fix` workflow on PR #45 (a Renovate-config tweak).
The PR was correctly labeled `dependencies` (in the skipLabels list), but the Changelog
Check kept failing on re-runs because the original `pull_request: opened` event was fired
before the label existed. The user confirmed "the same two checks keep failing on our
PRs", indicating this is a recurring fleet-wide problem, not project-specific.

**Suggested Fix**: Update the template's `.github/workflows/pr-validation.yml` to add
`labeled, unlabeled` to the `pull_request.types` list:

```yaml
on:
  pull_request:
    types: [opened, synchronize, reopened, labeled, unlabeled]
```

This makes label additions / removals trigger a fresh workflow run with a current event
payload, so the changelog-enforcer can see the new label set. Add a brief inline comment
above the `types:` line explaining why `labeled` / `unlabeled` are present so future
contributors do not remove them during cleanup passes.

**Affected Files**:

- `{{cookiecutter.project_slug}}/.github/workflows/pr-validation.yml`

---

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

### `__PROJECT_CREATION_DATE__` placeholder not substituted at generation

- **Priority**: Low
- **Category**: Tooling
- **Discovered**: 2026-05-08

**Issue**: The "Project Created" field in this file was rendered with an
unsubstituted `__PROJECT_CREATION_DATE__` placeholder instead of the actual
project creation date. It had to be filled in manually (`2026-01-19`).

**Context**: Found during the 2026-05-08 standards-alignment compliance audit
while reviewing generated template artifacts.

**Suggested Fix**: Resolve `__PROJECT_CREATION_DATE__` at cookiecutter
generation time (e.g., via a `pre_gen_project` hook that injects the current
date) so the value is populated automatically for new projects.

**Affected Files**: `docs/template_feedback.md` (template source)

---

### Template-shipped markdown files fail the template's own markdownlint hook

- **Priority**: Medium
- **Category**: Documentation
- **Discovered**: 2026-11-06

**Issue**: Eight markdown files that ship with the template fail the
`markdownlint` pre-commit hook that the same template configures
(`.markdownlint.json` with `"default": true`). 68 violations were present in
the generated project's initial commit (`e445770`), outside `docs/` and
`.claude/`: `.github/workflows/README.md` (30: 14 MD022, 11 MD032, 2 MD031,
2 MD040, 1 MD003), `CONFIG_TEMPLATES_SUMMARY.md` (20: 9 MD022, 7 MD032,
4 MD031), `CONTRIBUTING.md` (5: 2 MD034, 2 MD040, 1 MD031),
`scripts/README.md` (3: 2 MD032, 1 MD031), and the `.standards/` files
`CLAUDE.baseline.md`, `README.baseline.md`, `README.md` and
`template_feedback.baseline.md` (10: 6 MD032, 2 MD031, 1 MD036, 1 MD040).
The recurring causes are missing blank lines around headings, lists and
fences, fenced blocks without a language (ASCII diagrams and directory trees
need `text`), bare email addresses, and a `---` directly under a text line
that parses as a setext heading.

**Context**: Found while running `pre-commit run markdownlint --all-files`,
which reported 494 errors on main. Provenance was checked: all eight files
exist under `{{cookiecutter.project_slug}}/` in the template at the pinned
commit (`53a8c49`, from `.cruft.json`), and each was committed in the initial
"Initial commit from cookiecutter template" commit with the violations
already present (re-linting that commit's versions gives the same rule
classes). `CONFIG_TEMPLATES_SUMMARY.md` and `CONTRIBUTING.md` were edited
later by compliance commits, but the violation classes predate those edits.
The remaining ~426 errors under `docs/` and `.claude/` were not analyzed for
template origin and are not attributed to the template here.

**Suggested Fix**: Run `markdownlint --fix` over the template's markdown
sources and fix the rest by hand (fence languages, bare emails, the setext
heading), then add a template CI check that renders a project and runs the
markdownlint hook on it so shipped files cannot regress. The `.standards/`
baseline files are cruft-managed, so fixing them in the template is the only
way to stop the violations returning on each `cruft update`.

**Affected Files**: `.github/workflows/README.md`,
`CONFIG_TEMPLATES_SUMMARY.md`, `CONTRIBUTING.md`, `scripts/README.md`,
`.standards/CLAUDE.baseline.md`, `.standards/README.baseline.md`,
`.standards/README.md`, `.standards/template_feedback.baseline.md` (all under
`{{cookiecutter.project_slug}}/` in the template)

### Template ships a plain-text `.trivyignore` that the org container-security workflow rejects

- **Priority**: Medium
- **Category**: CI/CD
- **Discovered**: 2026-11-06

**Issue**: The template ships suppressions as a plain-text `.trivyignore` (and
lists it in `REUSE.toml` and the `container-security.yml` path filters). Newer
`python-container-security.yml` in `ByronWilliamsCPA/.github` defaults
`enforce-ignore-expiry: true` and `allow-legacy-trivyignore: false`. Its
"Suppression Revisit Dates" job fails when a plain-text `.trivyignore` exists,
because that format cannot carry an expiry. The checker also requires each entry
to have a `statement` and an `expired_at` that is in the future and within 90
days. Trivy itself does not auto-detect the YAML variant, so the workflow passes
`.trivyignore.yaml` explicitly.

**Context**: Renovate PR #99 (org reusable-workflow SHA bump to `b7c661e`)
failed the "Suppression Revisit Dates" job. Resolved by converting to
`.trivyignore.yaml` with `expired_at` dates instead of opting out.

**Suggested Fix**: Ship `.trivyignore.yaml` (a `vulnerabilities:` list with `id`,
`statement`, `expired_at` as YYYY-MM-DD) instead of `.trivyignore`. Update the
`REUSE.toml` annotation and the `container-security.yml` `paths:` filters to the
new name, and note in `docs/known-vulnerabilities.md` that `expired_at` must
equal each entry's "Reassess by" date and stay within 90 days.

**Affected Files**: `.trivyignore` (replace with `.trivyignore.yaml`),
`REUSE.toml`, `.github/workflows/container-security.yml`,
`docs/known-vulnerabilities.md` (all under `{{cookiecutter.project_slug}}/`)

---

### pr-validation.yml Concurrency Group Breaks the Merge Queue

- **Priority**: High
- **Category**: CI/CD
- **Discovered**: 2026-11-06

**Issue**: The template's `pr-validation.yml` sets `concurrency.group` to
`pr-validation-${{ github.event.pull_request.number }}` with
`cancel-in-progress: true` while also triggering on `merge_group`. For a
`merge_group` event `github.event.pull_request.number` is empty, so every merge
queue run resolves to the same group, `pr-validation-`. When a second pull
request enters the queue, its run cancels the first entry's in-flight PR
Validation run, and the queue ejects the first entry with reason
`failed_checks` even though nothing failed.

**Context**: Observed on this repository when #110 entered the queue while #102
was still being validated (PR Validation run 42261190597 and the `pr-110`
group): #102 was ejected from the queue with `failed_checks` after its run was
cancelled by the newer entry.

**Suggested Fix**: Key the group on something unique per event, with the PR
number first and the ref as fallback:
`pr-validation-${{ github.event.pull_request.number || github.ref }}`.
`github.ref` is unique per merge group (`refs/heads/gh-readonly-queue/...`),
and `cancel-in-progress` keeps its meaning for `pull_request` events. Audit
every template workflow that triggers on `merge_group` for a concurrency group
built from `github.event.pull_request.number` or `github.head_ref` alone; the
other workflows here already use the `|| github.ref` fallback.

**Affected Files**: `.github/workflows/pr-validation.yml` (under
`{{cookiecutter.project_slug}}/` in the template)

---

### Compose Forwards No Application Secrets; Roadmap and Plan Numbering Disagree

- **Priority**: Medium
- **Category**: Configuration
- **Discovered**: 2026-11-07

**Issue**: Two gaps surfaced while documenting the web sign-in rollout. First,
the template's `docker-compose.yml` forwards only logging and database
settings to the app container, so an app secret such as a session signing key
or API key set in `.env` never reaches the container; a stack that relies on
compose interpolation alone starts without it. Second, the generated
`docs/planning/roadmap.md` milestone numbering (M1 database, M2 Authentik)
differs from the one the synthesized `PROJECT-PLAN.md` produces (M0.5 data
import, M1 Authentik), so the two documents disagree about what a milestone
number means.

**Context**: Found while adding the Authentik setup guide and aligning the
roadmap with the project plan.

**Suggested Fix**: Have the compose template list pass-through (value-less)
entries for every setting the app validates at startup, and have the plan
synthesizer rewrite the roadmap milestone table when it renumbers milestones,
or generate one from the other.

**Resolution (this repo)**: The compose gap is fixed here. `docker-compose.yml`
now passes `LLC_MANAGER_SECRET_KEY` and `LLC_MANAGER_API_KEY` through as
value-less entries, and `docker-compose.prod.yml` requires both with
`${VAR:?message}` and sets `LLC_MANAGER_ENVIRONMENT: production`;
`tests/unit/test_compose_files.py` pins this. The template should adopt the
same entries. The roadmap numbering mismatch is still open.

**Affected Files**: `docker-compose.yml`, `docker-compose.prod.yml`,
`docs/planning/roadmap.md`, `docs/planning/PROJECT-PLAN.md`

---

## Submitting Feedback

Once you've collected feedback, you can:

1. **Create an issue** in the [cookiecutter-python-template repository](https://github.com/ByronWilliamsCPA/cookiecutter-python-template/issues)
2. **Submit a PR** if you have fixes for the template
3. **Share this file** with the template maintainers

When submitting, reference this project as the source of the feedback.
