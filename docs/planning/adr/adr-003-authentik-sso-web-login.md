# ADR-003: Authentik SSO for the Web UI, Signed-Cookie Sessions, Break-Glass Admin

> **Status**: Proposed
> **Date**: 2026-11-06
> **Supersedes**: None

## TL;DR

The browser UI signs users in through Authentik OIDC (authorization code with
PKCE). The app keeps the session in a signed cookie, takes the admin or viewer
role from Authentik group membership, protects state-changing requests with a
per-session CSRF token, and offers a hardened break-glass local admin login for
Authentik outages. `/api/v1` keeps its `X-API-Key` header; this decision does
not touch it.

## Context

### Problem

The web UI is open. Every route in `src/llc_manager/web/routes.py` answers
anonymous requests, and `PATCH /entities/{id}/edit` writes entity data. The
service API is already protected by `X-API-Key` (`src/llc_manager/core/auth.py`),
so the gap is the browser side only. ADR-001 planned Authentik OIDC for this and
nothing in `src/` implements it.

### Constraints

- 5 to 15 users, one container, no new infrastructure.
- An Authentik instance exists; the LLC Manager application, provider, and
  groups do not.
- The app is served over HTTPS behind a reverse proxy (Traefik or Pangolin).
- The repository is public: no real hostnames, client secrets, or password
  hashes are committed.

## Decision

1. **Scope.** M1 protects the web UI only. `/api/v1` keeps `X-API-Key`.
   `/api/health/*` and static files stay open. The unused bearer-JWT settings
   `authentik_jwks_url` and `authentik_audience` are removed so they do not
   imply a second API path.
2. **Protocol.** Authorization code flow with PKCE through `authlib`. Issuer
   discovery is fetched lazily on the first login. ID token checks: issuer,
   audience equal to the client ID, nonce, expiry.
3. **Sessions.** A signed cookie (`llc_session`, `HttpOnly`, `SameSite=Lax`,
   `Secure` when `public_base_url` is HTTPS) written by Starlette
   `SessionMiddleware`, signed with the existing `secret_key`. There is no
   server-side session table. The cookie is re-signed on every response, so the
   session payload carries its own absolute expiry (`session_max_age_seconds`,
   default 8 hours).
4. **Roles.** Group names come from the `groups` claim (name configurable).
   `admin_group` maps to admin, `viewer_group` to viewer; admin outranks viewer;
   no match or no claim is a 403. Role changes in Authentik take effect at the
   next sign-in.
5. **Gating.** `require_user` is attached to the web router, not to individual
   routes, so a new route cannot be left open. `require_admin` guards
   `GET` and `PATCH /entities/{id}/edit`. A page request without a session gets
   a 303 to `/auth/login?next=...`; an HTMX request gets 401 with `HX-Redirect`.
   `next` must be a relative path that starts with a single `/`.
6. **CSRF.** Each session holds a random token. `base.html` puts it in
   `hx-headers`, so every HTMX request sends `X-CSRF-Token`. `verify_csrf`
   checks every web request that is not GET, HEAD, or OPTIONS with a
   constant-time comparison. Plain forms carry a hidden `csrf_token` field.
7. **Logout.** `POST /auth/logout` clears the app session only. The Authentik
   session stays so signing in again is immediate and other applications are
   not signed out.
8. **Break-glass.** `/auth/local-login` returns 404 unless
   `local_admin_enabled` is true and an argon2 hash is set. One admin account,
   5 failures per 15 minutes per client IP, every attempt logged at WARNING
   with the correlation ID.
9. **Proxy trust.** `trusted_proxy_ips` lists the proxies whose
   `X-Forwarded-*` headers are believed. The app installs uvicorn's
   `ProxyHeadersMiddleware` as the outermost layer when the list is not empty.
   Redirect URIs are always built from `public_base_url`, never from request
   headers.
10. **Dev mode.** `auth_dev_mode` injects a fixed admin user. Startup refuses it
    outside development, local, and test environments.
11. **Rollout.** Four PRs, gating last. Settings validation that makes sign-in
    mandatory in production ships in the same PR as the gate, so earlier PRs do
    not change startup behavior for an unconfigured production environment.

## Consequences

### Positive

- The edit endpoint is no longer anonymous; roles map to group membership the
  family office already manages in Authentik.
- No new tables, services, or secrets store.
- A route enumeration test fails the build if a web route is added without the
  gate.

### Negative

- A signed cookie cannot be revoked before it expires. Rotating `secret_key`
  signs everyone out.
- The break-glass login is a second way in and the weakest link; it is off by
  default and hardened as described above.
- The login throttle is process-local. With several replicas or workers the
  effective limit is the per-process limit times the process count.
- Group renames in Authentik silently change access unless the setting is
  updated. The setup guide records the expected names.

### Neutral

- The Authentik session is not ended on logout.
- CSP and CDN script loading in `base.html` are unchanged and tracked
  separately.

### Known scanner finding

The repository's FIPS compatibility scan flags `argon2-cffi` in
`pyproject.toml`, because Argon2id is not a NIST-approved algorithm. The
decision is to keep Argon2id for the break-glass password hash: the app does not
target FIPS-enabled hosts, and the finding is informational (the FIPS job
passes). Revisit only if a deployment target requires FIPS mode, in which case
the hash would move to PBKDF2 and the settings validator would change with it.

## Alternatives Considered

### Alternative 1: Server-side sessions in PostgreSQL

Rejected for 5 to 15 users. It adds a table, expiry cleanup, and a migration
for revocation nobody has asked for.

### Alternative 2: Bearer-JWT validation on `/api/v1`

Rejected. No current client needs it, and two API auth paths double the
surface to test.

### Alternative 3: Reverse-proxy forward auth (outpost) in front of the app

Rejected for now. It removes the app's own role mapping and CSRF story and ties
local development to the proxy. It remains possible later.

### Alternative 4: No production fallback when Authentik is down

Rejected. An outage would lock the family office out. The break-glass login
costs a hardened second path.

## Implementation

- Package: `src/llc_manager/auth/` (`oidc.py`, `roles.py`, `session.py`,
  `csrf.py`, `dependencies.py`, `routes.py`, `redirects.py`, `throttle.py`,
  `templating.py`).
- Settings: `src/llc_manager/core/config.py`.
- Guide: `docs/guides/authentik-setup.md`. Runbook:
  `docs/guides/authentik-outage-runbook.md`.
- Design spec and delivery plan: `docs/superpowers/specs/2026-11-06-authentik-sso-design.md`
  and `docs/superpowers/plans/2026-11-06-authentik-sso.md`.

## Validation

- [ ] Login through Authentik returns to the requested page with a session
- [ ] A viewer cannot open or save an edit
- [ ] A forged or missing CSRF token on `PATCH` is refused
- [ ] A real request behind the proxy logs scheme `https` and the real client IP
- [ ] The break-glass login works once, from a drill, and is then disabled
