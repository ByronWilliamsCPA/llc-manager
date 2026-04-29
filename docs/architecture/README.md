---
title: "Architecture Documentation"
schema_type: common
status: published
owner: core-maintainer
purpose: "Index of architecture documentation and ADR locations for this project."
tags:
  - architecture
  - adr
---

This directory is the canonical location for architecture documentation in this project.

## Architecture Decision Records (ADRs)

ADRs for this project are maintained at [`docs/planning/adr/`](../planning/adr/).

Each ADR follows the standard format: title, status, context, decision, and consequences.

## Why docs/planning/adr/?

This project was generated from a cookiecutter template that placed planning artifacts,
including ADRs, under `docs/planning/`. ADRs were authored there before this
`docs/architecture/` directory was established as the standard location.

Files have not been moved to avoid breaking existing links and references. New ADRs
may be placed in either location; prefer `docs/planning/adr/` to keep them alongside
the related planning documents until a consolidation decision is made.
