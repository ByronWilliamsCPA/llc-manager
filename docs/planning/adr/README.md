---
title: "Architecture Decision Records"
schema_type: planning
status: published
owner: core-maintainer
purpose: "Index and documentation for Architecture Decision Records."
tags:
  - planning
  - architecture
  - decisions
---

This directory contains Architecture Decision Records (ADRs) for LLC Manager.

## What Are ADRs?

ADRs document significant architectural decisions along with their context and consequences. They help:

- Prevent architectural drift during AI-assisted development
- Provide rationale for technical choices
- Enable future developers to understand why decisions were made
- Maintain consistency across coding sessions

## ADR Index

| ADR                                        | Title                               | Status    | Date       |
| ------------------------------------------ | ----------------------------------- | --------- | ---------- |
| [ADR-001](adr-001-initial-architecture.md) | FastAPI Monolith with HTMX Frontend | Published | 2026-01-18 |

## Creating ADRs

When making a new architectural decision:

1. Copy the ADR template from [adr-template.md](adr-template.md)
2. Name the new file: `adr-NNN-[decision-slug].md` (use next available number)
3. Fill in all sections with project-specific information
4. Update the ADR index table above

## Naming Convention

ADRs follow this naming pattern:

```text
adr-NNN-short-description.md

Examples:
- adr-001-database-choice.md
- adr-002-auth-strategy.md
- adr-003-api-design.md
```

## When to Create an ADR

Create an ADR when:

- Choosing technology stack or framework
- Deciding on architectural patterns
- Selecting third-party services or libraries
- Making security or performance trade-offs
- Any decision that would be expensive to reverse

## ADR Lifecycle

```text
Proposed → Published → [Deprecated | Superseded]
```

- **Proposed**: Under discussion
- **Published**: Decision made and in use
- **Deprecated**: No longer relevant
- **Superseded**: Replaced by another ADR

## Template Reference

See [adr-template.md](adr-template.md) for the full template structure with all required sections.
