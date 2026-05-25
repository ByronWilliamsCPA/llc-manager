---
title: "OpenSSF Best Practices Badge: Pre-fill Report"
schema_type: common
status: draft
owner: core-maintainer
purpose: "Pre-filled per-criterion justifications and bulk submission URL for the OpenSSF Best Practices Badge (Passing level) application. Generated 2026-05-24 from the repo-compliance audit."
tags:
  - compliance
  - security
---

**Repository**: <https://github.com/ByronWilliamsCPA/llc-manager>
**Target level**: Passing

---

## How to file the badge application

1. Visit <https://bestpractices.coreinfrastructure.org/en/projects/new>.
2. Sign in with GitHub (OAuth -- you must do this manually).
3. Enter the repo URL: `https://github.com/ByronWilliamsCPA/llc-manager`
4. Use the criterion justifications below when filling out the form.

**Bulk pre-fill URL** (paste into browser after OAuth login):

```text
https://bestpractices.coreinfrastructure.org/en/projects/new?
  project[repo]=https://github.com/ByronWilliamsCPA/llc-manager
  &project[name]=llc-manager
  &project[description]=FastAPI+application+for+managing+LLC+entities%2C+compliance+dates%2C+and+ownership+structures.
```

> Note: the bulk API does not accept per-criterion answers via query string at Passing level.
> Use the justifications below to fill each criterion manually. Most are one-click "Met".

---

## Per-Criterion Justifications (Passing Level)

### Basics

| Criterion | Status | Justification |
|-----------|--------|---------------|
| `basic_project_website` | Met | README.md and GitHub repo page serve as project website. |
| `basic_project_website_https` | Met | GitHub serves all pages over HTTPS. |
| `repo_public` | Met | <https://github.com/ByronWilliamsCPA/llc-manager> is public. |
| `repo_track` | Met | Git history tracks all changes. |
| `repo_interim` | Met | Commits and CHANGELOG document interim changes. |
| `repo_distributed` | Met | Git is a distributed VCS. |
| `version_unique` | Met | SemVer tags on every release (semantic-release enforced). |
| `version_semver` | Met | `pyproject.toml` version + git tags follow SemVer. |
| `version_tags` | Met | Releases tagged in GitHub Releases. |
| `description_good` | Met | README.md describes what the software does and why. |
| `interact` | Met | GitHub Issues enabled for bug reports and feature requests. |
| `contribution` | Met | `CONTRIBUTING.md` present with contribution workflow. |
| `contribution_requirements` | Met | CONTRIBUTING.md documents code quality, testing, and commit standards. |

### Change control

| Criterion | Status | Justification |
|-----------|--------|---------------|
| `report_tracker` | Met | GitHub Issues used as the public bug tracker. |
| `report_process` | Met | CONTRIBUTING.md describes how to file issues and PRs. |
| `report_responses` | Met | Maintainer responds to issues; policy documented in CONTRIBUTING.md. |
| `enhancement_responses` | Met | Enhancement requests handled via GitHub Issues and PRs. |
| `report_archive` | Met | GitHub Issues archive is persistent and publicly visible. |
| `vulnerability_report_process` | Met | SECURITY.md describes the private reporting process. |
| `vulnerability_report_private` | **NEEDS ACTION** | Enable GitHub Private Vulnerability Reporting at <https://github.com/ByronWilliamsCPA/llc-manager/settings/security_analysis>. Already documented in SECURITY.md as the mechanism; toggle must be enabled. |
| `vulnerability_report_response` | Met | SECURITY.md commits to 14-day acknowledgement (48-hour target). |

### Quality

| Criterion | Status | Justification |
|-----------|--------|---------------|
| `build` | Met | `uv sync --all-extras` builds the project from source. |
| `build_common_tools` | Met | Uses UV (pip-compatible), standard Python packaging. |
| `build_floss_tools` | Met | UV, Ruff, pytest are all FLOSS tools. |
| `test` | Met | pytest suite in `tests/` with 80% line coverage requirement. |
| `test_invocation` | Met | `uv run pytest` is documented in CLAUDE.md and README. |
| `test_most` | Met | CI runs full test suite on every push and PR. |
| `test_continuous_integration` | Met | `.github/workflows/ci.yml` runs on push and pull_request. |
| `test_policy` | Met | CLAUDE.md mandates tests for new features before merge. |
| `tests_are_added` | Met | Pre-commit and CI block PRs that drop coverage. |
| `tests_documented_added` | Met | CONTRIBUTING.md and CLAUDE.md require tests for new code. |
| `warnings` | Met | Ruff and BasedPyright run with strict settings; Bandit for security. |
| `warnings_fixed` | Met | CI gates block merges if linting or type checks fail. |
| `warnings_strict` | Met | Ruff `select = ["ALL"]` equivalent; BasedPyright strict mode. |

### Security

