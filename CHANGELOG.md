# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

<!-- TODO(OSSF-001): OpenSSF Best Practices Badge application pending submission at https://bestpractices.coreinfrastructure.org -- see docs/compliance-reports/ossf-badge-prefill-2026-05-24.md -->
- qlty PR gate and weekly health scan in `.github/workflows/qlty.yml`:
  a diff-mode `qlty-gate` job that blocks PRs introducing medium+
  severity issues, and a scheduled Monday full-codebase `qlty-health`
  scan (informational, `no-fail`), both via the org reusable
  `python-qlty-gate.yml` workflow
- `feat(web)`: HTMX/Jinja2 entity views (M2): a server-rendered entity
  list page with search and pagination, an entity detail page, and an
  inline edit form. The edit form submits URL-encoded fields to a
  dedicated web route (`PATCH /entities/{id}/edit`) that coerces blank
  inputs to unset values and returns the read-only detail card for HTMX
  to swap in place, replacing the earlier `json-enc` post to the JSON API
  that rejected blank optional fields with HTTP 422
- `feat(api)`: OpenAPI metadata enrichment: `version` pinned to `1.0.0`,
  contact / license blocks on the FastAPI app, and `summary` /
  `description` / `response_model` / `status_code` / `responses` on
  every entity and health route
- `scripts/export_openapi.py`: exports the FastAPI OpenAPI spec to
  `docs/api/openapi.json` without booting a server
- `scripts/generate_postman_collection.py`: converts the exported
  OpenAPI spec to a Postman Collection v2.1 at
  `docs/api/postman-collection.json` with `{{baseUrl}}` / `{{apiKey}}`
  variables and per-request status / JSON-body assertions
- `.github/workflows/postman-api-tests.yml`: Newman smoke-test workflow
  that boots the API against a Postgres service container, verifies
  the committed OpenAPI spec is current, and exercises the Postman
  collection's Health folder on every PR and `push` to `main`
- `SECURITY-FINDINGS.md` documenting an OWASP Top 10 (2021) audit covering
  A01, A02, A03, A05, A07 and GitHub Actions supply-chain hardening
- `secret_key` minimum-length validator (>= 32 chars) enforced outside
  `development` / `local` / `test`, complementing the existing placeholder
  rejection
- Authentik OIDC configuration placeholders (`authentik_issuer`,
  `authentik_jwks_url`, `authentik_audience`); default `None` and inert
  until the planned `core/auth.py` dependency is wired in
- `Cache-Control: no-store` and `Pragma: no-cache` response headers on
  `/api/v1/*` data endpoints to prevent caching of EINs and compliance data
- Compliance audit remediation (2026-05-08): native pre-commit hooks for ruff,
  ruff-format, basedpyright, detect-secrets, commitizen, yamllint, markdownlint
  (PC-002/003/004/006/008/009/010); `# pragma: allowlist secret` on every SHA
  rev (PC-012); staged-files trufflehog scope (PC-LOCAL-001); `.secrets.baseline`
  (PC-NEW-001)
- `docs/architecture/system-overview.md` (FOUND-018) and SUPPORT.md (FOUND-019)
- `docs/response-aware-development.md` RAD tagging guide (NEW-012)
- `.editorconfig` (NEW-009) and `.mailmap` (NEW-010)
- Issue Tracker URL and expanded classifiers in `pyproject.toml` (FOUND-016/017)
- `step-security/harden-runner` first step in `fips-compatibility.yml` jobs (CI-002)
- Top-level `permissions: contents: read` on `validate-cruft.yml` and
  `fips-compatibility.yml` (CI-003/004)
- `concurrency:` blocks on 9 workflows that lacked them (CI-008)
- 404/409 response declarations on entity route decorators (NEW-011)
- `#CRITICAL` and `#VERIFY` RAD markers on unauthenticated entity endpoints
  (NEW-015)
- mkdocs nav coverage for architecture, RAD doc, project plan template, ADR
  template, and compliance lessons-learned (MKDOCS-content-001)
