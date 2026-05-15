# Security Findings — OWASP Top 10 (2021) Audit

**Audit date:** 2026-05-15
**Branch:** `claude/security-audit-access-control-Hq80G`
**Scope:** Backend (`src/llc_manager/`), frontend (`frontend/src/`), CI/CD (`.github/workflows/`).
**Methodology:** Manual code review against OWASP Top 10 (2021) categories listed in the audit request, plus GitHub Actions supply-chain hardening per OpenSSF Scorecard guidance.

---

## Executive summary

The backend has well-built defense-in-depth middleware (security headers, rate limiting, SSRF prevention) and uses parameterized SQLAlchemy ORM queries throughout — A03 is clean. **However, the application has no authentication or authorization layer.** Every entity endpoint (`GET/POST/PATCH/DELETE /api/v1/entities[/{id}]`) is publicly accessible to anyone who can reach the API. There is no `User` model, no `owner_id`/`tenant_id` foreign key on `Entity`, and no row-level filtering by ownership. This collapses A01 (Broken Access Control) and A07 (Authentication Failures) into a single architectural gap that must be closed before this service touches production data containing real EINs, registered-agent details, or compliance dates.

| OWASP | Category                       | Status   | Severity   |
| :---: | :----------------------------- | :------- | :--------- |
| A01   | Broken Access Control          | **FAIL** | CRITICAL   |
| A02   | Cryptographic Failures         | PARTIAL  | HIGH       |
| A03   | Injection                      | PASS     | —          |
| A05   | Security Misconfiguration      | PARTIAL  | MEDIUM     |
| A07   | Identification & Auth Failures | **FAIL** | CRITICAL   |
| —     | GitHub Actions hardening       | PARTIAL  | MEDIUM     |

Tractable fixes have been applied in this PR (CORS tightening, secret-key validation, `Cache-Control` header for API responses, GitHub Actions pinning + permissions). The architectural fixes (Authentik integration, `owner_id` migration, per-endpoint authorization) are documented below as remediation tasks; they cannot responsibly land in a single audit PR.

---

## A01 — Broken Access Control  ❌ CRITICAL

### Finding A01-1: No authentication on any data endpoint

**Location:** `src/llc_manager/api/v1/endpoints/entities.py:26-227`

All five entity endpoints accept anonymous requests:

```python
@router.get("", response_model=EntityListResponse)
async def list_entities(db: DBSession, page: int = ..., search: str | None = ..., ...):
    query = select(Entity).where(Entity.deleted_at.is_(None))
    # No filter by user/owner. Returns every entity in the database.
```

Any caller can:
- List every LLC in the database, including legal name, EIN, formation state, and notes.
- Read full entity records by UUID (`GET /api/v1/entities/{id}`).
- Create entities (`POST`), modify any entity (`PATCH`), and soft-delete any entity (`DELETE`).

There is no `User` model in `src/llc_manager/models/`, no `owner_id` column on `Entity`, no FastAPI authentication dependency wired into any router, and no middleware that rejects unauthenticated requests.

**Impact:** Anyone who can reach the API (over a misconfigured ingress, an exposed dev port, an internal pivot, or a leaked URL) can exfiltrate every customer's EIN and entity registration data, and can tamper with compliance records. EINs alone are PII under several state breach-notification laws.

**Remediation (planned via Authentik):**

