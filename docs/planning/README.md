---
title: "Project Planning Documents"
schema_type: planning
status: published
owner: core-maintainer
purpose: "Index of project planning documentation."
tags:
  - planning
  - documentation
component: Context
source: "Project initialization"
---

This directory contains the essential planning documents for LLC Manager.

## Quick Start

Planning documents have been generated and are ready for use during development.

Review the key documents:

- [PROJECT-PLAN.md](./PROJECT-PLAN.md) - Synthesized project plan with git branches
- [project-vision.md](./project-vision.md) - Project vision and scope
- [tech-spec.md](./tech-spec.md) - Technical specification
- [roadmap.md](./roadmap.md) - Development roadmap
- [adr/](./adr/) - Architecture decision records

## Documents

| Document                                        | Purpose                  | Status    |
| ----------------------------------------------- | ------------------------ | --------- |
| [PROJECT-PLAN.md](./PROJECT-PLAN.md)            | Synthesized project plan | Generated |
| [project-vision.md](./project-vision.md)        | What & Why               | Generated |
| [tech-spec.md](./tech-spec.md)                  | How to build             | Generated |
| [roadmap.md](./roadmap.md)                      | Implementation plan      | Generated |
| [adr/](./adr/)                                  | Architecture decisions   | Generated |

## Using Documents During Development

### Starting a Session

```text
Load context from:
- project-vision.md sections 2-3
- adr/adr-001-*.md
- tech-spec.md section [relevant section]

Then implement [feature].
```

### Validating Code

```text
Review this code against:
- tech-spec.md section 6 (security)
- adr/adr-002-*.md (relevant decision)

Flag any violations.
```

### Updating Documents

Update documents when:

- **Roadmap**: After completing tasks
- **ADR**: When making architectural decisions
- **Tech Spec**: When architecture changes
- **PVS**: When scope changes

## Document Relationships

```text
┌─────────────────────────────┐
│   Project Vision & Scope    │  ← WHAT & WHY
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  Architecture Decisions     │  ← KEY CHOICES
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  Technical Specification    │  ← HOW
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  Development Roadmap        │  ← WHEN
└─────────────────────────────┘
```

## CI/CD Integration Notes

Planning documents are **intentionally excluded** from strict validation checks:

- **Front Matter Validation**: Planning docs are excluded from strict YAML front matter requirements
- **MkDocs Validation**: Link checking is relaxed for planning directory
- **Pre-commit Hooks**: Planning docs use simplified validation rules

This allows you to:

1. Update planning documents as the project evolves
2. Commit changes without CI failures
3. Focus on content rather than strict formatting
