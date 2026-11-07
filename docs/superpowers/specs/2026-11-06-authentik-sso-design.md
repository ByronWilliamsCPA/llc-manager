---
title: "Authentik SSO Design (M1)"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Design for browser login to the LLC Manager web UI through Authentik OIDC, with roles, CSRF protection, a break-glass admin login, and a four-PR delivery order."
tags:
  - planning
  - security
  - specifications
  - decision
component: Context
source: "Brainstorming session 2026-11-06; PROJECT-PLAN.md M1 (lines 199-224); tech-spec.md auth sections"
---

> **Milestone**: M1 Authentik SSO (`PROJECT-PLAN.md` branch name `feat/phase-1-auth`)
> **Status**: design approved in conversation; written spec awaiting review
> **Next step**: implementation plan (writing-plans), then four PRs

## Problem

The web UI is open. All six routes in `src/llc_manager/web/routes.py` have no
authentication, and `PATCH /entities/{id}/edit` writes entity data (EIN, names,
ownership-related fields). `/api/v1` is already protected by `X-API-Key`
(`src/llc_manager/core/auth.py`), so the gap is the browser side only.

The plan expects Authentik OIDC login with admin and viewer roles taken from
group membership. Nothing in `src/` implements it: there is no session
middleware, no cookie handling, no OIDC client, and no CSRF protection.

## Decisions

These were made during brainstorming and are not open.

| Question | Decision | Reason |
|---|---|---|
| What does M1 protect? | Web UI login only. `/api/v1` keeps `X-API-Key`. | Closes the open-edit gap with the smallest change and matches the tech-spec. A second (bearer JWT) path is not needed by any current client. |
| Authentik state | Instance runs; the LLC Manager application, provider and groups do not exist yet. | The design ships a setup checklist and a token check for the `groups` claim. |
| Fallback when Authentik is down | Break-glass local admin password (argon2 hash), off by default. | Chosen over the "no production fallback" option so an outage does not lock the family office out. Costs a second login path, hardened below. |
| Exposure | HTTPS behind Traefik/Pangolin. | Needs a public base URL setting and trusted-proxy handling. |
| Session storage | Signed cookie with `authlib` and Starlette `SessionMiddleware`. No server-side table. | 5 to 15 users. Revocation waits for session expiry; rotating `secret_key` logs everyone out. |

## Non-goals

- Bearer-JWT validation on `/api/v1`. The unused `authentik_jwks_url` and
  `authentik_audience` settings are deleted so they do not imply it.
- Server-side sessions, instant revocation, "log out everywhere".
- Ending the Authentik session on app logout (see Logout).
- Per-entity permissions. Roles are global: admin or viewer.

## Architecture

A new package `src/llc_manager/auth/`, separate from `core/auth.py` (the
API-key code is not touched). One job per file:

| File | Responsibility |
|---|---|
| `oidc.py` | Registers the Authentik client with `authlib`: authorization code with PKCE, issuer discovery. |
| `roles.py` | Maps the `groups` claim to a role. Admin outranks viewer. No matching group means no access. |
| `session.py` | `SessionUser` (`sub`, email, name, role, expiry) read from and written to the signed cookie. |
| `csrf.py` | Per-session token and the check for state-changing web requests. |
| `dependencies.py` | `require_user`, `require_admin`, `verify_csrf`. |
| `routes.py` | `GET /auth/login`, `GET /auth/callback`, `POST /auth/logout`, `GET` and `POST /auth/local-login`. |

The session cookie is signed with the existing `secret_key` setting
(`core/config.py`, already validated to 32 characters or more outside dev).

New runtime dependencies: `authlib`, `itsdangerous`, and `argon2-cffi`
(currently only a transitive dev dependency).

## Settings

All use the `LLC_MANAGER_` prefix and live in `core/config.py`.

| Setting | Default | Notes |
|---|---|---|
| `public_base_url` | none | Required in production; must be `https://`. Redirect URIs are built from it, never from request headers. |
| `authentik_issuer` | none | Existing field, kept. Typically `https://<authentik-host>/application/o/<slug>/`. |
| `authentik_client_id` | none | New. |
| `authentik_client_secret` | none | New, `SecretStr`. |
| `authentik_groups_claim` | `groups` | Claim name holding group names. |
| `admin_group` | `llc-manager-admins` | Group name mapped to admin. |
| `viewer_group` | `llc-manager-viewers` | Group name mapped to viewer. |
| `session_max_age_seconds` | 28800 (8 hours) | Absolute lifetime; a signed cookie cannot track idle time. |
| `local_admin_enabled` | `false` | Break-glass switch. |
| `local_admin_password_hash` | none | Argon2 hash only. Never a plaintext password. |
| `trusted_proxy_ips` | none | Allow-list for forwarded headers. |
| `auth_dev_mode` | `false` | Fixed admin user, no Authentik. Refused in production. |