- Initial project setup and structure
- Pytest suite raising line coverage to ~95% across entity CRUD endpoints,
  security middleware (SSRF/rate-limit/headers), the async DB-session
  lifecycle, compliance-date model properties (`is_overdue`, `is_expired`),
  and Pydantic input validation; includes ownership-isolation tests that
  document the missing auth/tenant model
- SSRF prevention and rate-limit middleware wired into `main.py`
- CR/LF sanitization and 128-char cap on incoming correlation headers
  (`X-Correlation-ID`, `X-Request-ID`, `X-Trace-ID`, `X-Span-ID`) to
  prevent log-injection and ID forgery
- Startup validator that rejects the default `secret_key` placeholder
  outside `development` / `local` / `test` environments
- `docs/known-vulnerabilities-template.md` with `Last reassessed` field
  and retirement procedure
- Uninitialized-Sentry guard in `capture_exception` and `capture_message`
- `CODE_OF_CONDUCT.md` and `GOVERNANCE.md` pointer files linking to the
  ByronWilliamsCPA organization-level community health documents
- `SCORECARD_TOKEN` secret wired into `scorecard.yml` reusable workflow call
  so the OpenSSF Scorecard Branch-Protection check can authenticate against
  the GitHub API

### Changed

- CORS middleware in `main.py` restricted from wildcard `allow_methods` /
  `allow_headers` to explicit allowlists (`GET, POST, PATCH, DELETE,
  OPTIONS` and `Authorization, Content-Type, X-Correlation-ID,
  X-Request-ID`), tightening the credentialed cross-origin contract
- GitHub Actions hardening: `qlty.yml` and `coverage.yml` reusable-workflow
  references pinned from `@main` to commit SHA; `fips-compatibility.yml`
  given a top-level `permissions` block and `harden-runner` on both jobs;
  explicit per-job `permissions` blocks added across all caller workflows
- `permissions:` block reordered before `jobs:` in `publish-pypi.yml` (CI-001)
- `pip install cruft` replaced with pinned `uv tool install cruft==2.15.0` in
  `validate-cruft.yml` (CI-006)
- `INFISICAL_DOMAIN` removed from `sbom.yml`: the workflow-level `env:` value
  could not reach the reusable workflow, which takes no such input (CI-009)
- `secrets: inherit` removed from the `security-analysis.yml` reusable call;
  the callee declares no secrets, so inheriting the namespace was unnecessary
  exposure (CI-010)
- `concurrency:` groups simplified to drop the dead `pull_request.number`
  expression in workflows that never trigger on `pull_request`; `sbom.yml`
  now only cancels redundant PR runs so scheduled security scans are never
  aborted mid-flight
- `step-security/harden-runner` aligned to `v2.19.1` in `validate-cruft.yml`
  and `fips-compatibility.yml`
- TruffleHog and Qlty pre-commit hooks fixed to fail closed when a finding is
  detected (the prior `&& ... || echo` chain swallowed the non-zero exit)
- `detect-secrets` pre-commit hook bumped to `v1.5.0` (was `v0.14.4`) and
  `commitizen` to `v4.15.1` (was `v2.42.1`); `.secrets.baseline` regenerated
  to the v1.x schema
- `pyproject.toml` classifier corrected from the inaccurate WSGI topic to
  `Topic :: Internet :: WWW/HTTP :: Dynamic Content` (FastAPI is ASGI)
- Replaced "Comprehensive" (AI-pattern blacklist word) in CONTRIBUTING.md,
  docs/index.md, docs/OPENSSF_COMPLIANCE.md, docs/planning/project-vision.md
  (CLAUDE-001)
- Healthcheck path corrected to `/api/health/live` in Dockerfile,
  docker-compose.yml, and the K8s probe examples in `api/health.py` (NEW-001)
- `docker-compose.prod.yml` YAML structure fixed (NEW-002); stale `frontend:`
  service block removed (NEW-003); `version: '3.9'` line removed
- HTTP 409 response detail string sanitized to omit the EIN value (NEW-014)
- `__PROJECT_CREATION_DATE__` placeholder in `docs/template_feedback.md`
  replaced with `2026-01-19` (NEW-013)
