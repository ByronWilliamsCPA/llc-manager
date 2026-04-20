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

[Unreleased]: https://github.com/ByronWilliamsCPA/llc_manager/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ByronWilliamsCPA/llc_manager/releases/tag/v0.1.0