Removed: `authentik_jwks_url`, `authentik_audience`.

Production validation fails startup when: `auth_dev_mode` is true;
`public_base_url` is missing or not HTTPS; the OIDC settings are incomplete
and break-glass is not the only configured login; `local_admin_enabled` is
true without a hash.

## Request flow

### Gating

The web router gets `require_user` at router level, so a new route cannot be
left open by forgetting a decorator. Open paths: `/auth/*`, `/api/health/*`,
static files. `/api/v1` is unchanged.

When there is no valid session:

- A normal page request gets a 303 redirect to `/auth/login?next=<path>`.
- An HTMX request (`HX-Request: true`) gets 401 with an `HX-Redirect` header,
  so HTMX navigates instead of swapping a login page into a fragment.

`next` must be a relative path that starts with a single `/`. It is checked
before it is stored and again after the callback. Values such as `//evil.com`
or `https://evil.com` are discarded in favor of `/entities`. `#EDGE`

### Roles

- Viewer: `GET /entities`, `/entities/{id}`, `/entities/{id}/card`.
- Admin: also `GET` and `PATCH /entities/{id}/edit`. A viewer gets 403, and
  templates hide the edit controls for viewers.

### Login

1. `/auth/login` creates state, nonce and the PKCE verifier through `authlib`
   and redirects to Authentik.
2. `/auth/callback` exchanges the code and validates the ID token: issuer,
   audience equal to the client ID, nonce, expiry.
3. It reads the groups claim and maps it to a role. Both groups means admin.
   No matching group, or no claim, renders a 403 page and logs the denial.
4. On success it clears the previous session and builds a new one (prevents
   session fixation), with a new CSRF token and an expiry.
5. It redirects to the validated `next`, or `/entities`.

### Logout

`POST /auth/logout` with a CSRF token clears the app session only. The
Authentik session stays, so signing in again is immediate. Ending the
Authentik session would also sign the user out of every other application
they reach through Authentik.

## Cookie and CSRF

Cookie: name `llc_session`, `HttpOnly`, `Secure`, `SameSite=Lax`,
`max_age` from `session_max_age_seconds`. `Lax` is required because the
return from Authentik is a top-level GET that must carry the cookie.

CSRF:

- Each session holds a random token. `base.html` sets it in `hx-headers` on
  `<body>`, so every HTMX request sends `X-CSRF-Token`, including the edit
  `PATCH`.
- `verify_csrf` checks every web request that is not GET, HEAD or OPTIONS,
  plus `POST /auth/logout`, with a constant-time comparison. A mismatch is 403.
- Plain forms (logout, break-glass login) carry the token as a hidden field.
  The break-glass form page seeds a token in the session before anyone is
  logged in.

## Break-glass login

`/auth/local-login` returns 404 unless `local_admin_enabled` is true and a
hash is set. When enabled:

- One admin account; a successful login yields the admin role.
- The submitted password is checked against the argon2 hash.
- A stricter rate limit than the rest of the app, for example 5 failures per
  15 minutes per client IP. `#CRITICAL`
- Every attempt, success or failure, is logged at WARNING with the
  correlation ID.
- `/auth/login` shows an error page when Authentik is unreachable, and that
  page links to the break-glass form only if it is enabled.

## Proxy trust

Uvicorn currently runs without proxy-header flags (`Dockerfile` line 77), so
behind Traefik the app sees `http` and the proxy address for every request.
That would break the `Secure` cookie logic and make the rate limiter
(`middleware/security.py`, keyed on `request.client.host`) treat all users as
one client. The container runs uvicorn with `--proxy-headers` and an
allow-list driven by `trusted_proxy_ips`, documented next to
`public_base_url`. `#ASSUME` Traefik/Pangolin sets `X-Forwarded-For` and
`X-Forwarded-Proto`. `#VERIFY` log `request.url.scheme` and the client IP from
a real request after deploy.

## Dev mode