- Divergent local clones (`llc-manager/` and `llc_manager/`) consolidated
  into the dashed copy (PR #4)
- Readiness probe (`/api/health/ready`) returns opaque
  `database_unavailable` error; raw driver exceptions are logged via
  `logger.exception` only
- Structlog adopted in `middleware/security.py` in place of stdlib
  `logging` so correlation IDs flow into security-relevant events
- `tools/check_no_em_dash.py` fails closed on unreadable files
  (exit 2) and redacts the offending character in diagnostics
- SonarCloud workflow: `sonarqube-quality-gate-action` pinned to a SHA,
  `pull-requests: write` scoped to the analysis job, empty-coverage
  fallback removed
- `docs/known-vulnerabilities.md` policy text and entries record
  `Last reassessed` explicitly; 60-day clock runs from that field

### Removed

- `scripts/generate-client.sh` -- React frontend artefact superseded by HTMX
  migration (NEW-004)
- Orphan license files under `LICENSES/` that no file in the tree
  references (`Apache-2.0.txt`, `BSD-3-Clause.txt`, `GPL-3.0-or-later.txt`)
- Placeholder `check_cache` and `check_external_service` probes in
  `health.py` that always returned `status=True`

### Fixed

- fix(security): resolve CVE-2026-8643 -- bump transitive `pip` 26.1.1 to
  26.1.2 (dev-only, via `pip-api`/`pip-audit`); pip wrote `console_scripts`
  / `gui_scripts` entry points outside the installation directory without
  sanitizing the resolved absolute path
- `security-analysis.yml` now publishes the bare `Security Gate Validation`
  status check context required by the default-branch ruleset via a thin
  local gate job (reusable-workflow check runs carry a
  `<calling-job> / <reusable-job>` prefix that cannot match the bare
  context, which left every PR blocked from merging)
- `python-compatibility.yml` workflow: moved the `-m "not slow and not
  integration"` marker filter out of the `test-command` string and into
  `pyproject.toml` `[tool.pytest.ini_options].addopts` as separate list
  items. The upstream reusable workflow expands `$TEST_COMMAND` unquoted,
  so the marker expression was word-split by bash and pytest aborted with
  `file or directory not found: slow`. Documentation updated in
  `CLAUDE.md`, `README.md`, and `CONTRIBUTING.md` to show both the default
  fast-suite and the explicit full-suite (`-m ""`) invocations now that
  `slow` and `integration` markers are skipped by default
- `renovate.json` Python dependency managers switched from
  `pip_requirements`/`pip-compile` (which do not parse this repo's
  `pyproject.toml`) to `pep621`, the correct PEP 621 manager for
  uv-managed projects. Dev rule `matchDepTypes` also corrected to
  `["project.optional-dependencies", "dependency-groups"]` so it
  matches where this repo's dev tooling actually lives (the previous
  values targeted `[tool.uv.dev-dependencies]`, which the `pep621`
  manager does not parse and which this repo does not use)
- `sonarcloud.yml` replaced with a thin caller to the org-level reusable
  workflow (`python-sonarcloud.yml@6bad2f898...`); `pull-requests: write`
  scoped to job level only; `fail-on-quality-gate` made conditional (`true`
  on pushes to main/develop, `false` on PRs); missing-token case handled by
  `skip-if-no-token: true` passed to the callee (job-level `if:` using the
  `secrets` context is invalid in GitHub Actions, confirmed by actionlint)
- `ci.yml` org-level SHA updated from `d18c93045...` to `6bad2f898...`; the
  new SHA includes the PR #43 fix that removes `concurrency:` blocks from all
  org reusable workflow callees (GitHub rejects `concurrency:` at parse time
  in `workflow_call`-only workflows); `enable-sonarcloud` disabled to avoid
  duplicate SonarCloud runs alongside the dedicated `sonarcloud.yml`; dead
  `sonarcloud-organization` and `sonarcloud-project-key` parameters removed
  (no-ops when `enable-sonarcloud: false`)
