# ADR-002: Individual and Household Entities, Stable Seeded IDs

> **Status**: Accepted
> **Date**: 2026-10-05
> **Supersedes**: None

## TL;DR

We model people and the family as entities: a new `individual` entity type
(one per person) and a `household` entity type (one per family). Personal
accounts and personal documents attach to them, so `entity_id` is never
null anywhere in the suite. Production entities are loaded by an idempotent
seed command whose IDs are derived with UUIDv5 from a private stable key, so a
re-seed never changes an ID that other systems have stored.

## Context

### Problem

LLC Manager is the entity master for the family office suite: balances and
documents in other services carry an LLC Manager entity UUID. Until now every
entity was a legal entity (LLC, trust, corporation, and so on).

- `Document.entity_id` is required, but wills, powers of attorney, and health
  directives belong to a person, not a company. They had nowhere to attach.
- Personal accounts (IRAs, personal brokerage) need a roll-up by person.
- Joint and family-wide items need a single shared owner.
- Other services seed their own tables from these UUIDs, so the UUIDs must be
  stable across re-seeds and across rebuilds of the database.

### Constraints

- The repository is public. Real entity names, tax IDs, and external tenant
  IDs must never be committed, logged, or printed by tooling.
- `entity_type_enum` is a PostgreSQL enum that stores member names.
- Existing callers must keep working (additive change only).

## Decision

1. **Add two entity types** to `EntityType`: `individual` and `household`.
   They reuse the `entities` table; legal-entity columns (EIN, formation
   state) stay null for them.
2. **Attach personal items to entities, never to null.** A personal account or
   document uses its owner's `individual` entity; a joint or family item uses
   the `household` entity.
3. **Add external mapping fields.** `entities.xero_tenant_id` (nullable,
   unique among non-deleted rows) maps a Xero organisation to an entity;
   `bank_accounts.xero_account_id` (nullable) maps a Xero bank account. Both
   are returned by the entity API (`xero_tenant_id` on the entity, and a
   `bank_accounts` summary list carrying `xero_account_id`), and the entity
   list accepts `entity_type` and `xero_tenant_id` filters.
4. **Seed production entities from a private file.**
   `python -m llc_manager.cli.seed_entities` reads a JSON seed file named by
   `--file` or `LLC_MANAGER_ENTITY_SEED_FILE`. The file lives outside this
   repository; the command refuses a file inside the checkout unless it is
   marked `"synthetic": true` (as `data/examples/entity_seed.example.json`
   is). It prints counts and value-free problems only.
5. **Stable IDs.** Each seed entry has a private `key`. Its UUID is
   `uuid5(namespace, key)`, where `namespace` defaults to a constant in
   `llc_manager.services.entity_seed` and may be overridden per seed file. An
   entry may pin an explicit `id` instead, for entities that existed before
   the seed. The seed creates missing entities, updates only the fields the
   file names, and leaves soft-deleted entities alone.

## Consequences

### Positive

- Every balance and document has a non-null owner, including personal ones.
- Re-running the seed is safe and never changes an ID.
- Downstream services can map Xero organisations to entities through the API.
- The optional `--mapping-out` file (owner-only permissions) gives other
  seeds the key-to-UUID map without querying the database.

### Negative

- `individual` and `household` rows sit in a table whose columns are mostly
  about legal entities; many columns are simply null for them.
- PostgreSQL cannot drop enum labels. The migration's downgrade rebuilds the
  type and refuses to run while any row uses the new types.
- With the default namespace, anyone who can guess a key can compute its
  UUID. UUIDs are identifiers, not secrets, but a seed file can set a private
  `namespace` if that matters.

### Neutral

- Seeding bank accounts (and their `xero_account_id`) is not part of the seed
  yet; it can be added as a nested list per entity in a later version of the
  seed format.

## Alternatives Considered

### Alternative 1: Nullable `entity_id` for personal items

Rejected. Every consumer would need a null branch, and there would be no
roll-up by person.

### Alternative 2: A separate `people` table

Rejected for now. It doubles the foreign keys on every table that already
points at `entities` and gives no benefit the entity type does not.

### Alternative 3: Random UUIDs plus a stored key column

Workable, but IDs would then depend on database state: rebuilding the
database from the seed would produce new IDs. UUIDv5 makes the ID a pure
function of the private key.

## Implementation

- Migration `316e25bc258b`: enum labels, `xero_tenant_id` with partial unique
  index `ix_entities_xero_tenant_id_active`, `xero_account_id` with an index.
- Service: `src/llc_manager/services/entity_seed.py`.
- Command: `src/llc_manager/cli/seed_entities.py`.
- Example: `data/examples/entity_seed.example.json` (synthetic).