| Criterion | Status | Justification |
|-----------|--------|---------------|
| `know_secure_design` | **ATTEST** | Self-attestation: primary developer has training in secure software design (FIPS compliance, OWASP tooling, RAD tagging for security-sensitive paths). Check "Met" on the form. |
| `know_common_errors` | **ATTEST** | Self-attestation: primary developer is familiar with OWASP Top 10, CWE categories covered by Bandit, and SQL injection / SSRF / secrets exposure patterns. Check "Met" on the form. |
| `crypto_published` | Met | Only uses standard library and well-known packages (cryptography, bcrypt). No custom crypto. |
| `crypto_call` | Met | TLS handled by deployment infrastructure (Uvicorn + reverse proxy). No in-app crypto primitives. |
| `crypto_oss` | Met | All crypto components are open-source (Python stdlib, cryptography package). |
| `crypto_keylength` | Met | FIPS compatibility workflow (`fips-compatibility.yml`) enforces key-length minimums. |
| `crypto_working` | Met | No deprecated algorithms (MD5, SHA-1 for security) detected by FIPS workflow. |
| `crypto_pfs` | Met | TLS with PFS handled at the infrastructure layer; not in-app. |
| `crypto_password_storage` | Met | No password storage in Phase 0; auth is planned via OAuth2 (Phase 1). Mark N/A or Met. |
| `crypto_random` | Met | No custom random-number generation; Python secrets module used where needed. |
| `delivery_mitm` | Met | PyPI packages installed via uv with hash verification. GitHub Actions pinned to SHA. |
| `delivery_unsigned` | Met (inverted) | Releases use SLSA Level 3 provenance (`slsa-provenance.yml`) and OIDC PyPI publishing. |
| `vulnerabilities_fixed_60_days` | Met | `docs/known-vulnerabilities.md` policy: no entry ages past 60 days. pip-audit runs in CI. |
| `vulnerabilities_critical_fixed` | Met | Critical vulnerabilities patched within 7 days per SECURITY.md policy. |
| `no_leaked_credentials` | Met | detect-secrets pre-commit hook; GitHub secret scanning enabled; `.env` in `.gitignore`. |

### Analysis

| Criterion | Status | Justification |
|-----------|--------|---------------|
| `static_analysis` | Met | Bandit (SAST), Ruff (lint), BasedPyright (type), CodeQL (`security-analysis.yml`). |
| `static_analysis_common_vulnerabilities` | Met | Bandit covers OWASP/CWE categories; CodeQL covers injection and path traversal. |
| `static_analysis_fixed` | Met | CI gates block merges when Bandit or CodeQL finds issues. |
| `static_analysis_often` | Met | Static analysis runs on every push and PR in CI. |
| `dynamic_analysis` | Met (partial) | pytest integration tests exercise live FastAPI app. |
| `dynamic_analysis_unsafe` | N/A | Project does not use memory-unsafe languages. |
| `dynamic_analysis_enable_assertions` | Met | pytest runs with assertions enabled (default Python behavior). |
| `dynamic_analysis_string_format` | Met | Ruff checks f-string and format-string safety. |

### Documentation

| Criterion | Status | Justification |
|-----------|--------|---------------|
| `documentation_basics` | Met | README.md covers installation, configuration, and usage. |
| `documentation_interface` | **NEEDS ACTION** | No published API reference yet. Either: (a) add mkdocs + mkdocstrings and publish via `docs.yml`, or (b) select N/A on the form with justification: "Phase 0 has no stable public API; internal FastAPI auto-docs at /docs serve developer consumers." |
| `documentation_current` | Met | README and CLAUDE.md are updated with each feature phase. |
| `documentation_howto` | Met | README.md includes setup and usage instructions. |
| `documentation_roadmap` | Met | `docs/planning/roadmap.md` documents the phased implementation plan. |
| `documentation_architecture` | Met | `docs/planning/tech-spec.md` and `docs/planning/adr/` document architecture decisions. |

### Other

| Criterion | Status | Justification |
|-----------|--------|---------------|
| `sites_https` | Met | GitHub, PyPI, and all external links use HTTPS. |
| `discussion` | Met | GitHub Issues and PRs serve as the discussion forum. |
| `english` | Met | All documentation is in English. |
| `license_location` | Met | `LICENSE` file at repo root (MIT). |
| `floss_license` | Met | MIT license is FLOSS. |
| `floss_license_osi` | Met | MIT is OSI-approved. |
| `changelog_type` | Met | CHANGELOG.md follows Keep-a-Changelog format. |
| `user_visible_field` | Met | All user-facing changes documented in CHANGELOG.md. |

---

## Action Items Before Submitting

1. Enable GitHub Private Vulnerability Reporting:
   <https://github.com/ByronWilliamsCPA/llc-manager/settings/security_analysis>
2. Decide on `documentation_interface`: publish API docs via mkdocs, or select N/A on the form.
3. On the bestpractices.dev form, manually check "Met" for `know_secure_design` and `know_common_errors` (these are self-attestation only; no file change required).
4. After submitting, add the badge URL to README.md.

---

## Badge Application Status

- [ ] OAuth login at bestpractices.coreinfrastructure.org
- [ ] Form submitted
- [ ] Badge URL added to README.md
- [ ] Badge image added to README.md header