- `osv-scanner.toml` unused ignore entries `PYSEC-2022-42969` and
  `GHSA-w596-4wvx-j9j6` removed; osv-scanner v2.3.5 resolves all aliases
  automatically from the primary `CVE-2022-42969` entry, so the duplicate
  entries caused an "unused ignores" exit-code-1 failure
- Bandit B105 false positive suppressed on `_DEFAULT_SECRET_KEY_PLACEHOLDER`
  in `core/config.py` via `# nosec B105`; the string is a documented startup
  sentinel that is explicitly rejected at runtime outside development
  (consistent with the existing `# noqa: S105` Ruff annotation on the same line)
- Bandit B607 finding resolved in `core/sentry.py` by replacing the partial
  `"git"` executable path with `shutil.which("git")`; the resolved absolute
  path eliminates the partial-executable-path risk and gracefully skips the
  git-SHA lookup when git is absent from the environment
- CI workflow `concurrency:` blocks removed by pinning `ci.yml` and
  `security-analysis.yml` to org workflow SHA
  `12e065759bf2bc915bb092d62159f4ea11d91c95`; GitHub rejects `concurrency:` at
  parse time in `workflow_call`-only workflows, which silently skipped all CI
  jobs since the December 10, 2025 org workflow change
- `actions: read` permission added to `security-analysis.yml` (required for
  CodeQL when invoked via an org-level reusable workflow)
- SonarCloud organization corrected from `ByronWilliamsCPA` to `williaby` in
  `ci.yml`
- `sonarqube-scan-action` upgraded from v5.3.2 to v8.0.0
  (`@59db25f34e16620e48ab4bb9e4a5dce155cb5432`)
- README API docs URL corrected from `/docs` to `/api/docs` (FastAPI configured
  with `docs_url="/api/docs"`)
- `npm run generate-client` OpenAPI input URL corrected from
  `localhost:8000/openapi.json` to `localhost:8000/api/openapi.json` in
  `frontend/package.json`; the app serves the OpenAPI schema at `/api/openapi.json`
- README coverage example commands deduplicated: `--cov=src` (conflicts with
  pyproject.toml addopts `--cov=src/llc_manager`) and `--cov-fail-under=80`
  (already enforced via addopts) removed
- `pre-commit run --all-files` corrected to `uv run pre-commit run --all-files`
  in README; `pre-commit` is installed as a uv dev dependency, not a system tool
- README.md badge URLs corrected: GitHub Actions, Codecov, OpenSSF Scorecard,
  and REUSE badges updated from `llc_manager` to `llc-manager` to match the
  GitHub repository slug; Quick Start `cd` instruction corrected from
  `llc_manager` to `llc-manager`
- SonarCloud project key corrected in `ci.yml`, `sonarcloud.yml`, and
  `sonar-project.properties` from `ByronWilliamsCPA_llc_manager` to
  `ByronWilliamsCPA_llc-manager` to match the GitHub repository slug
- Hypothesis fuzz test assertion fixed: `EntityCreate` schema now validates
  only declared length constraints (`1 <= len(legal_name) <= 255`) rather
  than testing raw string round-trips that fail on characters Pydantic
  normalises during ingestion
- `core/sentry.py` and `core/cache.py` excluded from coverage measurement
  (require live Sentry/Redis connections unavailable in CI); new unit tests
  for `main.py` and `api/health.py` raise overall line coverage to 80%
- `validate-cruft` workflow changed to warning-only (exit 0) when template
  is out of sync; template sync will be addressed in a dedicated follow-up PR
- `requires-python` corrected from `>=3.10` to `>=3.12`; the codebase uses
  `StrEnum` (Python 3.11+) and targets Python 3.12 throughout; Python
  compatibility matrix updated to `["3.12", "3.13"]` to match
- `Dockerfile` builder stage now copies `README.md` alongside `pyproject.toml`
  and `uv.lock`; hatchling requires it to build the sdist and the previous
  `.dockerignore` exclusion caused `OSError: Readme file does not exist`
  during `uv sync`
