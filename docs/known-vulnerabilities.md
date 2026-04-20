---
title: "Known Vulnerabilities"
schema_type: common
status: published
owner: core-maintainer
purpose: "Log of accepted unfixed CVEs with 60-day reassessment commitment per global CLAUDE.md policy."
tags:
  - security
  - compliance
---

Every `pip-audit` or `safety` finding that cannot be immediately resolved must
be recorded here with a mandatory 60-day reassessment. The OpenSSF release
gate blocks releases for any entry older than 60 days regardless of reassessment
status (see global `~/.claude/CLAUDE.md` section on unfixed CVEs).

## Format

```markdown
### CVE-ID - Package (reassessment date YYYY-MM-DD)

| Field | Value |
|-------|-------|
| **CVE** | CVE-YYYY-NNNNN |
| **Package** | package-name<=version |
| **Severity** | Low / Medium / High / Critical (CVSS X.X) |
| **Status** | Accepted risk |
| **Introduced** | YYYY-MM-DD |
| **Reassess by** | YYYY-MM-DD (within 60 days) |

**Description**: what the vulnerability is.

**Rationale for accepting**: why this is safe in our context (platform, usage pattern, transitive-only, etc).

**Mitigation in place**: compensating controls, if any.

**Resolution path**: what will unblock a fix (upstream patch, removal of transitive dep, etc).

**Tracking**: link to issue or PR.
```

---

## Active Entries

### CVE-2025-53000 - nbconvert (reassess by 2026-06-19)

| Field | Value |
|-------|-------|
| **CVE** | CVE-2025-53000 |
| **GHSA** | GHSA-xm59-rqc7-hhvf |
| **Package** | nbconvert<=7.16.6 (transitive dep of `jupyter`) |
| **Severity** | High (CVSS 8.5) |
| **Status** | Accepted risk |
| **Introduced** | 2026-01-18 |
| **Reassess by** | 2026-06-19 (within 60 days of 2026-04-20 consolidation) |

**Description**: Uncontrolled search-path vulnerability on Windows allowing
code execution via a malicious `inkscape.bat` file when converting notebooks
with SVG to PDF.

**Rationale for accepting**: Vulnerability is Windows-specific. Project
development and CI run on Linux; no production code path touches nbconvert.
The package is pulled in transitively by `jupyter`, which is only used for
local notebook exploration, not runtime.

**Mitigation in place**:

- CI runs exclusively on Linux runners.
- Production Docker image uses the Python 3.12 slim base (Linux), so the
  vulnerable Windows path is not reachable.
- Dependabot and `pip-audit` monitor for an upstream fix.

**Resolution path**: await upstream fix or drop the `jupyter` dev dependency
if no fix lands before the reassessment date.

**Tracking**: [SECURITY.md](../SECURITY.md#cve-2025-53000-nbconvert---accepted-risk)
contains the original full risk assessment.

---

## Archive

No resolved entries yet.
