---
title: "Known Vulnerabilities Template"
schema_type: common
status: published
owner: core-maintainer
purpose: "Copy-paste template for a new entry in docs/known-vulnerabilities.md."
tags:
  - security
  - compliance
  - template
---

Copy the block below into `docs/known-vulnerabilities.md` under the
`## Active Entries` heading. Replace every placeholder. Keep the
`Last reassessed` field within 60 days of `Reassess by`; the OpenSSF release
gate blocks releases for any entry whose `Last reassessed` date is older than
60 days, regardless of whether a newer `Reassess by` date is set.

```markdown
### CVE-ID - Package (reassess by YYYY-MM-DD)

| Field | Value |
|-------|-------|
| **CVE** | CVE-YYYY-NNNNN |
| **GHSA** | GHSA-xxxx-xxxx-xxxx (if applicable) |
| **Package** | package-name<=version |
| **Severity** | Low / Medium / High / Critical (CVSS X.X) |
| **Status** | Accepted risk |
| **Introduced** | YYYY-MM-DD |
| **Last reassessed** | YYYY-MM-DD |
| **Reassess by** | YYYY-MM-DD (within 60 days of Last reassessed) |

**Description**: what the vulnerability is.

**Rationale for accepting**: why this is safe in our context (platform, usage
pattern, transitive-only, etc.).

**Mitigation in place**: compensating controls, if any.

**Resolution path**: what will unblock a fix (upstream patch, removal of
transitive dep, etc.).

**Tracking**: link to issue, PR, or upstream advisory.
```

## Reassessment checklist

When updating an entry's `Last reassessed` date, confirm each point below
holds before bumping the date. If any point no longer holds, revise the
rationale or retire the entry.

1. Upstream has not published a fix.
2. No viable path exists to drop the package or pin a safe version.
3. The threat model described under "Rationale for accepting" still matches
   current deployment and usage patterns.
4. Compensating controls listed under "Mitigation in place" are still
   operational.
5. `Reassess by` is no more than 60 days from today.

## Retiring an entry

When a vulnerability is fixed or the package is removed, move the entry
verbatim to the `## Archive` section in `known-vulnerabilities.md` and add a
closing line documenting the resolution date and mechanism (for example,
"Resolved 2026-07-15 by upstream fix in package-name==X.Y.Z").
