---
title: "Response-Aware Development"
schema_type: common
status: published
owner: core-maintainer
purpose: "Response-Aware Development assumption tagging guide for LLC Manager."
tags:
  - development
  - guide
  - architecture
---

RAD is a lightweight tagging practice that makes hidden assumptions visible at the point in
the code where they matter. When a buried assumption causes a production failure, the cost
is far higher than the 30 seconds it takes to mark it.

## The Four Markers

### `#CRITICAL`

Marks an assumption whose failure causes data loss, security exposure, or financial error.
These require verification before any production deployment.

```python
# #CRITICAL: EIN values are stored as strings, not integers.
# Leading zeros in EINs (e.g., 07-XXXXXXX) are silently dropped if coerced to int.
# #VERIFY: add a Pydantic validator that rejects non-string EIN fields at schema parse time.
ein: str = Field(..., pattern=r"^\d{2}-\d{7}$")
```

### `#ASSUME`

Marks a reasonable inference that has not been confirmed by testing or documentation.
Use this when you made a choice based on expected behavior rather than verified behavior.

```python
# #ASSUME: Authentik returns group membership in the `groups` claim of the ID token.
# This assumption has not been validated against the live Authentik instance.
# #VERIFY: log the decoded token payload during first SSO login and confirm claim name.
groups = token_claims.get("groups", [])
```

### `#EDGE`

Marks a known boundary condition that the current code does not fully handle. Use this
when you know the edge case exists but chose to defer it.

```python
# #EDGE: ownership percentages across all owners of a single entity may not sum to 100%.
# The model allows partial or over-allocated ownership without raising a validation error.
# #VERIFY: add a check constraint in the migration or a pre-save validator on Owner.
ownership_percentage: Decimal = Field(..., ge=Decimal("0"), le=Decimal("100"))
```

### `#VERIFY`

Pairs with any of the three markers above to describe exactly how the assumption should
be confirmed. Always write a `#VERIFY` line that a developer can act on independently,
without context from the original author.

```python
# #ASSUME: Apprise notification endpoint is reachable from within the Docker network.
# #VERIFY: from inside a running container, run:
#   curl -sf http://apprise:8000/notify/llc-manager || echo "unreachable"
# and confirm exit code 0 before enabling deadline alerts in production.
apprise_url: str = settings.apprise_endpoint
```

## Mandatory Categories for LLC Manager

Tag every assumption that falls into one of these categories, without exception:

| Category | Why it matters |
|----------|----------------|
| **Timing dependencies** | Compliance deadlines and notification schedules drive the core value of the application. A miscalculated deadline or a silently skipped notification is a business failure. |
| **External resources** | Authentik SSO, Apprise, Portainer, Traefik, and PostgreSQL are all external to the application container. Each can be absent, misconfigured, or rate-limited at runtime. |
| **Data integrity** | Entity relationships, soft-delete state, and Alembic migration ordering all carry implicit assumptions. Violated integrity constraints produce corrupt data that is expensive to remediate. |
| **Payment/financial** | EIN strings, ownership percentages, and tax filing dates are financial identifiers. Precision errors, truncation, and timezone offsets in these fields carry legal and financial risk. |

## Verification Workflow

1. During development, add `#CRITICAL`, `#ASSUME`, or `#EDGE` inline at the assumption site.
   Always add a paired `#VERIFY` line on the next line.

2. Before merging a feature branch, search for unresolved markers:

   ```bash
   grep -rn "#CRITICAL\|#ASSUME\|#EDGE" src/ tests/ --include="*.py"
   ```

3. For each result, either:
   - Run the verification described in the `#VERIFY` comment and replace the marker with a
     dated confirmation comment: `# VERIFIED 2026-05-08: groups claim confirmed in token payload`
   - Or convert it to a tracked issue and add the issue number inline:
     `# #ASSUME [LLC-42]: Apprise endpoint assumed reachable; ticket open for integration test`

4. `#CRITICAL` markers block merges. A PR that introduces a new `#CRITICAL` marker without
   a corresponding `#VERIFY` resolution or issue reference will not be approved.

5. `#ASSUME` and `#EDGE` markers are acceptable in merged code when paired with an open
   issue reference. Review all open markers quarterly and close or escalate them.

## Related Resources

- Global RAD standard: `~/.claude/CLAUDE.md` (Response-Aware Development section)
- Project CLAUDE.md: mandatory categories are listed in the RAD section
- Alembic migrations: `src/llc_manager/db/` (data integrity markers live here)
- Owner model: `src/llc_manager/models/owner.py` (financial marker site)