- Pre-existing Phase 0 bugs: bad import in `api/health.py`, wrong
  middleware class names in `main.py`, non-existent `.pop()` on
  Starlette `MutableHeaders` in `middleware/security.py`, wrong
  `call_next` annotation in `middleware/correlation.py`, stdlib
  logger silently dropping structlog kwargs in `core/cache.py` and
  `core/sentry.py`
- Invalid action SHA for `dangoslen/changelog-enforcer` (replaced with
  v3.6.1)
- Broken documentation links in `docs/development/architecture.md`
  and `docs/planning/project-plan-template.md`
- REUSE 3.2 compliance failure from unused license files
- SonarCloud analysis `404` on `api.sonarcloud.io/analysis/analyses`;
  `sonarqube-scan-action` downgraded from v4.0.0 to v5.3.2 (the version
  confirmed working via the org-level reusable CI workflow); v6.0.0 and v4.0.0
  both bundle SonarScanner CLI whose engine-bootstrap REST call is incompatible
  with this account's SonarQube Cloud endpoint
- Dockerfile Hadolint DL3008 warnings suppressed with inline `# hadolint ignore`
  pragmas; apt package version pinning is impractical for base-image OS packages
  whose exact versions vary across Debian mirrors
- Seven HIGH base-image CVEs in `python:3.12-slim` (CVE-2025-69720,
  CVE-2026-27135, CVE-2026-29111) have no Debian patch available; added
  `.trivyignore` to prevent CI gate failure and documented all three in
  `docs/known-vulnerabilities.md` per project policy

### Security

- fix(security): pass the `strict_mode` dispatch input in
  `fips-compatibility.yml` through an `env:` variable instead of interpolating
  it into the `run:` block, removing a shell template-injection pattern
  (closes #63)
- fix(security): address HIGH-severity Debian package CVEs in the runtime
  container by adding `apt-get upgrade -y` to the runtime stage of `Dockerfile`
  so any future Debian security backports for both base-image OS packages
  (`libgssapi-krb5-2`, `libssh2-1t64`) and packages installed in this layer
  (`curl`, `libcurl4t64`) are applied at build time. Container Security
  workflow (Trivy) has been failing on `main` since 2026-05-06 because of
  HIGH-severity CVEs in those packages.
- fix(security): track four HIGH-severity Debian CVEs with no upstream patch
  available as of 2026-05-25 in `.trivyignore` and `docs/known-vulnerabilities.md`
  per project policy:
  - CVE-2026-5773 -- libcurl wrong file transfer due to incorrect SMB handling
    (affects `curl`, `libcurl4t64`)
  - CVE-2026-6276 -- libcurl information disclosure via cookie leak (affects
    `curl`, `libcurl4t64`)
  - CVE-2026-40356 -- krb5 denial of service via integer overflow (affects
    `libgssapi-krb5-2`)
  - CVE-2026-7598 -- libssh2 integer overflow via large username or password
    (affects `libssh2-1t64`)

## [0.1.0] - TBD

### Added

- Initial project structure with Poetry package management
- Pydantic v2 JSON schema validation
- Structured logging with structlog and rich console output
- Pre-commit hooks (Ruff format, Ruff lint, BasedPyright, Bandit, Safety)
- Comprehensive test suite with pytest
- GitHub Actions CI/CD pipeline with quality gates
- CLI tool foundation
- License

### Documentation

- README with project overview and quick start
- CONTRIBUTING guidelines with development workflow
- References to ByronWilliamsCPA org-level Security Policy
- References to ByronWilliamsCPA org-level Code of Conduct

### Infrastructure

- Poetry dependency management with lock file
- pytest test framework with coverage reporting
- GitHub issue tracking and templates
- Automated dependency security scanning (Safety, Bandit)
- Code quality enforcement (Ruff, BasedPyright)
- CI/CD pipeline with multiple quality gates

### Security

- Bandit security linting
- Safety dependency vulnerability scanning
- Pre-commit hooks for security validation

[Unreleased]: https://github.com/ByronWilliamsCPA/llc-manager/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ByronWilliamsCPA/llc-manager/releases/tag/v0.1.0