The deployment plan is to front the API with a self-hosted [Authentik](https://goauthentik.io/) instance acting as an OIDC provider. The integration sequence:

1. **Authentik side**
   - Create an OIDC provider for the LLC Manager API with audience `llc-manager-api`.
   - Publish JWKS at `https://<authentik>/application/o/llc-manager-api/jwks/`.
   - Issue access tokens with claims: `sub` (stable user ID), `email`, `groups`.

2. **Backend side** (this repo, follow-up PR)
   - Add a `users` table keyed by Authentik `sub` (stable subject identifier), with `email`, `display_name`, `created_at` columns.
   - Add an `owner_user_id` (UUID, FK → `users.id`, NOT NULL) column to `entities`. Backfill is out of scope because no production data exists yet.
   - Add a `core/auth.py` module that:
     - Caches Authentik JWKS (refresh on `kid` miss, TTL 10 min).
     - Validates the `Authorization: Bearer <jwt>` header: signature, `iss`, `aud`, `exp`, `nbf`.
     - Resolves the `sub` claim to a `User` row, lazily creating it on first sight.
     - Exposes `CurrentUser = Annotated[User, Depends(get_current_user)]`.
   - Update every entity endpoint to take `CurrentUser` and `WHERE owner_user_id = current_user.id` on every query.
   - Reject any `PATCH`/`DELETE` that targets an entity not owned by the caller with `404` (not `403` — avoid confirming the resource exists).

3. **Frontend side** (`frontend/`, follow-up PR)
   - Replace the `localStorage` token pattern (see A02-2) with the OIDC authorization-code + PKCE flow against Authentik.
   - Store the access token in memory only; rely on Authentik's session cookie for refresh.

**This PR does not implement the integration.** Configuration placeholders for Authentik (issuer URL, JWKS URL, audience) are added to `core/config.py` so deployment can wire them in advance; they default to `None` and have no runtime effect until the auth dependency is added.

### Finding A01-2: Soft-delete bypass on `EIN` uniqueness check

**Location:** `src/llc_manager/api/v1/endpoints/entities.py:101-107` and `:178-187`

The duplicate-EIN check (`select(Entity).where(Entity.ein == entity_in.ein)`) does **not** exclude soft-deleted rows (`deleted_at IS NULL`). A soft-deleted entity that previously held an EIN will block a legitimate new entity from being created with that EIN. Conversely, this also means that listing/reading endpoints filter `deleted_at IS NULL` while writing endpoints do not, an inconsistency that can leak the existence of soft-deleted records via `409 Conflict`.

**Severity:** LOW (information disclosure of soft-deleted records).
**Remediation:** Add `, Entity.deleted_at.is_(None)` to both EIN-uniqueness queries. Defer until A01-1 is fixed (uniqueness is naturally scoped to owner once `owner_user_id` exists; whether EIN should be globally unique or per-owner unique is a product decision).

---

## A02 — Cryptographic Failures  ⚠️ PARTIAL

### Finding A02-1: Default `SECRET_KEY` placeholder shipped in package

**Location:** `src/llc_manager/core/config.py:18`, `:68-96`

`SECRET_KEY` defaults to the string `change-me-in-production`. There is a `model_validator` (`_reject_default_secret_key_outside_dev`) that blocks startup when the placeholder is detected outside `development`/`local`/`test`, which is a good safeguard. Two gaps remain:

- The validator only rejects the literal placeholder. Any other short, weak, or guessable string passes (e.g. `LLC_MANAGER_SECRET_KEY=secret` would start cleanly in production).
- No minimum length is enforced.

**Fix applied in this PR:** Added a length check (`>= 32` characters, recommend 64+) that runs in the same validator chain. The placeholder check still runs first.

### Finding A02-2: Auth token stored in `localStorage`

**Location:** `frontend/src/hooks/useApi.ts:41-47`

```ts
const token = localStorage.getItem('auth_token')
if (token) { config.headers.Authorization = `Bearer ${token}` }
```

`localStorage` is accessible to any JavaScript executing in the page. Despite the strict CSP middleware (`script-src 'self'`), an XSS or a compromised npm dependency in the frontend bundle would have full access to the bearer token, which is then long-lived because there is no expiry handling on the client.

**Severity:** HIGH once auth is wired up. Currently moot (no auth exists), but the code is in place and will be inherited by the Authentik integration.

**Remediation (follow-up PR alongside A01 fix):**
- Switch to OIDC authorization-code + PKCE against Authentik.
- Hold the access token in a React `useRef`/context, never `localStorage`.
- Use Authentik's HTTP-only session cookie (with `SameSite=Lax`, `Secure`) for refresh; the SPA never reads the cookie directly.
- Add a `Cache-Control: no-store` header on API responses (this PR — see A05-2) so the browser does not cache JSON containing entity details.

### Finding A02-3: Sensitive entity fields stored in plaintext

**Location:** `src/llc_manager/models/registered_agent.py`, `src/llc_manager/models/state_registration.py`, `src/llc_manager/models/entity.py`

The DB stores plaintext: registered agent contact info (name, phone, email, address, account number), EIN, state file numbers. The schema does not use PostgreSQL `pgcrypto` or application-level encryption. There is no field-level encryption helper in `src/llc_manager/utils/`.

**Severity:** MEDIUM. Defense in depth — full-database encryption at rest (PostgreSQL TDE, or volume-level encryption in the deployment environment) covers most of the threat model. Application-level encryption protects against a compromised DB user reading the table directly, and against accidental leakage via `pg_dump` artifacts or replication targets.

**Remediation (follow-up):**
- Decide threat model: at-rest disk encryption only, or application-level field encryption for the most sensitive columns (registered-agent `account_number`, `phone`, `email`).
- If field encryption is chosen: use `cryptography.fernet` with a key sourced from Infisical (already integrated per `.infisical.json`); add an `EncryptedString` SQLAlchemy column type; migrate existing columns. Out of scope for this PR.

---

## A03 — Injection  ✅ PASS

All database access uses SQLAlchemy 2.0 Core/ORM with parameter binding:

- `src/llc_manager/api/v1/endpoints/entities.py:47-72`: `select(Entity).where(Entity.legal_name.ilike(search_filter))` — `ilike` value is a bound parameter, not interpolated SQL. The `f"%{search}%"` string-builds the *value* to bind, not the SQL text, so `%` and `_` wildcards are user-controllable but the query structure is not.
- `src/llc_manager/api/v1/endpoints/entities.py:101-228`: All `select(Entity).where(...)` calls use ORM expressions; UUIDs are coerced via FastAPI path parameter typing.
- `src/llc_manager/api/health.py:108`: The only `text()` call is `text("SELECT 1")` — a constant, no interpolation.

No raw SQL, no f-string SQL, no `executemany` against user input. Pydantic `EntityCreate`/`EntityUpdate` schemas (`src/llc_manager/schemas/entity.py`) apply length and pattern constraints (e.g. `ein` matches `^\d{2}-\d{7}$|^$`), reducing the wildcard injection surface as well.

**Note:** The wildcard semantics of `ilike` are user-controllable. A search of `%` returns everything; a search of `a%b` matches anything starting with `a` and containing `b`. This is intended behavior for a search box and is safe — but is worth noting if the search endpoint ever becomes accessible to lower-trust callers.

---

## A05 — Security Misconfiguration  ⚠️ PARTIAL

### Finding A05-1: Permissive CORS configuration

**Location:** `src/llc_manager/main.py:51-58` (before fix)

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Combined with `allow_credentials=True`, the wildcard `allow_methods` / `allow_headers` is broader than required and weakens the cross-origin contract. While Starlette's CORS middleware ignores `allow_origins=["*"]` when credentials are enabled (good), the wildcard methods/headers still authorize every CORS-preflighted method and any header, including custom headers that an attacker-controlled origin could probe with.

**Fix applied in this PR:** Restricted to the methods actually used by the API (`GET`, `POST`, `PATCH`, `DELETE`, `OPTIONS`) and the specific headers required (`Authorization`, `Content-Type`, `X-Correlation-ID`, `X-Request-ID`). Origins continue to be sourced from `settings.cors_origins` (defaults to localhost:3000/5173 — must be overridden in production via `LLC_MANAGER_CORS_ORIGINS`).

### Finding A05-2: No `Cache-Control` directive on API responses

**Location:** `src/llc_manager/middleware/security.py:46-107` (before fix)

`SecurityHeadersMiddleware` sets HSTS, CSP, `X-Frame-Options`, etc., but no `Cache-Control`. Browser/proxy caches may retain JSON responses containing EINs, addresses, and compliance dates. Combined with the `localStorage` auth pattern (A02-2), a shared workstation could leak data via the disk cache.

**Fix applied in this PR:** The middleware now emits `Cache-Control: no-store` and `Pragma: no-cache` on responses for `/api/v1/*` paths (data endpoints). Static assets and health endpoints are unaffected.

### Finding A05-3: API host binding to `0.0.0.0`

**Location:** `src/llc_manager/core/config.py:57`

Default `api_host = "0.0.0.0"`. This is correct for containerized deployment but means a developer running `uv run python -m llc_manager.main` on a laptop will expose the API on all interfaces (LAN-reachable). The existing inline comment notes the rationale; `bandit` is silenced via `# nosec B104`. **Acceptable** — the comment documents the intent and the deployment model is container-first. No change.

### Finding A05-4: API docs exposed at `/api/docs` and `/api/redoc`

**Location:** `src/llc_manager/main.py:46-48`

`docs_url`, `redoc_url`, `openapi_url` are unconditionally enabled. In production, Swagger UI gives an attacker a free map of every endpoint and schema. Ideally these are gated by environment.

**Severity:** LOW — common pattern, and once auth is enforced (A01) the endpoints described in the docs are no longer exploitable without a valid token. Documenting as a remediation TODO; not changed in this PR to avoid a behavior break before the planned API redesign for Authentik.

**Remediation:** wrap the docs URLs in a conditional that disables them when `ENVIRONMENT=production`, or gates them behind an Authentik-protected admin route.

### Finding A05-5: `TrustedHostMiddleware` not added in `main.py`

**Location:** `src/llc_manager/main.py:35-71`

`add_security_middleware()` in `middleware/security.py` supports `TrustedHostMiddleware` (host-header validation, A05 defense), but `create_app()` in `main.py` does not call `add_security_middleware()` — it adds the individual middlewares manually and skips `TrustedHostMiddleware` entirely. Host-header attacks (cache poisoning via `Host:` injection) are unmitigated.

**Severity:** LOW — typically mitigated at the ingress layer (nginx/Traefik/cloud LB), but defense in depth is cheap. Documenting as TODO; the fix is to add `TrustedHostMiddleware` with `allowed_hosts=settings.allowed_hosts` (a new config field) once deployment hostnames are known.

---

## A07 — Identification & Authentication Failures  ❌ CRITICAL

### Finding A07-1: No session timeout — because no sessions exist

**Location:** N/A (no auth subsystem)

The audit asks: "Verify session timeout is enforced for compliance with legal data handling best practices." There is no session subsystem to evaluate. `core/config.py:69` declares `access_token_expire_minutes: int = 30` but the value is unreferenced anywhere in the codebase.

**Remediation:** Once the Authentik integration (A01-1) lands:
- Set Authentik access-token TTL to 15 minutes (regulated-data norm; CMS/HIPAA-adjacent guidance suggests ≤20 min for compliance dashboards).
- Set Authentik refresh-token TTL to 8 hours with sliding expiry; require re-auth after 24h of inactivity.
- Reject tokens with `iat` more than 24h in the past at the FastAPI layer, even if Authentik would have accepted the refresh, to enforce the absolute session ceiling regardless of IdP misconfiguration.
- Wire `access_token_expire_minutes` (or rename to `session_max_minutes`) into the validator so the config reflects the enforced policy.

### Finding A07-2: Rate limit applies per-IP across all endpoints

**Location:** `src/llc_manager/middleware/security.py:110-242`

The in-memory rate limiter is a single bucket per source IP at 60 rpm with a 10-rps burst, applied to every endpoint. This is sensible for read endpoints but is too generous for an eventual login/token endpoint, where credential stuffing requires a much tighter limit (e.g. 5 attempts / 15 min). Also: in-memory means a multi-worker deployment (`api_workers > 1`) effectively multiplies the limit by the worker count.

**Severity:** LOW currently (no auth endpoint exists), MEDIUM once login is added.

**Remediation (follow-up):**
- When adding the Authentik token-validation endpoint: add a tighter rate limit specifically on `/auth/*`.
- For multi-worker production: switch to Redis-backed rate limiting (`fastapi-limiter` is already mentioned in the docstring) so the limit is global, not per-worker.

---

## GitHub Actions hardening

### Finding GHA-1: Two workflows pin reusable workflows to `@main` (mutable ref)

**Locations:**
- `.github/workflows/qlty.yml:18` — `ByronWilliamsCPA/.github/.github/workflows/python-qlty-coverage.yml@main`
- `.github/workflows/coverage.yml:26` — same.

Every other workflow in the repo pins to commit SHA `e8fc83c98c2971ad1ece71573d28171463e30c16` with a `# main` trailing comment. A force-push or compromised commit on the `main` branch of `ByronWilliamsCPA/.github` would silently propagate into both workflows.

**Fix applied in this PR:** Pinned both to `e8fc83c98c2971ad1ece71573d28171463e30c16` for consistency with the rest of the repo.

### Finding GHA-2: `fips-compatibility.yml` lacks `permissions:` block and `harden-runner`

**Location:** `.github/workflows/fips-compatibility.yml`

No top-level `permissions:` block — the workflow inherits the repository's default token permissions (often `contents: write` for older repos). Neither job (`fips-check`, `fips-runtime-test`) installs `step-security/harden-runner`, so there is no egress audit trail and no policy enforcement.

**Fix applied in this PR:** Added top-level `permissions: contents: read`, restated job-level permissions explicitly, and added `harden-runner@v2.19.1` (egress-policy: audit) as the first step of both jobs.

### Finding GHA-3: Caller workflows that delegate to reusable workflows have no opportunity to install `harden-runner`

**Locations:** `ci.yml`, `container-security.yml`, `docs.yml`, `mutation-testing.yml`, `publish-pypi.yml`, `python-compatibility.yml`, `qlty.yml`, `coverage.yml`, `release.yml`, `scorecard.yml`, `sbom.yml`, `security-analysis.yml`, `sonarcloud.yml`.

These are thin caller workflows whose only job is `uses: ByronWilliamsCPA/.github/...@SHA`. GitHub Actions does not allow `steps:` (and therefore no `harden-runner`) in a job that delegates to a reusable workflow — the hardening must be added inside the reusable workflow at `ByronWilliamsCPA/.github`.

**Cannot fix in this repo.**
**Remediation:** open an issue / PR against `ByronWilliamsCPA/.github` requesting that every reusable Python workflow start with `step-security/harden-runner@v2.19.1` with `egress-policy: audit`. Track in the org-level repo, not here.

### Finding GHA-4: Several workflows have top-level `permissions:` but jobs do not restate them

**Locations:** Multiple. Reusable-workflow callers in particular often lack job-level permissions blocks.

GitHub Actions inherits top-level permissions when no job-level block is present. Per-job `permissions:` is defense in depth and required by OpenSSF Scorecard's "Token-Permissions" check.

**Fix applied in this PR:** Added explicit job-level `permissions:` blocks to every job in every workflow, restating exactly what the job needs (typically `contents: read`).

### Finding GHA-5: Inline jobs in `slsa-provenance.yml` and `pr-validation.yml` already use `harden-runner` and pinned SHAs ✅

No action required. Noted for completeness — these are correctly hardened.

---

## Summary of fixes applied in this PR

| File                                                    | Change                                                                                          |
| :------------------------------------------------------ | :---------------------------------------------------------------------------------------------- |
| `SECURITY-FINDINGS.md` (new)                            | This document.                                                                                  |
| `src/llc_manager/main.py`                               | Tighten CORS: explicit method + header allowlists.                                              |
| `src/llc_manager/core/config.py`                        | Add `SECRET_KEY` minimum-length validator. Add Authentik OIDC config placeholders (no-op until wired). |
| `src/llc_manager/middleware/security.py`                | Add `Cache-Control: no-store`, `Pragma: no-cache` on `/api/v1/*` responses.                     |
| `.github/workflows/qlty.yml`                            | Pin reusable workflow `@main` → SHA. Add explicit job-level permissions.                        |
| `.github/workflows/coverage.yml`                        | Pin reusable workflow `@main` → SHA. Add explicit job-level permissions.                        |
| `.github/workflows/fips-compatibility.yml`              | Add top-level `permissions:`, job-level `permissions:`, `harden-runner` on both jobs.           |
| `.github/workflows/*.yml` (callers)                     | Add explicit job-level `permissions:` blocks where missing.                                     |

## Out-of-PR remediation tasks (track as issues)

1. **(CRITICAL)** Implement Authentik OIDC integration: `core/auth.py`, `User` model + migration, `owner_user_id` FK on `Entity`, per-endpoint `WHERE owner_user_id = current_user.id` filters, frontend OIDC + PKCE flow. Blocks production launch.
2. **(HIGH)** Replace `localStorage` token storage in `frontend/src/hooks/useApi.ts` with in-memory + HTTP-only session cookie pattern as part of (1).
3. **(MEDIUM)** Add field-level encryption for sensitive registered-agent fields, sourcing key from Infisical.
4. **(MEDIUM)** Disable `/api/docs`, `/api/redoc`, `/api/openapi.json` in production environments.
5. **(MEDIUM)** Add `TrustedHostMiddleware` in `main.py` once production hostnames are decided.
6. **(MEDIUM)** Open PR against `ByronWilliamsCPA/.github` to add `step-security/harden-runner` to every reusable Python workflow (covers GHA-3).
7. **(LOW)** Switch the in-memory rate limiter to Redis-backed (`fastapi-limiter`) once `api_workers > 1` in production.
8. **(LOW)** Add `Entity.deleted_at.is_(None)` to EIN-uniqueness checks in `entities.py:101-107` and `:178-187`.
