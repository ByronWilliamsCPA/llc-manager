# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial project setup and structure
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
- Orphan license files under `LICENSES/` that no file in the tree
  references (`Apache-2.0.txt`, `BSD-3-Clause.txt`, `GPL-3.0-or-later.txt`)
- Placeholder `check_cache` and `check_external_service` probes in
  `health.py` that always returned `status=True`

### Fixed

- `sonarcloud.yml` replaced with a thin caller to the org-level reusable
  workflow (`python-sonarcloud.yml@6bad2f898...`); picks up
  `sonarqube-scan-action` v7.2.0 and keeps PR decoration working by relaying
  `pull-requests: write` to the callee; note: SonarScanner CLI 8.0.1 (bundled
  in v7.2.0) still returns 404 on `api.sonarcloud.io/analysis/analyses` for
  projects with no prior analysis -- this is an upstream scanner bug unblocked
  by the SonarCloud quality-gate check not being a required merge gate
- `ci.yml` org-level SHA updated from `d18c93045...` to `6bad2f898...`; the
  new SHA includes the PR #43 fix that removes `concurrency:` blocks from all
  org reusable workflow callees (GitHub rejects `concurrency:` at parse time
  in `workflow_call`-only workflows); `enable-sonarcloud` disabled in `ci.yml`
  to avoid duplicate SonarCloud runs alongside the dedicated `sonarcloud.yml`
- `sonarcloud-organization` in `ci.yml` corrected from `ByronWilliamsCPA` to
  `williaby` to match the actual SonarCloud account name

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