`auth_dev_mode` injects a fixed admin user and skips Authentik. Production
validation refuses it, and the app logs a loud warning at startup when it is
on.

## Errors

Every failure renders a plain error page with no stack trace. The cause goes
to the log with the correlation ID.

| Situation | Response |
|---|---|
| Authentik unreachable during login | 503 page, break-glass link if enabled |
| State, nonce or token validation failure | 400 page |
| No matching group | 403 page |
| Expired or missing session | Redirect to login (HTMX: `HX-Redirect`) |
| CSRF mismatch | 403 |

## Testing

Tests are written first.

- Role mapping, parametrized: admin, viewer, both, neither, missing claim,
  wrong case.
- `next` validation, CSRF, session expiry, settings validators.
- OIDC login flow with the `authlib` token exchange mocked; no network.
- Break-glass: disabled gives 404, wrong password rejected, rate limit
  applies, attempts logged.
- Route coverage: a test enumerates the web router and fails if any route is
  not gated, modeled on the existing test that checks every `/api/v1`
  operation declares the API key (`tests/unit/test_api_key_auth.py`).
- Existing web tests (`tests/unit/test_web_entities.py`) get an
  authenticated-client fixture so they keep passing. The autouse API-key
  fixture in `tests/conftest.py` does not cover web sessions.

## Authentik setup checklist

To be written as a guide in PR 4. Summary:

1. Create groups `llc-manager-admins` and `llc-manager-viewers`.
2. Create a confidential OAuth2/OpenID provider with the authorization-code
   flow and redirect URI `https://<host>/auth/callback`.
3. Create the application and restrict access to those two groups.
4. Decode a test ID token and confirm a `groups` claim with group names. If it
   is missing, add a scope mapping that returns group names. `#ASSUME`
   Authentik emits `groups` with the chosen scopes. `#VERIFY` this step; it is
   the plan's still-unchecked assumption (`PROJECT-PLAN.md` line 800).
5. Record issuer URL, client ID and client secret; set them in the
   environment.

## Documentation work

- New ADR-003 recording this decision (there is no auth ADR today).
- `.env.example` entries for the new settings (it has no auth variables now).
- Authentik outage runbook (the plan lists it as P2 and it does not exist).
- Fix stale statements: ADR-001 and ADR-002 say there is no auth;
  `docs/architecture/system-overview.md` says users are "authenticated via
  Authentik OIDC", which is not true yet; the tech-spec uses unprefixed env
  names (`AUTHENTIK_CLIENT_ID`, `SECRET_KEY`, `AUTH_DEV_MODE`) where the code
  uses `LLC_MANAGER_*`.
- Milestone numbering: `PROJECT-PLAN.md` calls Authentik SSO M1, while
  `roadmap.md` calls it M2. Proposed: align the roadmap to the plan, because
  the plan carries the git branch names.

## Delivery

Four PRs. Gating is switched on last so nobody is locked out.

1. ADR-003, settings and validators, dependencies. No behavior change.
2. OIDC login, session, roles, CSRF and dev mode. The gate exists and is
   tested but is not attached to routes.
3. Break-glass login and proxy trust.
4. Attach the gate to the web routes, update templates, add the setup guide,
   runbook and the documentation fixes.

Deployment order for PR 4: create the Authentik application and groups, set
the environment values, confirm the groups claim, then deploy. Deploying
before that leaves only dev mode and break-glass as ways in.

## Out of scope, to file separately

- CSP and CDN scripts: `middleware/security.py` sets `script-src 'self'`
  while `templates/base.html` loads HTMX and Alpine from a CDN. Either the
  policy is not applied or it breaks the UI when it is.
- `/api/docs` and `/api/openapi.json` are unauthenticated
  (`main.py` lines 76-78).
- Unrouted nav links to `/documents` and `/compliance` in `base.html`.

## Risks

| Risk | Mitigation |
|---|---|
| Group renamed in Authentik silently changes access | Group names come from settings; the setup guide records the names. |
| Cookie cannot be revoked before expiry | 8 hour lifetime; rotate `secret_key` to invalidate all sessions. |
| Break-glass becomes the weak point | Off by default, argon2, rate limit, WARNING logs. `#CRITICAL` |
| Redirect URI built from a spoofed `Host` | Always built from `public_base_url`. |
| Locked out after gating deploys | Gating ships last; break-glass ships before it; deployment order above. |
