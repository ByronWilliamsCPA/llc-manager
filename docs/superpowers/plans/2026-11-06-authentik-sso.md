---
title: Authentik SSO Implementation Plan (M1)
schema_type: planning
status: draft
owner: core-maintainer
purpose: Task-by-task plan to deliver Authentik SSO for the LLC Manager web UI as four sequential pull requests, with gating switched on last.
tags: [planning, security, specifications]
component: Context
source: docs/superpowers/specs/2026-11-06-authentik-sso-design.md
---

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put the browser UI behind Authentik OIDC sign-in with admin and viewer roles, CSRF protection, and a break-glass admin login, without locking anyone out and without changing startup behavior for an unconfigured production environment until the final PR.

**Architecture:** A new `src/llc_manager/auth/` package (OIDC client, session, roles, CSRF, gates, routes, login throttle). A signed cookie holds the session; no server-side table. `/api/v1` keeps `X-API-Key`. The gate is built and tested in PR 2 and 3, and attached to the web routes only in PR 4.

**Tech Stack:** FastAPI, Starlette `SessionMiddleware`, `authlib` (Starlette client, PKCE), `joserfc` (via authlib), `itsdangerous`, `argon2-cffi`, HTMX/Jinja2, pytest.

**Authority:** `docs/superpowers/specs/2026-11-06-authentik-sso-design.md` is authoritative. Where this plan departs from it, the departure is listed in "Verified facts that differ from the spec" and is deliberate.

## Ground rules

These apply to every task. An implementer who skips them breaks the delivery contract.

1. **HARD RULE: PRs 1 to 3 must not change startup behavior for an unconfigured production environment.** A host-side watcher may auto-pull the GHCR image built on each merge to `main`. An unconfigured production container must start and serve exactly as before after PR 1, PR 2, and PR 3. The rule "production requires a working sign-in method" ships in PR 4, together with the gate. `#CRITICAL` `#VERIFY` PR 1 carries `TestUnconfiguredProductionIsUnchanged`; PR 2 and PR 3 re-run it and `tests/unit/test_auth_wiring.py`, which proves the web routes are still open.
2. **One PR, one branch, one worktree.** Each PR uses its own branch and a worktree at `.worktrees/<slug>` inside the repository. Never create worktrees elsewhere. PR N+1 branches from `origin/main` after PR N has merged.
3. **Never push, open a PR, or merge from a task.** Steps that show `git push` or `gh pr create` are marked "orchestrator". The orchestrator runs them after approval.
4. **Commits:** signed (`git commit -S`, never `--no-gpg-sign`), Conventional Commits with a lowercase subject, staging only the named paths (never `git add -A` or `git add .`), and ending with `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`.
5. **TDD:** write the failing test, run it and see it fail for the stated reason, write the minimal implementation, run it and see it pass. Fix lint findings properly; never add `noqa`, `type: ignore`, or skip markers.
6. **No em-dash characters and no emojis** in code, comments, docs, commit messages, or PR text.
7. **Test command:** the repository's default pytest options enforce coverage over the whole tree, so run focused tests with the options cleared: `uv run pytest <files> -v -o addopts=""`. Before each PR's final commit also run the full suite with the default options, `uv run pytest`.
8. **Dependencies change only through `uv`.** Edit `pyproject.toml` for the declaration, then run `uv lock`. Never edit `uv.lock` by hand.
9. **`pre-commit run --files ...`** must pass before a PR's final commit. If the `detect-secrets` hook rewrites `.secrets.baseline` (line numbers shift when an audited file changes), run `git add .secrets.baseline` and re-run the hook; include that file in the commit.
10. **Verification record.** Every code block below was run in a scratch tree against the stated base. In that run the full suite, excluding `tests/unit/test_import_excel.py` (it needs `pandas`, which the scratch environment lacked), passed with these totals: base 562, after PR 1 606, after PR 2 700, after PR 3 732, after PR 4 767. Your totals will also include the Excel import tests.

## Decisions recorded in this plan

The owner was unavailable while this plan was written. These choices were made to keep the work moving; each is reversible in review.

| Decision | Choice | Reason |
| --- | --- | --- |
| How tests fake Authentik | A fake in-memory provider (`tests/oidc_fake.py`) signs real ID tokens with `joserfc` and monkeypatches only `fetch_access_token` on the `authlib` client. Static provider metadata is passed as keyword arguments to `oauth.register`. No test touches the network. | Exercises real ID-token validation (issuer, audience, nonce, expiry, signature) with no network. |
| Unauthenticated HTMX request | 401 plus an `HX-Redirect: /auth/login?next=...` header. A page request gets 303. | `base.html` sets `hx-boost` on `<body>`, so even link navigation carries `HX-Request: true`; an XHR cannot follow a cross-origin redirect to Authentik. |
| `next` validation | Relative path, single leading `/`, no `//`, no backslash, no control characters, no scheme or host, not under `/auth`. Checked when stored and again after the callback. Invalid values become `/entities`. | Prevents open redirects. |
| Role extraction | Admin outranks viewer. No matching group, or no claim, gives a 403 page and clears the session. Matching is exact and case-sensitive. | Matches the spec; the safe default is no access. |
| Session cookie | Name `llc_session`, `HttpOnly`, `SameSite=Lax`, `max_age` 28800, `Secure` when `public_base_url` starts with `https://`. | `Lax` is required for the top-level return from Authentik. Plain-HTTP local runs and the test client still work. |
| Absolute session lifetime | The session payload stores its own `exp`. | `SessionMiddleware` re-signs the cookie on every response, so the cookie alone gives a sliding window. |
| Route scope | `/api/v1` stays on `X-API-Key`. `/api/health/*`, `/api/docs`, `/api/redoc`, `/api/openapi.json`, `/auth/*`, and `/static` stay open. | Spec: web UI only. Docs exposure is tracked separately. |
| Logout | `POST /auth/logout` with a CSRF token; clears the app session only; returns a 200 "Signed out" page. | Spec. |
| Break-glass identity | One account, subject `local-admin`, role admin, `auth_method: local`. No username setting. | Spec says one account; a username adds a guess target and nothing else. |

## Verified facts that differ from the spec

Each item was checked against the installed libraries or the repository. None changes the spec's intent.

1. **Proxy trust is done in the app, not on the uvicorn command line.** The spec says the container runs uvicorn with `--proxy-headers` and an allow-list driven by `trusted_proxy_ips`. The uvicorn CLI cannot read a pydantic setting, and uvicorn's `--proxy-headers` is already on by default with an allow-list of `127.0.0.1`. The plan keeps the `Dockerfile` `CMD` unchanged and adds uvicorn's `ProxyHeadersMiddleware` as the outermost middleware when `trusted_proxy_ips` is not empty (PR 3). An empty list adds nothing, so the PR 3 deploy changes no behavior.
2. **OIDC discovery is lazy.** With `server_metadata_url`, `authlib` fetches the discovery document on the first `authorize_redirect`, so an Authentik outage first shows up in `/auth/login`, not only in the callback. Both routes catch `httpx.HTTPError` and render the 503 page.
3. **Token validation errors are `joserfc` errors.** `authlib` 1.9 raises `joserfc.errors.JoseError` subclasses for a bad ID token, and `OAuthError` for a provider `error=` response or a state mismatch. The callback catches both, plus `httpx.HTTPError` separately.
4. **The session must be cleared only after the token exchange.** `authorize_redirect` stores state, nonce, and the PKCE verifier in `request.session`; clearing it before the exchange breaks the flow.
5. **Clearing a Starlette session emits an expired cookie, not `max-age=0`.** Tests assert on the `Set-Cookie` header (`expires=Thu, 01 Jan 1970`), because the test client's cookie jar does not drop a cookie that was set without a domain.
6. **`PROJECT-PLAN.md` line 224 is wrong.** It says "Local admin works when `AUTH_DEV_MODE=true`". The break-glass login and dev mode are different features. PR 4 corrects it.
7. **`tests/auth_helpers.py` already exists** (the API-key test constants). PR 2 extends it rather than creating it.
8. **The compose files forward no application secrets.** `docker-compose.yml` and `docker-compose.prod.yml` pass `ENVIRONMENT`, logging, and database settings but no `LLC_MANAGER_SECRET_KEY` or `LLC_MANAGER_API_KEY`, and there is no `env_file`. PR 4 adds passthroughs for the new auth settings only, using real defaults for booleans and numbers because an empty string is not a valid bool or int. How production receives the secret key is an open question (see "Open risks").
9. **Blank group names would silently match nothing useful.** `LLC_MANAGER_ADMIN_GROUP=""` is accepted by a plain `str` field. PR 1 gives the three claim and group settings `min_length=1`.
10. **The lockfile pins FastAPI 0.138.2; newer FastAPI wraps included routers in a private `_IncludedRouter` object.** The route-enumeration test in PR 4 flattens both shapes; it was run against 0.138.2 and 0.162.
11. **`detect-secrets` keeps a line-numbered baseline.** Editing `docs/planning/tech-spec.md` (PR 4) moves an audited line, so `.secrets.baseline` must be committed with it.
12. **The login throttle is per process.** `docker-compose.prod.yml` defaults to two replicas, so the effective limit is up to 5 failures per 15 minutes per replica. Recorded as an `#ASSUME` in the code and in ADR-003.
13. **There are seven page routes, not six.** `src/llc_manager/api/ui.py` holds a second page router (`GET /`, the dashboard, included before the web router so it answers `/`). The spec counts only the six routes in `web/routes.py`. PR 4 gates both routers, and the enumeration test covers every route that is not under `/api/` or `/auth/`.
14. **Browser sessions use `Secure` only for an https `public_base_url`.** The spec says the cookie is always `Secure`. Production requires https (PR 1 validator) so a deployed cookie is always `Secure`; the flag is conditional so that plain-HTTP local runs and the test client can still sign in.

## Delivery map

| PR | Branch and worktree slug | Contents | Depends on |
| --- | --- | --- | --- |
| 0 | `docs/authentik-sso-design` (this branch) | Spec (already committed as d52c806) and this plan | None |
| 1 | `feat/auth-settings`, `.worktrees/auth-settings` | ADR-003, settings and validators, runtime dependencies. No behavior change. | PR 0 not required |
| 2 | `feat/auth-oidc-session`, `.worktrees/auth-oidc-session` | `auth/` package: OIDC login, session, roles, CSRF, dev mode. Gates tested, not attached. | PR 1 merged |
| 3 | `feat/auth-break-glass`, `.worktrees/auth-break-glass` | Break-glass login, throttle, proxy trust, outage page link. | PR 2 merged |
| 4 | `feat/auth-gate-web`, `.worktrees/auth-gate-web` | Gate attached, templates, production-required validator, docs, runbook, compose and env entries. | PR 3 merged, and the deploy prerequisites below |

## Task 0: Spec and plan (PR 0)

The spec is already committed on `docs/authentik-sso-design` as `d52c806`. This plan file is added to the same branch and PR.

- [ ] **Step 1: Confirm the branch and that only the plan is new**

```bash
cd /home/byron/dev/llc-manager/.worktrees/authentik-sso-design
git branch --show-current
git status --short
```

Expected: `docs/authentik-sso-design`, and only `?? docs/superpowers/plans/2026-11-06-authentik-sso.md` (or nothing after the commit).

- [ ] **Step 2: Lint and commit the plan**

```bash
pre-commit run --files docs/superpowers/plans/2026-11-06-authentik-sso.md
git add docs/superpowers/plans/2026-11-06-authentik-sso.md
git commit -S -m "docs(auth): add Authentik SSO implementation plan" -m "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

Expected: all hooks pass; a signed commit is created.

- [ ] **Step 3: PR (orchestrator)**

```bash
git push -u origin docs/authentik-sso-design
gh pr create --title "docs(auth): add Authentik SSO design spec and implementation plan" --body-file <prepared body>
```

Not run by an implementer. depends-on: none.

## Deploy prerequisites for PR 4

PR 4 makes the application fail closed. Before PR 4 is merged (a host watcher may deploy the image built from `main`), all of these must be true:

1. The Authentik application, provider, and the two groups exist (`docs/guides/authentik-setup.md`, steps 1 to 3).
2. A test ID token shows a `groups` claim with group names (step 4). This is the plan's still-unchecked assumption (`PROJECT-PLAN.md` line 800).
3. The production environment has `LLC_MANAGER_PUBLIC_BASE_URL` (https), the three Authentik values, a 32-character-or-longer `LLC_MANAGER_SECRET_KEY`, and `LLC_MANAGER_TRUSTED_PROXY_IPS`. Optionally the break-glass hash and switch.
4. The compose files, or whatever deploys the container, forward those variables to it.

If any is missing, a container built from PR 4 refuses to start in production. That is the intended fail-closed behavior; the previous image keeps running only if the deploy tooling rolls back.

## PR 1: ADR-003, settings, runtime dependencies

Branch `feat/auth-settings`. No route, middleware, or template changes. The new settings are optional; a production container with none of them set starts exactly as it does today (ground rule 1).

### Task 1.0: Worktree for PR 1

depends-on: none

- [ ] **Step 1: Create the worktree and install dependencies**

```bash
cd /home/byron/dev/llc-manager
git fetch origin
git worktree add .worktrees/auth-settings -b feat/auth-settings origin/main
cd .worktrees/auth-settings
uv sync --all-extras
git status --short
```

Expected: the worktree is created and `git status --short` prints nothing. If the parent repository's `git status` lists `.worktrees/` as untracked, add `.worktrees/` to `.git/info/exclude` there; never stage it.

- [ ] **Step 2: Record the baseline**

```bash
uv run pytest -o addopts="" -q --ignore=tests/unit/test_import_excel.py
```

Expected: all tests pass (562 in the verification run, with the Excel import tests excluded). Write the number down; later steps compare against it.

### Task 1.1: ADR-003

depends-on: Task 1.0 [completion]

Files:

- Create: `docs/planning/adr/adr-003-authentik-sso-web-login.md`
- Modify: `docs/planning/adr/README.md`, `mkdocs.yml`

The ADR records the decision, the alternatives rejected, the consequences, and the rollout order. It is documentation only, so the check is the docs build and the markdown hooks rather than a pytest run.

- [ ] **Step 1: Write the ADR**

````markdown
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
````

- [ ] **Step 2: Add the ADR to the index and the site navigation**

In `docs/planning/adr/README.md`, replace this text:

````markdown
| [ADR-002](adr-002-individual-household-entities.md) | Individual and Household Entities, Stable Seeded IDs | Proposed  | 2026-10-05 |
````

with:

````markdown
| [ADR-002](adr-002-individual-household-entities.md) | Individual and Household Entities, Stable Seeded IDs | Proposed  | 2026-10-05 |
| [ADR-003](adr-003-authentik-sso-web-login.md)       | Authentik SSO for the Web UI                         | Proposed  | 2026-11-06 |
````

In `mkdocs.yml`, replace this text:

````yaml
          - Initial Architecture: planning/adr/adr-001-initial-architecture.md
````

with:

````yaml
          - Initial Architecture: planning/adr/adr-001-initial-architecture.md
          - Authentik SSO Web Login: planning/adr/adr-003-authentik-sso-web-login.md
````

- [ ] **Step 3: Build the docs and lint**

```bash
uv run mkdocs build --strict 2>&1 | tail -5
pre-commit run --files docs/planning/adr/adr-003-authentik-sso-web-login.md docs/planning/adr/README.md mkdocs.yml
```

Expected: the build ends with `Documentation built in ...` and no `WARNING`; every pre-commit hook passes. A `detect-secrets` rewrite of `.secrets.baseline` is not expected here.

- [ ] **Step 4: Commit**

```bash
git add docs/planning/adr/adr-003-authentik-sso-web-login.md docs/planning/adr/README.md mkdocs.yml
git commit -S -m "docs(auth): add adr-003 for authentik web sign-in" -m "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

### Task 1.2: Runtime dependencies

depends-on: Task 1.0 [completion]

Files:

- Create: `tests/unit/test_auth_packaging.py`
- Modify: `pyproject.toml`, `uv.lock` (by `uv lock` only)

The Dockerfile installs `--extra api`, so the sign-in libraries must be in that extra or the shipped image cannot import them.

- [ ] **Step 1: Write the failing test**

````python
"""The libraries browser login needs are declared for the shipped image."""

from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement

pytestmark = pytest.mark.unit

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"
AUTH_PACKAGES = {"authlib", "itsdangerous", "argon2-cffi", "httpx"}


def test_auth_packages_are_in_the_api_extra() -> None:
    """The Dockerfile installs ``--extra api``, so the packages must be there."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    api_extra = data["project"]["optional-dependencies"]["api"]
    declared = {Requirement(entry).name for entry in api_extra}
    assert declared >= AUTH_PACKAGES


@pytest.mark.parametrize(
    "module",
    [
        "authlib.integrations.starlette_client",
        "itsdangerous",
        "argon2",
        "httpx",
    ],
)
def test_auth_modules_import(module: str) -> None:
    assert importlib.import_module(module) is not None
````

- [ ] **Step 2: Run it and see it fail**

```bash
uv run pytest tests/unit/test_auth_packaging.py -v -o addopts=""
```

Expected: `test_auth_packages_are_in_the_api_extra` FAILED with `assert {...} >= {'authlib', 'itsdangerous', 'argon2-cffi', 'httpx'}` and a set of missing names. On a clean environment the import checks for `authlib` and `itsdangerous` also fail with `ModuleNotFoundError`.

- [ ] **Step 3: Declare the dependencies**

````diff
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -137,6 +137,11 @@
     "alembic>=1.12.0",  # Database migrations
     "asyncpg>=0.29.0",  # Async PostgreSQL driver
     "psycopg[binary]>=3.1.0",  # Sync PostgreSQL driver (for Alembic)
+    # Browser login (see ADR-003)
+    "authlib>=1.9",  # OIDC client: authorization code flow with PKCE
+    "itsdangerous>=2.2",  # Signs the Starlette session cookie
+    "argon2-cffi>=25.1",  # Break-glass admin password hash
+    "httpx>=0.28",  # HTTP client that authlib's Starlette integration uses
 ]
````

- [ ] **Step 4: Re-lock and install**

```bash
uv lock
uv sync --all-extras
git diff --stat -- uv.lock pyproject.toml
uv lock --check
```

Expected: `uv lock` reports added packages (`authlib`, `itsdangerous`, and `joserfc`, which `authlib` requires); `git diff --stat` lists `pyproject.toml` and `uv.lock`; `uv lock --check` prints `Resolved ... packages` and exits 0. Never edit `uv.lock` by hand.

- [ ] **Step 5: Run the test and see it pass**

```bash
uv run pytest tests/unit/test_auth_packaging.py -v -o addopts=""
```

Expected: `5 passed`. A warning from `authlib` that its `httpx` module is deprecated may print; it is harmless (see "Open risks").

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock tests/unit/test_auth_packaging.py
git commit -S -m "build(deps): declare the sign-in libraries as runtime dependencies" -m "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

### Task 1.3: Settings and validators

depends-on: Task 1.2 [completion]

Files:

- Create: `tests/unit/test_auth_settings.py`
- Modify: `src/llc_manager/core/config.py`, `tests/unit/test_security_audit_fixes.py`

The new settings, their validators, and the removal of `authentik_jwks_url` and `authentik_audience`. `TestUnconfiguredProductionIsUnchanged` is the executable form of the hard rule: production with no auth setting at all still loads.

- [ ] **Step 1: Write the failing tests**

````python
"""Settings and validators for browser login (Authentik OIDC, break-glass)."""

from __future__ import annotations

import pytest
from argon2 import PasswordHasher
from pydantic import SecretStr

from llc_manager.core.config import Settings
from llc_manager.core.exceptions import ConfigurationError

pytestmark = [pytest.mark.unit, pytest.mark.security]

AUTH_ENV_NAMES = (
    "PUBLIC_BASE_URL",
    "AUTHENTIK_ISSUER",
    "AUTHENTIK_CLIENT_ID",
    "AUTHENTIK_CLIENT_SECRET",
    "AUTHENTIK_GROUPS_CLAIM",
    "AUTHENTIK_JWKS_URL",
    "AUTHENTIK_AUDIENCE",
    "ADMIN_GROUP",
    "VIEWER_GROUP",
    "SESSION_MAX_AGE_SECONDS",
    "LOCAL_ADMIN_ENABLED",
    "LOCAL_ADMIN_PASSWORD_HASH",
    "TRUSTED_PROXY_IPS",
    "AUTH_DEV_MODE",
)

ARGON2_HASH = PasswordHasher().hash("correct horse battery staple")


@pytest.fixture(autouse=True)
def clean_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test with no auth settings in the process environment."""
    for name in AUTH_ENV_NAMES:
        monkeypatch.delenv(f"LLC_MANAGER_{name}", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("LLC_MANAGER_ENVIRONMENT", raising=False)


@pytest.fixture
def production(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the process look like a production deployment."""
    monkeypatch.setenv("LLC_MANAGER_ENVIRONMENT", "production")
    monkeypatch.setenv("LLC_MANAGER_SECRET_KEY", "s" * 40)


def _oidc_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLC_MANAGER_PUBLIC_BASE_URL", "https://llc.example.com")
    monkeypatch.setenv(
        "LLC_MANAGER_AUTHENTIK_ISSUER",
        "https://auth.example.com/application/o/llc-manager/",
    )
    monkeypatch.setenv("LLC_MANAGER_AUTHENTIK_CLIENT_ID", "llc-manager")
    monkeypatch.setenv("LLC_MANAGER_AUTHENTIK_CLIENT_SECRET", "client-secret-value")


class TestDefaults:
    def test_defaults(self) -> None:
        s = Settings(_env_file=None)
        assert s.public_base_url is None
        assert s.authentik_issuer is None
        assert s.authentik_client_id is None
        assert s.authentik_client_secret is None
        assert s.authentik_groups_claim == "groups"
        assert s.admin_group == "llc-manager-admins"
        assert s.viewer_group == "llc-manager-viewers"
        assert s.session_max_age_seconds == 28800
        assert s.local_admin_enabled is False
        assert s.local_admin_password_hash is None
        assert s.trusted_proxy_ips == []
        assert s.auth_dev_mode is False
        assert s.oidc_configured is False

    def test_removed_bearer_jwt_settings_are_gone(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_AUTHENTIK_JWKS_URL", "https://x/jwks/")
        monkeypatch.setenv("LLC_MANAGER_AUTHENTIK_AUDIENCE", "llc-manager-api")
        s = Settings(_env_file=None)
        assert not hasattr(s, "authentik_jwks_url")
        assert not hasattr(s, "authentik_audience")

    @pytest.mark.parametrize(
        "name", ["AUTHENTIK_GROUPS_CLAIM", "ADMIN_GROUP", "VIEWER_GROUP"]
    )
    def test_blank_group_settings_are_rejected(
        self, monkeypatch: pytest.MonkeyPatch, name: str
    ) -> None:
        # An empty group name must never silently match a user's group list.
        monkeypatch.setenv(f"LLC_MANAGER_{name}", "")
        with pytest.raises(ValueError, match="String should have at least 1"):
            Settings(_env_file=None)

    def test_session_max_age_must_be_positive(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_SESSION_MAX_AGE_SECONDS", "0")
        with pytest.raises(ValueError, match="session_max_age_seconds"):
            Settings(_env_file=None)


class TestUnconfiguredProductionIsUnchanged:
    """PR 1 to 3 must not change startup for a production host with no auth set."""

    def test_production_without_any_auth_setting_starts(self, production: None) -> None:
        s = Settings(_env_file=None)
        assert s.oidc_configured is False
        assert s.local_admin_enabled is False
        assert s.auth_dev_mode is False


class TestOidcConsistency:
    def test_complete_oidc_settings_are_accepted(
        self, monkeypatch: pytest.MonkeyPatch, production: None
    ) -> None:
        _oidc_env(monkeypatch)
        s = Settings(_env_file=None)
        assert s.oidc_configured is True
        assert isinstance(s.authentik_client_secret, SecretStr)
        assert s.authentik_client_secret.get_secret_value() == "client-secret-value"

    @pytest.mark.parametrize(
        "missing",
        [
            "PUBLIC_BASE_URL",
            "AUTHENTIK_ISSUER",
            "AUTHENTIK_CLIENT_ID",
            "AUTHENTIK_CLIENT_SECRET",
        ],
    )
    def test_partial_oidc_settings_are_rejected(
        self, monkeypatch: pytest.MonkeyPatch, missing: str
    ) -> None:
        _oidc_env(monkeypatch)
        monkeypatch.delenv(f"LLC_MANAGER_{missing}")
        with pytest.raises(ConfigurationError, match="must all be set together"):
            Settings(_env_file=None)

    def test_blank_values_count_as_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLC_MANAGER_AUTHENTIK_ISSUER", "")
        monkeypatch.setenv("LLC_MANAGER_AUTHENTIK_CLIENT_SECRET", "  ")
        monkeypatch.setenv("LLC_MANAGER_PUBLIC_BASE_URL", "")
        s = Settings(_env_file=None)
        assert s.authentik_issuer is None
        assert s.authentik_client_secret is None
        assert s.public_base_url is None

    def test_http_issuer_is_rejected_in_production(
        self, monkeypatch: pytest.MonkeyPatch, production: None
    ) -> None:
        _oidc_env(monkeypatch)
        monkeypatch.setenv(
            "LLC_MANAGER_AUTHENTIK_ISSUER", "http://auth.example.com/application/o/x/"
        )
        with pytest.raises(ConfigurationError, match="AUTHENTIK_ISSUER"):
            Settings(_env_file=None)

    def test_http_issuer_is_allowed_in_development(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _oidc_env(monkeypatch)
        monkeypatch.setenv("LLC_MANAGER_PUBLIC_BASE_URL", "http://localhost:8000")
        monkeypatch.setenv(
            "LLC_MANAGER_AUTHENTIK_ISSUER", "http://localhost:9000/application/o/x/"
        )
        assert Settings(_env_file=None).oidc_configured is True


class TestPublicBaseUrl:
    def test_trailing_slash_is_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLC_MANAGER_PUBLIC_BASE_URL", "https://llc.example.com/")
        assert Settings(_env_file=None).public_base_url == "https://llc.example.com"

    @pytest.mark.parametrize(
        "value",
        [
            "llc.example.com",
            "ftp://llc.example.com",
            "https://llc.example.com/app",
            "https://llc.example.com/?x=1",
            "https://llc.example.com/#frag",
            "https://",
        ],
    )
    def test_non_origin_values_are_rejected(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_PUBLIC_BASE_URL", value)
        with pytest.raises(ConfigurationError, match="PUBLIC_BASE_URL"):
            Settings(_env_file=None)

    def test_http_is_rejected_in_production(
        self, monkeypatch: pytest.MonkeyPatch, production: None
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_PUBLIC_BASE_URL", "http://llc.example.com")
        with pytest.raises(ConfigurationError, match="https://"):
            Settings(_env_file=None)

    def test_http_is_allowed_in_development(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_PUBLIC_BASE_URL", "http://localhost:8000")
        assert Settings(_env_file=None).public_base_url == "http://localhost:8000"


class TestBreakGlassSettings:
    def test_enabled_without_hash_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_LOCAL_ADMIN_ENABLED", "true")
        with pytest.raises(ConfigurationError, match="LOCAL_ADMIN_PASSWORD_HASH"):
            Settings(_env_file=None)

    def test_enabled_with_argon2_hash_is_accepted(
        self, monkeypatch: pytest.MonkeyPatch, production: None
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_LOCAL_ADMIN_ENABLED", "true")
        monkeypatch.setenv("LLC_MANAGER_LOCAL_ADMIN_PASSWORD_HASH", ARGON2_HASH)
        s = Settings(_env_file=None)
        assert s.local_admin_enabled is True
        assert s.local_admin_password_hash is not None

    @pytest.mark.parametrize("value", ["hunter2", "$2b$12$abcdefghijklmnopqrstuv"])
    def test_non_argon2_value_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_LOCAL_ADMIN_PASSWORD_HASH", value)
        with pytest.raises(ConfigurationError, match="argon2"):
            Settings(_env_file=None)

    def test_hash_alone_does_not_enable_the_login(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_LOCAL_ADMIN_PASSWORD_HASH", ARGON2_HASH)
        assert Settings(_env_file=None).local_admin_enabled is False

    def test_hash_is_not_exposed_in_repr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLC_MANAGER_LOCAL_ADMIN_PASSWORD_HASH", ARGON2_HASH)
        assert ARGON2_HASH not in repr(Settings(_env_file=None))


class TestDevMode:
    def test_refused_in_production(
        self, monkeypatch: pytest.MonkeyPatch, production: None
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_AUTH_DEV_MODE", "true")
        with pytest.raises(ConfigurationError, match="AUTH_DEV_MODE"):
            Settings(_env_file=None)

    @pytest.mark.parametrize("environment", ["development", "local", "test"])
    def test_allowed_in_development_class_environments(
        self, monkeypatch: pytest.MonkeyPatch, environment: str
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_ENVIRONMENT", environment)
        monkeypatch.setenv("LLC_MANAGER_AUTH_DEV_MODE", "true")
        assert Settings(_env_file=None).auth_dev_mode is True


class TestTrustedProxyIps:
    def test_comma_separated_list_is_parsed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_TRUSTED_PROXY_IPS", "10.0.0.5, 172.18.0.0/16")
        assert Settings(_env_file=None).trusted_proxy_ips == [
            "10.0.0.5",
            "172.18.0.0/16",
        ]

    def test_blank_value_is_an_empty_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_TRUSTED_PROXY_IPS", " ")
        assert Settings(_env_file=None).trusted_proxy_ips == []

    @pytest.mark.parametrize("value", ["*", "proxy.local", "10.0.0.5,not-an-ip"])
    def test_invalid_entries_are_rejected(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_TRUSTED_PROXY_IPS", value)
        with pytest.raises(ConfigurationError, match="TRUSTED_PROXY_IPS"):
            Settings(_env_file=None)
````

Only the `TestAuthentikConfigPlaceholders` class of `tests/unit/test_security_audit_fixes.py` changes; its other classes (`TestSecretKeyMinLength`, `TestCacheControlOnApiResponses`, `TestCorsHardening`) must stay exactly as they are. Apply this diff, do not retype the file:

````diff
--- a/tests/unit/test_security_audit_fixes.py
+++ b/tests/unit/test_security_audit_fixes.py
@@ -61,23 +61,26 @@
     def test_authentik_fields_default_none(self) -> None:
         settings = Settings()
         assert settings.authentik_issuer is None
-        assert settings.authentik_jwks_url is None
-        assert settings.authentik_audience is None
+        assert settings.authentik_client_id is None
+        assert settings.authentik_client_secret is None
+        assert not hasattr(settings, "authentik_jwks_url")
+        assert not hasattr(settings, "authentik_audience")

     @pytest.mark.unit
     def test_authentik_fields_loadable_from_env(
         self, monkeypatch: pytest.MonkeyPatch
     ) -> None:
+        monkeypatch.setenv("LLC_MANAGER_PUBLIC_BASE_URL", "https://llc.example.com")
         monkeypatch.setenv("LLC_MANAGER_AUTHENTIK_ISSUER", "https://auth.example.com")
-        monkeypatch.setenv(
-            "LLC_MANAGER_AUTHENTIK_JWKS_URL",
-            "https://auth.example.com/jwks/",
-        )
-        monkeypatch.setenv("LLC_MANAGER_AUTHENTIK_AUDIENCE", "llc-manager-api")
+        monkeypatch.setenv("LLC_MANAGER_AUTHENTIK_CLIENT_ID", "llc-manager")
+        monkeypatch.setenv("LLC_MANAGER_AUTHENTIK_CLIENT_SECRET", "not-a-real-secret")
         settings = Settings()
         assert settings.authentik_issuer == "https://auth.example.com"
-        assert settings.authentik_jwks_url == "https://auth.example.com/jwks/"
-        assert settings.authentik_audience == "llc-manager-api"
+        assert settings.authentik_client_id == "llc-manager"
+        assert settings.authentik_client_secret is not None
+        assert settings.authentik_client_secret.get_secret_value() == (
+            "not-a-real-secret"
+        )


 class TestCacheControlOnApiResponses:
````

- [ ] **Step 2: Run them and see them fail**

```bash
uv run pytest tests/unit/test_auth_settings.py tests/unit/test_security_audit_fixes.py -v -o addopts=""
```

Expected: `40 failed, 8 passed`. The failures are `AttributeError` on the new fields, `DID NOT RAISE` for the validators, and `assert hasattr(...)` for the removed settings.

- [ ] **Step 3: Implement the settings**

````diff
--- a/src/llc_manager/core/config.py
+++ b/src/llc_manager/core/config.py
@@ -4,9 +4,11 @@
 Pydantic-settings handles the parsing and validation.
 """

+import ipaddress
 import os
 from pathlib import Path
-from typing import ClassVar, Literal
+from typing import Annotated, ClassVar, Literal
+from urllib.parse import urlsplit

 from pydantic import (
     AliasChoices,
@@ -17,7 +19,7 @@
     field_validator,
     model_validator,
 )
-from pydantic_settings import BaseSettings, SettingsConfigDict
+from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

 from llc_manager.core.exceptions import ConfigurationError

@@ -82,9 +84,26 @@
         cors_origins (list[str]): List of allowed CORS origins.
         secret_key (str): Secret key for signing tokens.
         access_token_expire_minutes (int): Token expiration time in minutes.
-        authentik_issuer (str | None): Authentik OIDC issuer URL.
-        authentik_jwks_url (str | None): Authentik JWKS endpoint URL.
-        authentik_audience (str | None): Authentik token audience.
+        public_base_url (str | None): Public ``https://`` origin of the app,
+            for example ``https://llc.example.com``. OIDC redirect URIs are
+            built from it, never from request headers.
+        authentik_issuer (str | None): Authentik OIDC issuer URL, typically
+            ``https://<authentik-host>/application/o/<slug>/``.
+        authentik_client_id (str | None): OAuth2 client ID of the Authentik
+            provider.
+        authentik_client_secret (SecretStr | None): OAuth2 client secret.
+        authentik_groups_claim (str): ID token claim that holds group names.
+        admin_group (str): Group name that maps to the admin role.
+        viewer_group (str): Group name that maps to the viewer role.
+        session_max_age_seconds (int): Absolute lifetime of a browser session.
+        local_admin_enabled (bool): Switch for the break-glass admin login.
+        local_admin_password_hash (SecretStr | None): Argon2 hash of the
+            break-glass password. Never a plaintext password.
+        trusted_proxy_ips (Annotated[list[str], NoDecode]): Comma-separated IP
+            addresses or CIDR networks of reverse proxies whose forwarded
+            headers are trusted.
+        auth_dev_mode (bool): Sign in as a fixed admin without Authentik.
+            Refused outside development, local, and test environments.
         api_key (SecretStr | None): Shared key that callers of ``/api/v1``
             send in the ``X-API-Key`` header. Read from
             ``LLC_MANAGER_API_KEY`` or, if that is unset,
@@ -133,14 +152,26 @@
     secret_key: str = _DEFAULT_SECRET_KEY_PLACEHOLDER
     access_token_expire_minutes: int = 30

-    # Authentik OIDC integration (placeholder - not yet wired into endpoints).
-    # When set, a future per-user check in core/auth.py will validate
-    # Authorization: Bearer JWTs against Authentik's JWKS. core/auth.py
-    # currently holds only the interim API-key check. See SECURITY-FINDINGS.md
-    # A01-1.
+    # Browser login through Authentik OIDC (see ADR-003). /api/v1 keeps the
+    # X-API-Key check in core/auth.py; these settings only drive the web UI.
+    public_base_url: str | None = None
     authentik_issuer: str | None = None
-    authentik_jwks_url: str | None = None
-    authentik_audience: str | None = None
+    authentik_client_id: str | None = None
+    authentik_client_secret: SecretStr | None = None
+    authentik_groups_claim: str = Field(default="groups", min_length=1)
+    admin_group: str = Field(default="llc-manager-admins", min_length=1)
+    viewer_group: str = Field(default="llc-manager-viewers", min_length=1)
+    session_max_age_seconds: int = Field(default=28800, gt=0)
+
+    # Break-glass local admin login, off by default.
+    local_admin_enabled: bool = False
+    local_admin_password_hash: SecretStr | None = None
+
+    # Reverse proxies whose X-Forwarded-* headers are trusted.
+    trusted_proxy_ips: Annotated[list[str], NoDecode] = Field(default_factory=list)
+
+    # Fixed admin user, no Authentik. Refused outside development.
+    auth_dev_mode: bool = False

     # Inbound service authentication for /api/v1 (see core/auth.py). An explicit
     # validation alias bypasses env_prefix, so both full names are listed; the
@@ -245,6 +276,238 @@
         )
         raise ConfigurationError(message, details={"config_key": "secret_key"})

+    @field_validator(
+        "public_base_url",
+        "authentik_issuer",
+        "authentik_client_id",
+        "authentik_client_secret",
+        "local_admin_password_hash",
+        mode="before",
+    )
+    @classmethod
+    def _blank_auth_value_is_unset(cls, value: object) -> object:
+        """Treat a blank auth setting as unset.
+
+        An empty value (for example ``LLC_MANAGER_AUTHENTIK_ISSUER=`` in an env
+        file) must behave like no value at all.
+
+        Args:
+            value (object): The raw value.
+
+        Returns:
+            object: None for a blank string, else the value unchanged.
+        """
+        if isinstance(value, str) and not value.strip():
+            return None
+        return value
+
+    @field_validator("public_base_url", mode="after")
+    @classmethod
+    def _normalize_public_base_url(cls, value: str | None) -> str | None:
+        """Require a bare http(s) origin and strip any trailing slash.
+
+        Args:
+            value (str | None): The configured URL.
+
+        Returns:
+            str | None: The origin without a trailing slash, or None.
+
+        Raises:
+            ConfigurationError: If the value is not a bare ``http://`` or
+                ``https://`` origin.
+        """
+        if value is None:
+            return None
+        parts = urlsplit(value.strip())
+        is_origin = (
+            parts.scheme in {"http", "https"}
+            and bool(parts.hostname)
+            and parts.path in {"", "/"}
+            and not parts.query
+            and not parts.fragment
+        )
+        if not is_origin:
+            message = (
+                "LLC_MANAGER_PUBLIC_BASE_URL must be a bare http(s) origin such "
+                "as https://llc.example.com (no path, query, or fragment)."
+            )
+            raise ConfigurationError(message, details={"config_key": "public_base_url"})
+        return f"{parts.scheme}://{parts.netloc}"
+
+    @field_validator("local_admin_password_hash", mode="after")
+    @classmethod
+    def _require_argon2_hash(cls, value: SecretStr | None) -> SecretStr | None:
+        """Reject a break-glass value that is not an argon2 hash.
+
+        Args:
+            value (SecretStr | None): The configured hash.
+
+        Returns:
+            SecretStr | None: The value, unchanged.
+
+        Raises:
+            ConfigurationError: If the value does not start with ``$argon2``.
+        """
+        if value is not None and not value.get_secret_value().startswith("$argon2"):
+            message = (
+                "LLC_MANAGER_LOCAL_ADMIN_PASSWORD_HASH must be an argon2 hash "
+                "(it starts with $argon2). Never set a plaintext password."
+            )
+            raise ConfigurationError(
+                message, details={"config_key": "local_admin_password_hash"}
+            )
+        return value
+
+    @field_validator("trusted_proxy_ips", mode="before")
+    @classmethod
+    def _split_proxy_ips(cls, value: object) -> object:
+        """Accept a comma-separated string of proxy addresses.
+
+        Args:
+            value (object): The raw value.
+
+        Returns:
+            object: A list of stripped, non-empty items for a string, else the
+                value unchanged.
+        """
+        if isinstance(value, str):
+            return [part.strip() for part in value.split(",") if part.strip()]
+        return value
+
+    @field_validator("trusted_proxy_ips", mode="after")
+    @classmethod
+    def _check_proxy_ips(cls, value: list[str]) -> list[str]:
+        """Require every entry to be an IP address or a CIDR network.
+
+        Args:
+            value (list[str]): The configured entries.
+
+        Returns:
+            list[str]: The entries, unchanged.
+
+        Raises:
+            ConfigurationError: If an entry is not an IP address or network.
+        """
+        for entry in value:
+            try:
+                ipaddress.ip_network(entry, strict=False)
+            except ValueError as exc:
+                message = (
+                    "LLC_MANAGER_TRUSTED_PROXY_IPS entries must be IP addresses "
+                    f"or CIDR networks; got {entry!r}."
+                )
+                raise ConfigurationError(
+                    message, details={"config_key": "trusted_proxy_ips"}
+                ) from exc
+        return value
+
+    @property
+    def oidc_configured(self) -> bool:
+        """Whether every setting that browser OIDC login needs is present."""
+        return (
+            self.authentik_issuer is not None
+            and self.authentik_client_id is not None
+            and self.authentik_client_secret is not None
+            and self.public_base_url is not None
+        )
+
+    @model_validator(mode="after")
+    def _enforce_oidc_settings_are_complete(self) -> "Settings":
+        """Reject a partly configured OIDC login.
+
+        Setting any of the issuer, client ID, or client secret means the others
+        and ``public_base_url`` must be set too. Setting none of them is valid
+        and leaves OIDC login unconfigured.
+
+        Returns:
+            Settings: The validated settings.
+
+        Raises:
+            ConfigurationError: If some, but not all, OIDC settings are set.
+        """
+        any_oidc = any(
+            value is not None
+            for value in (
+                self.authentik_issuer,
+                self.authentik_client_id,
+                self.authentik_client_secret,
+            )
+        )
+        if not any_oidc or self.oidc_configured:
+            return self
+        message = (
+            "LLC_MANAGER_AUTHENTIK_ISSUER, LLC_MANAGER_AUTHENTIK_CLIENT_ID, "
+            "LLC_MANAGER_AUTHENTIK_CLIENT_SECRET, and LLC_MANAGER_PUBLIC_BASE_URL "
+            "must all be set together."
+        )
+        raise ConfigurationError(message, details={"config_key": "authentik_issuer"})
+
+    @model_validator(mode="after")
+    def _enforce_local_admin_needs_hash(self) -> "Settings":
+        """Reject an enabled break-glass login that has no password hash.
+
+        Returns:
+            Settings: The validated settings.
+
+        Raises:
+            ConfigurationError: If the login is enabled without a hash.
+        """
+        if self.local_admin_enabled and self.local_admin_password_hash is None:
+            message = (
+                "LLC_MANAGER_LOCAL_ADMIN_ENABLED requires "
+                "LLC_MANAGER_LOCAL_ADMIN_PASSWORD_HASH."
+            )
+            raise ConfigurationError(
+                message, details={"config_key": "local_admin_password_hash"}
+            )
+        return self
+
+    @model_validator(mode="after")
+    def _refuse_dev_mode_outside_development(self) -> "Settings":
+        """Block startup when the dev-mode login is on in a non-dev environment.
+
+        Returns:
+            Settings: The validated settings.
+
+        Raises:
+            ConfigurationError: If ``auth_dev_mode`` is true outside
+                development, local, and test environments.
+        """
+        # #CRITICAL: Security - dev mode signs everyone in as admin.
+        # #VERIFY: tests/unit/test_auth_settings.py covers production refusal.
+        if self.auth_dev_mode and not _is_development_environment():
+            message = (
+                "LLC_MANAGER_AUTH_DEV_MODE must not be enabled outside "
+                "development, local, and test environments."
+            )
+            raise ConfigurationError(message, details={"config_key": "auth_dev_mode"})
+        return self
+
+    @model_validator(mode="after")
+    def _require_https_outside_development(self) -> "Settings":
+        """Require https for the public URL and the issuer outside development.
+
+        Returns:
+            Settings: The validated settings.
+
+        Raises:
+            ConfigurationError: If a configured URL is not ``https://`` outside
+                development, local, and test environments.
+        """
+        if _is_development_environment():
+            return self
+        for key, value in (
+            ("public_base_url", self.public_base_url),
+            ("authentik_issuer", self.authentik_issuer),
+        ):
+            if value is not None and not value.startswith("https://"):
+                message = (
+                    f"LLC_MANAGER_{key.upper()} must start with https:// outside "
+                    "development, local, and test environments."
+                )
+                raise ConfigurationError(message, details={"config_key": key})
+        return self
+
     @computed_field  # type: ignore[prop-decorator]  # Pydantic pattern: decorator composition confuses pyright
     @property
     def database_url(self) -> str:
````

- [ ] **Step 4: Run the tests and see them pass**

```bash
uv run pytest tests/unit/test_auth_settings.py tests/unit/test_security_audit_fixes.py -v -o addopts=""
```

Expected: `48 passed` (39 in `test_auth_settings.py`, 9 in `test_security_audit_fixes.py`).

- [ ] **Step 5: Lint and type-check the touched files**

```bash
uv run ruff format src/llc_manager/core/config.py tests/unit/test_auth_settings.py tests/unit/test_security_audit_fixes.py
uv run ruff check src/llc_manager/core/config.py tests/unit/test_auth_settings.py tests/unit/test_security_audit_fixes.py
uv run basedpyright src/llc_manager/core/config.py
```

Expected: `All checks passed!` from ruff and `0 errors` from basedpyright (warnings that already exist in `config.py` are not new).

- [ ] **Step 6: Commit**

```bash
git add src/llc_manager/core/config.py tests/unit/test_auth_settings.py tests/unit/test_security_audit_fixes.py
git commit -S -m "feat(auth): add sign-in settings and validators" -m "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

### Task 1.4: Finish PR 1

depends-on: Task 1.1 [completion], Task 1.2 [completion], Task 1.3 [completion]

- [ ] **Step 1: Add the changelog bullets under `## [Unreleased]`**

In `CHANGELOG.md`, replace this text:

````markdown
## [Unreleased]

### Added
````

with:

````markdown
## [Unreleased]

### Added

- `feat(auth)`: settings and validators for browser sign-in through Authentik
  (ADR-003): `public_base_url`, `authentik_client_id`,
  `authentik_client_secret`, `authentik_groups_claim`, `admin_group`,
  `viewer_group`, `session_max_age_seconds`, `local_admin_enabled`,
  `local_admin_password_hash`, `trusted_proxy_ips`, and `auth_dev_mode`.
  The OIDC settings must be all set or all unset; the break-glass switch
  needs an argon2 hash; dev mode is refused outside development, local, and
  test environments. `authlib`, `itsdangerous`, and `argon2-cffi` are now
  runtime dependencies. No route behavior changes yet.
````

In `CHANGELOG.md`, replace this text:

````markdown
- `scripts/generate-client.sh` -- React frontend artefact superseded by HTMX
````

with:

````markdown
- `refactor(auth)`: removed the unused `authentik_jwks_url` and
  `authentik_audience` settings. They implied bearer-JWT validation on
  `/api/v1`, which is not planned; the service API keeps `X-API-Key` (ADR-003).
- `scripts/generate-client.sh` -- React frontend artefact superseded by HTMX
````

- [ ] **Step 2: Run the whole suite with the repository defaults**

```bash
uv run pytest
```

Expected: all tests pass and the coverage gate (`--cov-fail-under=80`) holds. The verification run had 606 passing with the Excel import tests excluded.

- [ ] **Step 3: Pre-commit on every touched file**

```bash
pre-commit run --files CHANGELOG.md pyproject.toml uv.lock mkdocs.yml docs/planning/adr/README.md docs/planning/adr/adr-003-authentik-sso-web-login.md src/llc_manager/core/config.py tests/unit/test_auth_packaging.py tests/unit/test_auth_settings.py tests/unit/test_security_audit_fixes.py
git status --short
```

Expected: every hook passes. If `.secrets.baseline` shows as modified, run `git add .secrets.baseline` and run the command again.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -S -m "docs(changelog): record the sign-in settings" -m "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

- [ ] **Step 5: Open the PR (orchestrator only)**

```bash
git push -u origin feat/auth-settings
gh pr create --title "feat(auth): add adr-003, sign-in settings, and runtime dependencies" --body "$(cat <<'EOF'
## Summary

- Adds ADR-003 for Authentik web sign-in.
- Adds optional sign-in settings with validators; removes the unused `authentik_jwks_url` and `authentik_audience`.
- Declares `authlib`, `itsdangerous`, `argon2-cffi`, and `httpx` in the `api` extra.

No route behavior changes. A production environment with none of the new settings starts as before (`TestUnconfiguredProductionIsUnchanged`).

## Test plan

- [ ] `uv run pytest` passes
- [ ] `pre-commit run --all-files` passes

Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Not run by an implementer; the orchestrator pushes, opens the PR, and merges after CI. depends-on: Task 1.4 Step 4 [completion].

## PR 2: OIDC login, session, roles, CSRF, dev mode

Branch `feat/auth-oidc-session`. Adds the `auth/` package and wires `SessionMiddleware` and the `/auth` router into the app. `require_user`, `require_admin`, and `verify_csrf` are built and tested here but attached to nothing, so every existing page behaves as before. With no auth settings, `/auth/login` answers 503 and nothing else changes.

### Task 2.0: Worktree for PR 2

depends-on: PR 1 merged to `main`

- [ ] **Step 1: Create the worktree from the updated `main`**

```bash
cd /home/byron/dev/llc-manager
git fetch origin
git worktree add .worktrees/auth-oidc-session -b feat/auth-oidc-session origin/main
cd .worktrees/auth-oidc-session
uv sync --all-extras
uv run pytest tests/unit/test_auth_settings.py tests/unit/test_auth_packaging.py -v -o addopts=""
```

Expected: `44 passed`. If PR 1 is not on `origin/main`, stop: this PR needs its settings.

### Task 2.1: Redirect target validation

depends-on: Task 2.0 [completion]

Files:

- Create: `src/llc_manager/auth/__init__.py`, `src/llc_manager/auth/redirects.py`, `tests/unit/test_auth_redirects.py`

`next` is attacker-controlled. `safe_next` returns it only when it is a relative in-site path.

- [ ] **Step 1: Write the failing tests**

````python
"""Tests for post-login redirect validation."""

import pytest

from llc_manager.auth.redirects import DEFAULT_NEXT, safe_next


@pytest.mark.parametrize(
    "value",
    [
        "/entities",
        "/entities/123/edit",
        "/entities?q=acme&page=2",
        "/",
    ],
)
def test_safe_paths_are_kept(value: str) -> None:
    assert safe_next(value) == value


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "entities",
        "//evil.example/path",
        "///evil.example",
        "/\\evil.example",
        "/entities\\..\\x",
        "https://evil.example/",
        "http:/evil.example",
        "javascript:alert(1)",
        "/entities\r\nSet-Cookie: x=1",
        "/entities\x00",
        "/auth/login",
        "/auth/callback?code=1",
        "/auth",
        "evil.example",
    ],
)
def test_unsafe_values_fall_back_to_default(value: str | None) -> None:
    assert safe_next(value) == DEFAULT_NEXT


def test_lookalike_auth_prefix_is_allowed() -> None:
    assert safe_next("/authors") == "/authors"
````

- [ ] **Step 2: Run them and see them fail**

```bash
uv run pytest tests/unit/test_auth_redirects.py -v -o addopts=""
```

Expected: a collection error, `ModuleNotFoundError: No module named 'llc_manager.auth'`.

- [ ] **Step 3: Implement**

````python
"""Browser sign-in for the server-rendered web UI (Authentik OIDC)."""
````

````python
"""Validation of post-login redirect targets."""

from urllib.parse import urlsplit

DEFAULT_NEXT = "/entities"


def safe_next(value: str | None) -> str:
    """Return ``value`` if it is a safe in-site path, else the default.

    A safe target is a relative path that starts with a single ``/``. Anything
    that a browser could treat as another origin (a leading double slash, a
    backslash, a scheme, control characters) is rejected, as are paths under
    ``/auth`` so a login can never bounce back into the login flow.

    Args:
        value: The untrusted ``next`` value.

    Returns:
        The original value when safe, otherwise ``DEFAULT_NEXT``.
    """
    # #EDGE open redirect: an attacker-supplied `next` must never leave the site.
    # #VERIFY tests/unit/test_auth_redirects.py covers //, backslash, scheme, control chars.
    if not value or not value.startswith("/") or value.startswith("//"):
        return DEFAULT_NEXT
    if "\\" in value or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        return DEFAULT_NEXT
    parts = urlsplit(value)
    if parts.scheme or parts.netloc:
        return DEFAULT_NEXT
    if parts.path == "/auth" or parts.path.startswith("/auth/"):
        return DEFAULT_NEXT
    return value
````

- [ ] **Step 4: Run the tests and see them pass**

```bash
uv run pytest tests/unit/test_auth_redirects.py -v -o addopts=""
```

Expected: `21 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/llc_manager/auth/__init__.py src/llc_manager/auth/redirects.py tests/unit/test_auth_redirects.py
git commit -S -m "feat(auth): validate post-login redirect targets" -m "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

### Task 2.2: Role mapping

depends-on: Task 2.1 [output: the `llc_manager.auth` package]

Files:

- Create: `src/llc_manager/auth/roles.py`, `tests/unit/test_auth_roles.py`

Admin outranks viewer, matching is exact and case-sensitive, and no match or no claim gives no role (the callback turns that into a 403 page).

- [ ] **Step 1: Write the failing tests**

````python
"""Tests for group-claim to role mapping."""

import pytest

from llc_manager.auth.roles import Role, resolve_role

ADMIN = "llc-manager-admins"
VIEWER = "llc-manager-viewers"


def _resolve(claims: dict[str, object], claim: str = "groups") -> Role | None:
    return resolve_role(
        claims, groups_claim=claim, admin_group=ADMIN, viewer_group=VIEWER
    )


@pytest.mark.parametrize(
    ("claims", "expected"),
    [
        ({"groups": [ADMIN]}, Role.ADMIN),
        ({"groups": [VIEWER]}, Role.VIEWER),
        ({"groups": [VIEWER, ADMIN]}, Role.ADMIN),
        ({"groups": ["other", VIEWER]}, Role.VIEWER),
        ({"groups": ADMIN}, Role.ADMIN),
        ({"groups": ["other"]}, None),
        ({"groups": []}, None),
        ({"groups": None}, None),
        ({"groups": {"nested": ADMIN}}, None),
        ({"groups": [1, None, VIEWER]}, Role.VIEWER),
        ({}, None),
    ],
)
def test_role_resolution(claims: dict[str, object], expected: Role | None) -> None:
    assert _resolve(claims) == expected


def test_custom_claim_name_is_honoured() -> None:
    assert _resolve({"roles": [ADMIN]}, claim="roles") is Role.ADMIN
    assert _resolve({"groups": [ADMIN]}, claim="roles") is None


def test_group_names_are_matched_exactly() -> None:
    assert _resolve({"groups": [ADMIN.upper()]}) is None
    assert _resolve({"groups": [f"{ADMIN}-extra"]}) is None
````

- [ ] **Step 2: Run them and see them fail**

```bash
uv run pytest tests/unit/test_auth_roles.py -v -o addopts=""
```

Expected: `ModuleNotFoundError: No module named 'llc_manager.auth.roles'`.

- [ ] **Step 3: Implement**

````python
"""Mapping of Authentik group claims to application roles."""

from collections.abc import Mapping
from enum import StrEnum
from typing import cast


class Role(StrEnum):
    """Application roles, from most to least privileged."""

    ADMIN = "admin"
    VIEWER = "viewer"


def resolve_role(
    claims: Mapping[str, object],
    *,
    groups_claim: str,
    admin_group: str,
    viewer_group: str,
) -> Role | None:
    """Pick the highest role granted by the groups claim.

    Args:
        claims: Verified ID token claims.
        groups_claim: Name of the claim that lists group names.
        admin_group: Group that grants ``Role.ADMIN``.
        viewer_group: Group that grants ``Role.VIEWER``.

    Returns:
        ``Role.ADMIN`` if the admin group is present (it outranks viewer),
        ``Role.VIEWER`` if only the viewer group is present, else ``None``.
    """
    raw = claims.get(groups_claim)
    if isinstance(raw, str):
        groups = {raw}
    elif isinstance(raw, list):
        items = cast("list[object]", raw)
        groups = {item for item in items if isinstance(item, str)}
    else:
        return None
    if admin_group in groups:
        return Role.ADMIN
    if viewer_group in groups:
        return Role.VIEWER
    return None
````

- [ ] **Step 4: Run the tests and see them pass**

```bash
uv run pytest tests/unit/test_auth_roles.py -v -o addopts=""
```

Expected: `13 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/llc_manager/auth/roles.py tests/unit/test_auth_roles.py
git commit -S -m "feat(auth): map authentik groups to admin and viewer roles" -m "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

### Task 2.3: Session user and CSRF token storage

depends-on: Task 2.2 [output: `Role`]

Files:

- Create: `src/llc_manager/auth/session.py`, `tests/unit/test_auth_session.py`

`SessionMiddleware` re-signs the cookie on every response, so the cookie alone is a sliding window. The payload therefore carries an absolute `exp`, and `load_user` enforces it. `store_user` clears the session first (session fixation) and mints a new CSRF token.

- [ ] **Step 1: Write the failing tests**

````python
"""Tests for the session user and CSRF token helpers."""

from llc_manager.auth.roles import Role
from llc_manager.auth.session import (
    SessionUser,
    csrf_token,
    expected_csrf_token,
    load_user,
    store_user,
)

USER = SessionUser(
    sub="u1",
    email="u1@example.test",
    name="U One",
    role=Role.VIEWER,
    auth_method="oidc",
)


def test_round_trip_and_flags() -> None:
    session: dict[str, object] = {"stale": "pre-login state"}
    store_user(session, USER, max_age=100, now=1000.0)

    assert "stale" not in session
    assert load_user(session, now=1050.0) == USER
    assert USER.is_admin is False
    assert expected_csrf_token(session)


def test_absolute_expiry_is_enforced() -> None:
    session: dict[str, object] = {}
    store_user(session, USER, max_age=100, now=1000.0)

    assert load_user(session, now=1099.9) is not None
    assert load_user(session, now=1100.0) is None
    assert load_user(session, now=5000.0) is None


def test_new_login_mints_a_new_csrf_token() -> None:
    first: dict[str, object] = {}
    second: dict[str, object] = {}
    store_user(first, USER, max_age=100)
    store_user(second, USER, max_age=100)

    assert expected_csrf_token(first) != expected_csrf_token(second)


def test_malformed_session_is_treated_as_signed_out() -> None:
    assert load_user({}) is None
    assert load_user({"user": "admin"}) is None
    assert load_user({"user": {"sub": "x"}}) is None
    assert load_user({"user": {"sub": "x", "role": "root", "exp": 9e12}}) is None
    assert load_user({"user": {"sub": "x", "role": "admin", "exp": "never"}}) is None


def test_csrf_token_is_minted_once_and_stable() -> None:
    session: dict[str, object] = {}
    assert expected_csrf_token(session) is None

    token = csrf_token(session)

    assert token
    assert csrf_token(session) == token
    assert expected_csrf_token(session) == token
````

- [ ] **Step 2: Run them and see them fail**

```bash
uv run pytest tests/unit/test_auth_session.py -v -o addopts=""
```

Expected: `ModuleNotFoundError: No module named 'llc_manager.auth.session'`.

- [ ] **Step 3: Implement**

````python
"""Signed-cookie session helpers: the signed-in user and the CSRF token."""

import secrets
import time
from collections.abc import MutableMapping
from dataclasses import dataclass
from typing import Any, Literal, cast

from llc_manager.auth.roles import Role

SESSION_COOKIE = "llc_session"
_USER_KEY = "user"
_CSRF_KEY = "csrf"

AuthMethod = Literal["oidc", "local", "dev"]
Session = MutableMapping[str, Any]


@dataclass(frozen=True)
class SessionUser:
    """The signed-in user as stored in the session cookie."""

    sub: str
    email: str | None
    name: str | None
    role: Role
    auth_method: AuthMethod

    @property
    def is_admin(self) -> bool:
        """Whether this user may edit data."""
        return self.role is Role.ADMIN


def store_user(
    session: Session,
    user: SessionUser,
    *,
    max_age: int,
    now: float | None = None,
) -> None:
    """Replace the session contents with a freshly signed-in user.

    The session is cleared first so no pre-login state survives (session
    fixation), and a new CSRF token is minted. An absolute expiry is stored
    because Starlette refreshes the cookie on every response, which would
    otherwise make the lifetime sliding.

    Args:
        session: The request session mapping.
        user: The user to sign in.
        max_age: Absolute lifetime in seconds.
        now: Current epoch seconds (injectable for tests).
    """
    # #ASSUME a signed cookie cannot be revoked server-side before `exp`; the
    # 8 hour lifetime is the only bound on a stolen cookie.
    # #VERIFY rotating LLC_MANAGER_SECRET_KEY invalidates every session at once.
    issued = time.time() if now is None else now
    session.clear()
    session[_USER_KEY] = {
        "sub": user.sub,
        "email": user.email,
        "name": user.name,
        "role": user.role.value,
        "auth_method": user.auth_method,
        "exp": issued + max_age,
    }
    session[_CSRF_KEY] = secrets.token_urlsafe(32)


def load_user(session: Session, *, now: float | None = None) -> SessionUser | None:
    """Return the signed-in user, or ``None`` if absent, expired or malformed.

    Args:
        session: The request session mapping.
        now: Current epoch seconds (injectable for tests).

    Returns:
        The stored user, or ``None``.
    """
    raw = session.get(_USER_KEY)
    if not isinstance(raw, dict):
        return None
    data = cast("dict[str, Any]", raw)
    current = time.time() if now is None else now
    exp = data.get("exp")
    if not isinstance(exp, int | float) or exp <= current:
        return None
    try:
        return SessionUser(
            sub=str(data["sub"]),
            email=data.get("email"),
            name=data.get("name"),
            role=Role(data["role"]),
            auth_method=data["auth_method"],
        )
    except (KeyError, ValueError):
        return None


def csrf_token(session: Session) -> str:
    """Return the session CSRF token, minting one if none exists yet.

    Args:
        session: The request session mapping.

    Returns:
        The token to embed in forms and the ``X-CSRF-Token`` header.
    """
    token = session.get(_CSRF_KEY)
    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        session[_CSRF_KEY] = token
    return token


def expected_csrf_token(session: Session) -> str | None:
    """Return the stored CSRF token without minting one.

    Args:
        session: The request session mapping.

    Returns:
        The stored token, or ``None`` if the session has none.
    """
    token = session.get(_CSRF_KEY)
    return token if isinstance(token, str) and token else None
````

- [ ] **Step 4: Run the tests and see them pass**

```bash
uv run pytest tests/unit/test_auth_session.py -v -o addopts=""
```

Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/llc_manager/auth/session.py tests/unit/test_auth_session.py
git commit -S -m "feat(auth): store the signed-in user and csrf token in the session" -m "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

### Task 2.4: CSRF check and the gates (not attached)

depends-on: Task 2.1 [output: `safe_next`], Task 2.2 [output: `Role`], Task 2.3 [output: `load_user`, `expected_csrf_token`]

Files:

- Create: `src/llc_manager/auth/csrf.py`, `src/llc_manager/auth/dependencies.py`, `tests/unit/test_auth_gates.py`
- Modify: `tests/auth_helpers.py`

`require_user` redirects (303) or answers 401 plus `HX-Redirect`; `require_admin` answers 403 for a viewer; `verify_csrf` rejects any non-safe request without the session token. They are tested against a throwaway app inside the test file; nothing in the real app uses them yet.

- [ ] **Step 1: Extend the shared test helpers and write the failing tests**

`tests/auth_helpers.py` already holds `TEST_API_KEY` and `AUTH_HEADERS`; the diff adds cookie-signing helpers.

````diff
--- a/tests/auth_helpers.py
+++ b/tests/auth_helpers.py
@@ -1,4 +1,74 @@
-"""Shared API key values for tests. Synthetic; not used anywhere else."""
+"""Shared test credentials and session helpers. All values are synthetic."""
+
+import json
+import time
+from base64 import b64decode, b64encode
+from typing import Any
+
+import itsdangerous
+
+from llc_manager.auth.session import SESSION_COOKIE

 TEST_API_KEY = "test-only-api-key-0123456789abcdef"  # pragma: allowlist secret
 AUTH_HEADERS = {"X-API-Key": TEST_API_KEY}
+TEST_CSRF_TOKEN = "test-only-csrf-token-0123456789"  # pragma: allowlist secret
+
+
+def session_cookie_value(secret_key: str, session: dict[str, Any]) -> str:
+    """Encode ``session`` exactly as Starlette's SessionMiddleware does.
+
+    Args:
+        secret_key: The application secret key.
+        session: The session payload.
+
+    Returns:
+        The signed cookie value.
+    """
+    data = b64encode(json.dumps(session).encode("utf-8"))
+    signer = itsdangerous.TimestampSigner(secret_key)
+    return signer.sign(data).decode("utf-8")
+
+
+def decode_session_cookie(secret_key: str, value: str) -> dict[str, Any]:
+    """Decode and verify a session cookie value.
+
+    Args:
+        secret_key: The application secret key.
+        value: The cookie value.
+
+    Returns:
+        The session payload.
+    """
+    signer = itsdangerous.TimestampSigner(secret_key)
+    return json.loads(b64decode(signer.unsign(value)))
+
+
+def user_session(
+    role: str = "admin", *, exp_in: float = 3600, csrf: str = TEST_CSRF_TOKEN
+) -> dict[str, Any]:
+    """Build a session payload for a signed-in user.
+
+    Args:
+        role: ``"admin"`` or ``"viewer"``.
+        exp_in: Seconds until the session expires (negative for expired).
+        csrf: The CSRF token stored in the session.
+
+    Returns:
+        The session mapping.
+    """
+    return {
+        "user": {
+            "sub": f"test-{role}",
+            "email": f"{role}@example.test",
+            "name": f"Test {role.title()}",
+            "role": role,
+            "auth_method": "oidc",
+            "exp": time.time() + exp_in,
+        },
+        "csrf": csrf,
+    }
+
+
+def cookie_name() -> str:
+    """Return the session cookie name used by the app."""
+    return SESSION_COOKIE
````

````python
"""Tests for the gate dependencies, using a throwaway app.

The gates are defined here but not yet attached to the real web routes, so
they are exercised against a minimal FastAPI app with the same session
middleware settings as the real one.
"""

from collections.abc import Iterator
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from llc_manager.auth.csrf import verify_csrf
from llc_manager.auth.dependencies import require_admin, require_user
from llc_manager.auth.session import SESSION_COOKIE, SessionUser
from llc_manager.core.config import settings
from tests.auth_helpers import (
    TEST_CSRF_TOKEN,
    session_cookie_value,
    user_session,
)

SECRET = "x" * 40  # pragma: allowlist secret


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        SessionMiddleware, secret_key=SECRET, session_cookie=SESSION_COOKIE
    )

    @app.get("/page")
    async def page(
        user: Annotated[SessionUser, Depends(require_user)],
    ) -> dict[str, str]:
        return {"sub": user.sub, "role": user.role.value}

    @app.get("/admin-page")
    async def admin_page(
        user: Annotated[SessionUser, Depends(require_admin)],
    ) -> dict[str, str]:
        return {"sub": user.sub}

    @app.post("/change", dependencies=[Depends(verify_csrf)])
    async def change() -> dict[str, bool]:
        return {"changed": True}

    @app.patch("/change", dependencies=[Depends(verify_csrf)])
    async def change_patch() -> dict[str, bool]:
        return {"changed": True}

    return app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(_build_app(), follow_redirects=False) as test_client:
        yield test_client


def _sign_in(client: TestClient, role: str = "admin", **kwargs: float) -> None:
    client.cookies.set(
        SESSION_COOKIE, session_cookie_value(SECRET, user_session(role, **kwargs))
    )


class TestRequireUser:
    def test_page_request_without_session_redirects_to_login(
        self, client: TestClient
    ) -> None:
        response = client.get("/page?x=1")

        assert response.status_code == 303
        assert response.headers["location"] == "/auth/login?next=%2Fpage%3Fx%3D1"

    def test_htmx_request_gets_401_with_hx_redirect(self, client: TestClient) -> None:
        response = client.get(
            "/page",
            headers={
                "HX-Request": "true",
                "HX-Current-URL": "http://testserver/entities/42?tab=a",
            },
        )

        assert response.status_code == 401
        assert response.headers["hx-redirect"] == (
            "/auth/login?next=%2Fentities%2F42%3Ftab%3Da"
        )
        assert "location" not in response.headers

    def test_hostile_hx_current_url_falls_back_to_default(
        self, client: TestClient
    ) -> None:
        response = client.get(
            "/page",
            headers={"HX-Request": "true", "HX-Current-URL": "http://x//evil.example"},
        )

        assert response.headers["hx-redirect"] == "/auth/login?next=%2Fentities"

    def test_non_get_request_does_not_remember_its_path(
        self, client: TestClient
    ) -> None:
        response = client.post("/change")

        # verify_csrf runs without a session; the point is the 403, not a path.
        assert response.status_code == 403

    def test_valid_session_passes(self, client: TestClient) -> None:
        _sign_in(client, "viewer")

        response = client.get("/page")

        assert response.status_code == 200
        assert response.json() == {"sub": "test-viewer", "role": "viewer"}

    def test_expired_session_is_signed_out(self, client: TestClient) -> None:
        _sign_in(client, exp_in=-5)

        assert client.get("/page").status_code == 303

    def test_session_signed_with_another_key_is_rejected(
        self, client: TestClient
    ) -> None:
        client.cookies.set(
            SESSION_COOKIE,
            session_cookie_value("y" * 40, user_session("admin")),
        )

        assert client.get("/page").status_code == 303

    def test_dev_mode_acts_as_admin_without_a_session(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "auth_dev_mode", True)

        response = client.get("/admin-page")

        assert response.status_code == 200
        assert response.json() == {"sub": "dev-user"}


class TestRequireAdmin:
    def test_admin_passes(self, client: TestClient) -> None:
        _sign_in(client, "admin")

        assert client.get("/admin-page").status_code == 200

    def test_viewer_is_forbidden(self, client: TestClient) -> None:
        _sign_in(client, "viewer")

        assert client.get("/admin-page").status_code == 403

    def test_anonymous_is_sent_to_login_not_403(self, client: TestClient) -> None:
        assert client.get("/admin-page").status_code == 303


class TestVerifyCsrf:
    def test_safe_methods_need_no_token(self, client: TestClient) -> None:
        assert client.get("/page").status_code == 303  # gate, not CSRF

    def test_header_token_is_accepted(self, client: TestClient) -> None:
        _sign_in(client)

        response = client.patch("/change", headers={"X-CSRF-Token": TEST_CSRF_TOKEN})

        assert response.status_code == 200

    def test_form_field_token_is_accepted(self, client: TestClient) -> None:
        _sign_in(client)

        response = client.post("/change", data={"csrf_token": TEST_CSRF_TOKEN})

        assert response.status_code == 200

    @pytest.mark.parametrize("token", [None, "", "wrong", TEST_CSRF_TOKEN + "x"])
    def test_missing_or_wrong_token_is_rejected(
        self, client: TestClient, token: str | None
    ) -> None:
        _sign_in(client)
        headers = {} if token is None else {"X-CSRF-Token": token}

        assert client.post("/change", headers=headers).status_code == 403

    def test_session_without_a_token_rejects_everything(
        self, client: TestClient
    ) -> None:
        payload = user_session()
        del payload["csrf"]
        client.cookies.set(SESSION_COOKIE, session_cookie_value(SECRET, payload))

        response = client.post("/change", headers={"X-CSRF-Token": "anything"})

        assert response.status_code == 403

    def test_json_body_does_not_satisfy_the_check(self, client: TestClient) -> None:
        _sign_in(client)

        response = client.post("/change", json={"csrf_token": TEST_CSRF_TOKEN})

        assert response.status_code == 403
````

- [ ] **Step 2: Run them and see them fail**

```bash
uv run pytest tests/unit/test_auth_gates.py -v -o addopts=""
```

Expected: `ModuleNotFoundError: No module named 'llc_manager.auth.csrf'`.

- [ ] **Step 3: Implement**

````python
"""CSRF protection for cookie-authenticated, state-changing requests."""

import hmac

from fastapi import HTTPException, Request, status

from llc_manager.auth.session import expected_csrf_token

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
CSRF_HEADER = "X-CSRF-Token"
CSRF_FORM_FIELD = "csrf_token"


async def verify_csrf(request: Request) -> None:
    """Reject non-safe requests that lack the session's CSRF token.

    The token may arrive in the ``X-CSRF-Token`` header (HTMX) or the
    ``csrf_token`` form field (plain forms). Comparison is constant time.

    Args:
        request: The incoming request.

    Raises:
        HTTPException: 403 when the token is missing or does not match.
    """
    # #CRITICAL cookie-authenticated writes are forgeable without this check.
    # #VERIFY every non-safe web route carries it (tests/unit/test_web_gating.py).
    if request.method in SAFE_METHODS:
        return
    expected = expected_csrf_token(request.session)
    supplied = request.headers.get(CSRF_HEADER)
    if supplied is None:
        content_type = request.headers.get("content-type", "")
        if content_type.startswith(
            ("application/x-www-form-urlencoded", "multipart/form-data")
        ):
            field = (await request.form()).get(CSRF_FORM_FIELD)
            supplied = field if isinstance(field, str) else None
    if (
        expected is None
        or supplied is None
        or not hmac.compare_digest(expected.encode(), supplied.encode())
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token missing or invalid",
        )
````

````python
"""Gate dependencies for the web UI: sign-in, role, and the dev-mode user."""

from typing import Annotated
from urllib.parse import quote, urlsplit

from fastapi import Depends, HTTPException, Request, status

from llc_manager.auth.redirects import safe_next
from llc_manager.auth.roles import Role
from llc_manager.auth.session import SessionUser, load_user
from llc_manager.core.config import settings

LOGIN_PATH = "/auth/login"
_DEV_USER = SessionUser(
    sub="dev-user",
    email="dev@localhost",
    name="Development User",
    role=Role.ADMIN,
    auth_method="dev",
)


def is_htmx(request: Request) -> bool:
    """Whether the request was issued by HTMX (including boosted links).

    Args:
        request: The incoming request.

    Returns:
        True when the ``HX-Request`` header is ``true``.
    """
    return request.headers.get("HX-Request", "").lower() == "true"


def current_user(request: Request) -> SessionUser | None:
    """Return the signed-in user without enforcing anything.

    Args:
        request: The incoming request.

    Returns:
        The dev user in dev mode, else the session user, else ``None``.
    """
    if settings.auth_dev_mode:
        return _DEV_USER
    return load_user(request.session)


def _login_target(request: Request) -> str:
    """Pick where the user should land after signing in."""
    if is_htmx(request):
        current = urlsplit(request.headers.get("HX-Current-URL", ""))
        candidate = current.path + (f"?{current.query}" if current.query else "")
        return safe_next(candidate)
    if request.method in {"GET", "HEAD"}:
        query = f"?{request.url.query}" if request.url.query else ""
        return safe_next(request.url.path + query)
    return safe_next(None)


async def require_user(request: Request) -> SessionUser:
    """Require a signed-in user.

    Args:
        request: The incoming request.

    Returns:
        The signed-in user.

    Raises:
        HTTPException: 303 to the login page for page requests, or 401 with
            ``HX-Redirect`` for HTMX requests (a redirect would otherwise be
            swapped into the page as a fragment).
    """
    user = current_user(request)
    if user is not None:
        return user
    location = f"{LOGIN_PATH}?next={quote(_login_target(request), safe='')}"
    if is_htmx(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in required",
            headers={"HX-Redirect": location},
        )
    raise HTTPException(
        status_code=status.HTTP_303_SEE_OTHER,
        detail="Sign in required",
        headers={"Location": location},
    )


async def require_admin(
    user: Annotated[SessionUser, Depends(require_user)],
) -> SessionUser:
    """Require a signed-in administrator.

    Args:
        user: The signed-in user.

    Returns:
        The administrator.

    Raises:
        HTTPException: 403 when the user is not an administrator.
    """
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required",
        )
    return user
````

- [ ] **Step 4: Run the tests and see them pass**

```bash
uv run pytest tests/unit/test_auth_gates.py -v -o addopts=""
```

Expected: `20 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/llc_manager/auth/csrf.py src/llc_manager/auth/dependencies.py tests/auth_helpers.py tests/unit/test_auth_gates.py
git commit -S -m "feat(auth): add the session, admin, and csrf gates" -m "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

### Task 2.5: OIDC client, login routes, and app wiring

depends-on: Task 2.4 [completion]

Files:

- Create: `src/llc_manager/auth/oidc.py`, `src/llc_manager/auth/routes.py`, `src/llc_manager/templates/auth/message.html`, `tests/oidc_fake.py`, `tests/unit/test_auth_oidc_flow.py`, `tests/unit/test_auth_wiring.py`
- Modify: `src/llc_manager/main.py`

The tests use a fake in-memory provider: `tests/oidc_fake.py` signs real ID tokens with `joserfc` and replaces only the `authlib` client's `fetch_access_token`. Provider metadata is passed as static keyword arguments, so no test touches the network, yet issuer, audience, nonce, expiry, and signature are still validated by the real library code.

- [ ] **Step 1: Write the fake provider and the failing tests**

````python
"""A fake in-memory OIDC provider for tests. Never touches the network.

The real authlib client is used with static provider metadata and an inline
JWKS, so state, nonce, PKCE and ID token validation all run for real. Only the
token-endpoint HTTP call is replaced, returning an ID token signed here.
"""

import time
from typing import Any
from urllib.parse import parse_qs, urlsplit

from authlib.integrations.starlette_client import OAuth
from joserfc import jwt
from joserfc.jwk import RSAKey

ISSUER = "https://auth.example.test/application/o/llc-manager/"
CLIENT_ID = "test-client-id"
REDIRECT_URI = "https://llc.example.test/auth/callback"


class FakeProvider:
    """Signs ID tokens and exposes an authlib client wired to itself."""

    def __init__(self) -> None:
        """Generate a signing key and register the authlib client."""
        self._key = RSAKey.generate_key(
            2048, {"kid": "test-key", "use": "sig", "alg": "RS256"}
        )
        self.next_claims: dict[str, Any] = {}
        self.fail_with: Exception | None = None
        oauth = OAuth()
        oauth.register(
            name="authentik",
            client_id=CLIENT_ID,
            client_secret="test-client-secret",  # pragma: allowlist secret
            issuer=ISSUER,
            authorization_endpoint="https://auth.example.test/authorize/",
            token_endpoint="https://auth.example.test/token/",
            jwks={"keys": [self._key.as_dict(private=False)]},
            id_token_signing_alg_values_supported=["RS256"],
            client_kwargs={
                "scope": "openid profile email",
                "code_challenge_method": "S256",
            },
        )
        self.client: Any = oauth.authentik
        self.client.fetch_access_token = self._fetch_access_token
        self._nonce: str | None = None

    def remember_authorization(self, location: str) -> dict[str, str]:
        """Capture state and nonce from the redirect to the provider.

        Args:
            location: The ``Location`` header of the authorize redirect.

        Returns:
            Single-valued query parameters of the authorize URL.
        """
        query = parse_qs(urlsplit(location).query)
        params = {key: values[0] for key, values in query.items()}
        self._nonce = params["nonce"]
        return params

    def claims(self, **overrides: Any) -> dict[str, Any]:
        """Build valid claims for the remembered authorization, with overrides.

        Args:
            **overrides: Claims to add or replace. A value of ``None`` removes
                the claim.

        Returns:
            The claim set.
        """
        now = int(time.time())
        base: dict[str, Any] = {
            "iss": ISSUER,
            "aud": CLIENT_ID,
            "sub": "user-123",
            "iat": now,
            "exp": now + 300,
            "nonce": self._nonce,
            "email": "ada@example.test",
            "name": "Ada Lovelace",
            "groups": ["llc-manager-admins"],
        }
        base.update(overrides)
        return {key: value for key, value in base.items() if value is not None}

    def sign(self, claims: dict[str, Any]) -> str:
        """Sign an ID token.

        Args:
            claims: The claim set.

        Returns:
            The compact JWT.
        """
        return jwt.encode({"alg": "RS256", "kid": "test-key"}, claims, self._key)

    async def _fetch_access_token(self, **_params: Any) -> dict[str, Any]:
        if self.fail_with is not None:
            raise self.fail_with
        return {
            "access_token": "fake-access-token",
            "token_type": "Bearer",
            "id_token": self.sign(self.next_claims),
        }
````

````python
"""Tests for /auth/login, /auth/callback and /auth/logout with a fake provider."""

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, cast

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from llc_manager.auth.oidc import (
    build_oidc_client,
    discovery_url,
    redirect_uri,
)
from llc_manager.auth.session import SESSION_COOKIE
from llc_manager.core.config import settings
from llc_manager.main import create_app
from tests.auth_helpers import (
    TEST_CSRF_TOKEN,
    decode_session_cookie,
    session_cookie_value,
    user_session,
)
from tests.oidc_fake import CLIENT_ID, ISSUER, REDIRECT_URI, FakeProvider

if TYPE_CHECKING:
    from fastapi import FastAPI

BASE_URL = "https://llc.example.test"


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def client(
    provider: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    monkeypatch.setattr(settings, "public_base_url", BASE_URL)
    monkeypatch.setattr(settings, "authentik_issuer", ISSUER)
    monkeypatch.setattr(settings, "authentik_client_id", CLIENT_ID)
    monkeypatch.setattr(settings, "authentik_client_secret", SecretStr("s"))
    app = create_app()
    app.state.oidc_client = provider.client
    with TestClient(app, base_url=BASE_URL, follow_redirects=False) as test_client:
        yield test_client


def _start_login(client: TestClient, provider: FakeProvider, next_: str | None = None):
    url = "/auth/login" if next_ is None else f"/auth/login?next={next_}"
    response = client.get(url)
    assert response.status_code == 302
    params = provider.remember_authorization(response.headers["location"])
    return response, params


def _finish_login(
    client: TestClient, provider: FakeProvider, params: dict[str, str], **claims: Any
):
    provider.next_claims = provider.claims(**claims)
    return client.get("/auth/callback", params={"code": "c", "state": params["state"]})


class TestLogin:
    def test_redirects_to_provider_with_state_nonce_and_pkce(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        response, params = _start_login(client, provider)

        assert response.headers["location"].startswith(
            "https://auth.example.test/authorize/?"
        )
        assert params["client_id"] == CLIENT_ID
        assert params["redirect_uri"] == REDIRECT_URI
        assert params["response_type"] == "code"
        assert params["scope"] == "openid profile email"
        assert params["code_challenge_method"] == "S256"
        assert params["state"]
        assert params["nonce"]

    def test_session_cookie_is_hardened(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        response, _ = _start_login(client, provider)

        cookie = response.headers["set-cookie"].lower()
        assert f"{SESSION_COOKIE}=" in cookie
        assert "httponly" in cookie
        assert "secure" in cookie
        assert "samesite=lax" in cookie

    def test_not_configured_shows_unavailable_page(self, client: TestClient) -> None:
        cast("FastAPI", client.app).state.oidc_client = None

        response = client.get("/auth/login")

        assert response.status_code == 503
        assert "not configured" in response.text

    def test_provider_outage_during_discovery_shows_retry_page(
        self, client: TestClient
    ) -> None:
        class _Unreachable:
            async def authorize_redirect(self, *_args: Any, **_kwargs: Any) -> None:
                raise httpx.ConnectError("discovery failed")

        cast("FastAPI", client.app).state.oidc_client = _Unreachable()

        response = client.get("/auth/login")

        assert response.status_code == 503
        assert "temporarily unavailable" in response.text

    def test_already_signed_in_goes_straight_to_next(self, client: TestClient) -> None:
        client.cookies.set(
            SESSION_COOKIE,
            session_cookie_value(settings.secret_key, user_session("viewer")),
        )

        response = client.get("/auth/login?next=/entities/1")

        assert response.status_code == 303
        assert response.headers["location"] == "/entities/1"


class TestCallback:
    def test_admin_login_creates_session_and_returns_to_next(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        _, params = _start_login(client, provider, next_="/entities/9?tab=a")

        response = _finish_login(client, provider, params)

        assert response.status_code == 303
        assert response.headers["location"] == "/entities/9?tab=a"
        assert f"{SESSION_COOKIE}=" in response.headers["set-cookie"]

    def test_session_after_login_has_role_and_csrf_token(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        _, params = _start_login(client, provider)
        _finish_login(client, provider, params, groups=["llc-manager-viewers"])

        session = decode_session_cookie(
            settings.secret_key, client.cookies[SESSION_COOKIE]
        )

        assert session["user"]["role"] == "viewer"
        assert session["user"]["email"] == "ada@example.test"
        assert session["user"]["auth_method"] == "oidc"
        assert session["csrf"]
        # Login state (state, nonce, PKCE verifier) must not outlive the login.
        assert sorted(session) == ["csrf", "user"]

    def test_unsafe_next_is_replaced_by_default(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        _, params = _start_login(client, provider, next_="//evil.example")

        response = _finish_login(client, provider, params)

        assert response.headers["location"] == "/entities"

    def test_user_without_a_known_group_gets_403_page(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        _, params = _start_login(client, provider)

        response = _finish_login(client, provider, params, groups=["other"])

        assert response.status_code == 403
        assert "Access denied" in response.text

    @pytest.mark.parametrize(
        "overrides",
        [
            {"iss": "https://evil.example/"},
            {"aud": "another-client"},
            {"nonce": "not-the-nonce"},
            {"exp": 1},
            {"exp": None},
            {"sub": None},
        ],
        ids=["issuer", "audience", "nonce", "expired", "no-exp", "no-sub"],
    )
    def test_invalid_id_token_is_rejected_without_a_session(
        self, client: TestClient, provider: FakeProvider, overrides: dict[str, Any]
    ) -> None:
        _, params = _start_login(client, provider)

        response = _finish_login(client, provider, params, **overrides)

        assert response.status_code == 400
        assert "Sign-in failed" in response.text
        assert "user" not in response.headers.get("set-cookie", "")

    def test_state_mismatch_is_rejected(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        _start_login(client, provider)
        provider.next_claims = provider.claims()

        response = client.get("/auth/callback", params={"code": "c", "state": "forged"})

        assert response.status_code == 400

    def test_callback_without_a_login_attempt_is_rejected(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        provider.next_claims = provider.claims()

        response = client.get("/auth/callback", params={"code": "c", "state": "x"})

        assert response.status_code == 400

    def test_provider_error_response_is_rejected(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        _, params = _start_login(client, provider)

        response = client.get(
            "/auth/callback",
            params={"error": "access_denied", "state": params["state"]},
        )

        assert response.status_code == 400

    def test_provider_outage_shows_retry_page(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        _, params = _start_login(client, provider)
        provider.fail_with = httpx.ConnectError("boom")

        response = _finish_login(client, provider, params)

        assert response.status_code == 503
        assert "temporarily unavailable" in response.text
        assert 'href="/auth/login"' in response.text

    def test_callback_is_not_blocked_by_the_ssrf_filter(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        _, params = _start_login(client, provider)
        provider.next_claims = provider.claims()

        response = client.get(
            "/auth/callback",
            params={"code": "c", "state": params["state"], "iss": ISSUER},
        )

        assert response.status_code == 303

    def test_replayed_state_cannot_log_in_twice(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        _, params = _start_login(client, provider)
        assert _finish_login(client, provider, params).status_code == 303

        replay = _finish_login(client, provider, params)

        assert replay.status_code == 400


class TestLogout:
    def test_logout_requires_csrf_token(self, client: TestClient) -> None:
        client.cookies.set(
            SESSION_COOKIE,
            session_cookie_value(settings.secret_key, user_session("admin")),
        )

        assert client.post("/auth/logout").status_code == 403

    def test_logout_clears_the_session(self, client: TestClient) -> None:
        client.cookies.set(
            SESSION_COOKIE,
            session_cookie_value(settings.secret_key, user_session("admin")),
        )

        response = client.post("/auth/logout", data={"csrf_token": TEST_CSRF_TOKEN})

        assert response.status_code == 200
        assert "Signed out" in response.text
        # An emptied session makes Starlette expire the cookie in the browser.
        assert "expires=thu, 01 jan 1970" in response.headers["set-cookie"].lower()

    def test_get_logout_is_not_allowed(self, client: TestClient) -> None:
        assert client.get("/auth/logout").status_code == 405


class TestClientConstruction:
    def test_discovery_url_handles_trailing_slash(self) -> None:
        assert (
            discovery_url("https://a.test/o/x/")
            == "https://a.test/o/x/.well-known/openid-configuration"
        )
        assert (
            discovery_url("https://a.test/o/x")
            == "https://a.test/o/x/.well-known/openid-configuration"
        )

    def test_redirect_uri_is_under_the_public_origin(self) -> None:
        assert redirect_uri("https://llc.example.test") == REDIRECT_URI

    def test_no_client_when_unconfigured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "authentik_issuer", None)

        assert build_oidc_client(settings) is None

    def test_client_is_built_when_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "public_base_url", BASE_URL)
        monkeypatch.setattr(settings, "authentik_issuer", ISSUER)
        monkeypatch.setattr(settings, "authentik_client_id", CLIENT_ID)
        monkeypatch.setattr(settings, "authentik_client_secret", SecretStr("s"))

        assert build_oidc_client(settings) is not None
````

````python
"""Tests for how the auth package is wired into the app (PR 2 behavior).

PR 2 adds the sign-in machinery but gates nothing, so an app with no auth
settings must behave exactly as before.
"""

from collections.abc import Iterator
from typing import TYPE_CHECKING, cast

import pytest
from fastapi.testclient import TestClient

from llc_manager.auth.session import SESSION_COOKIE
from llc_manager.core.config import settings
from llc_manager.main import create_app

if TYPE_CHECKING:
    from fastapi import FastAPI


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), follow_redirects=False) as test_client:
        yield test_client


def test_unconfigured_app_has_no_oidc_client(client: TestClient) -> None:
    assert cast("FastAPI", client.app).state.oidc_client is None


def test_unconfigured_login_is_a_clear_503_not_a_crash(client: TestClient) -> None:
    response = client.get("/auth/login")

    assert response.status_code == 503
    assert "not configured" in response.text


def test_web_routes_are_still_open(client: TestClient) -> None:
    # Gating ships in a later PR; until then the root dashboard stays open.
    assert client.get("/").status_code == 200


def test_no_cookie_is_set_for_anonymous_requests(client: TestClient) -> None:
    response = client.get("/")

    assert SESSION_COOKIE not in response.headers.get("set-cookie", "")


def test_auth_routes_are_hidden_from_the_openapi_schema(client: TestClient) -> None:
    paths = client.get("/api/openapi.json").json()["paths"]

    assert not [path for path in paths if path.startswith("/auth")]


def test_dev_mode_login_goes_straight_to_next(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_dev_mode", True)
    with TestClient(create_app(), follow_redirects=False) as dev_client:
        response = dev_client.get("/auth/login?next=/entities/5")

    assert response.status_code == 303
    assert response.headers["location"] == "/entities/5"


def test_dev_mode_logs_a_startup_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(settings, "auth_dev_mode", True)

    with TestClient(create_app()):
        pass

    assert "auth_dev_mode_enabled" in caplog.text
````

- [ ] **Step 2: Run them and see them fail**

```bash
uv run pytest tests/unit/test_auth_oidc_flow.py tests/unit/test_auth_wiring.py -v -o addopts=""
```

Expected: `ModuleNotFoundError: No module named 'llc_manager.auth.oidc'`.

- [ ] **Step 3: Implement the OIDC client**

Discovery is lazy: `authlib` fetches the discovery document on the first `authorize_redirect`, so building the client never makes a network call and an unreachable Authentik cannot stop the app from starting.

````python
"""Authentik OpenID Connect client, wrapped behind a small typed protocol."""

from typing import Any, Protocol, cast

from authlib.integrations.starlette_client import OAuth  # pyright: ignore[reportMissingTypeStubs]
from fastapi import Request
from starlette.responses import Response

from llc_manager.core.config import Settings

CLIENT_NAME = "authentik"
CALLBACK_PATH = "/auth/callback"
SCOPE = "openid profile email"


class OidcClient(Protocol):
    """The two authlib calls the login flow needs."""

    async def authorize_redirect(self, request: Request, redirect_uri: str) -> Response:
        """Start the authorization-code flow with PKCE."""
        ...

    async def authorize_access_token(self, request: Request) -> dict[str, Any]:
        """Exchange the callback code and validate the ID token."""
        ...


def discovery_url(issuer: str) -> str:
    """Build the OIDC discovery document URL for an issuer.

    Args:
        issuer: The issuer URL, with or without a trailing slash.

    Returns:
        The ``.well-known/openid-configuration`` URL.
    """
    return issuer.rstrip("/") + "/.well-known/openid-configuration"


def redirect_uri(public_base_url: str) -> str:
    """Build the callback URL registered with Authentik.

    Args:
        public_base_url: The normalized public origin.

    Returns:
        The absolute callback URL.
    """
    return public_base_url + CALLBACK_PATH


def build_oidc_client(config: Settings) -> OidcClient | None:
    """Create the OIDC client, or ``None`` when OIDC is not configured.

    Discovery is lazy: no network call happens until the first login.

    Args:
        config: Application settings.

    Returns:
        A configured client, or ``None``.
    """
    if (
        not config.oidc_configured
        or config.authentik_issuer is None
        or config.authentik_client_id is None
        or config.authentik_client_secret is None
    ):
        return None
    # #ASSUME Authentik emits the configured groups claim in the ID token or
    # userinfo (spec "Authentik setup checklist", step 4); without it every
    # sign-in lands on the 403 page.
    # #VERIFY sign in as a member of each group and read the groups claim.
    oauth = OAuth()
    oauth.register(
        name=CLIENT_NAME,
        client_id=config.authentik_client_id,
        client_secret=config.authentik_client_secret.get_secret_value(),
        server_metadata_url=discovery_url(config.authentik_issuer),
        client_kwargs={"scope": SCOPE, "code_challenge_method": "S256"},
    )
    return cast("OidcClient", getattr(oauth, CLIENT_NAME))


def get_oidc_client(request: Request) -> OidcClient | None:
    """FastAPI dependency: the client stored on the app, if any.

    Args:
        request: The incoming request.

    Returns:
        The configured client, or ``None`` when OIDC is not configured.
    """
    return cast("OidcClient | None", getattr(request.app.state, "oidc_client", None))
````

- [ ] **Step 4: Implement the routes and the message page**

The callback exchanges the code first and clears the session only afterward (the state, nonce, and PKCE verifier live in it until then). `JoseError` covers a bad ID token, `OAuthError` a provider error or a state mismatch, and `httpx.HTTPError` an unreachable provider (503 page).

````python
"""Sign-in, callback and sign-out routes, mounted at ``/auth``."""

from typing import Annotated, Any, cast

import httpx
from authlib.integrations.base_client import OAuthError  # pyright: ignore[reportMissingTypeStubs]
from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from joserfc.errors import JoseError

from llc_manager.auth.csrf import verify_csrf
from llc_manager.auth.dependencies import current_user
from llc_manager.auth.oidc import OidcClient, get_oidc_client, redirect_uri
from llc_manager.auth.redirects import safe_next
from llc_manager.auth.roles import resolve_role
from llc_manager.auth.session import SessionUser, store_user
from llc_manager.core.config import settings
from llc_manager.core.templates import templates
from llc_manager.middleware.correlation import get_correlation_id
from llc_manager.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"], include_in_schema=False)

_LOGIN_NEXT_KEY = "login_next"

OidcDep = Annotated[OidcClient | None, Depends(get_oidc_client)]


def _message(
    request: Request,
    *,
    title: str,
    message: str,
    status_code: int,
    show_login: bool = False,
) -> HTMLResponse:
    """Render the standalone message page."""
    return templates.TemplateResponse(
        request,
        "auth/message.html",
        {
            "title": title,
            "message": message,
            "show_login": show_login,
            "show_local_login": settings.local_admin_enabled
            and settings.local_admin_password_hash is not None,
        },
        status_code=status_code,
    )


def _provider_unreachable(request: Request, exc: httpx.HTTPError) -> HTMLResponse:
    """Log and render the page shown when Authentik cannot be reached."""
    logger.warning(
        "oidc_provider_unreachable",
        error=type(exc).__name__,
        correlation_id=get_correlation_id(),
    )
    return _message(
        request,
        title="Sign-in is temporarily unavailable",
        message="The sign-in service could not be reached. Try again shortly.",
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        show_login=True,
    )


@router.get("/login")
async def login(
    request: Request,
    oidc: OidcDep,
    next_: Annotated[str | None, Query(alias="next")] = None,
) -> Response:
    """Start the Authentik sign-in, remembering where to return to.

    Args:
        request: The incoming request.
        oidc: The configured OIDC client, if any.
        next_: Relative path to return to after sign-in.

    Returns:
        A redirect to Authentik, or a message page when sign-in is unavailable.
    """
    target = safe_next(next_)
    if current_user(request) is not None:
        return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)
    if oidc is None:
        return _message(
            request,
            title="Sign-in unavailable",
            message="Single sign-on is not configured for this site.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    request.session[_LOGIN_NEXT_KEY] = target
    try:
        return await oidc.authorize_redirect(
            request, redirect_uri(settings.public_base_url or "")
        )
    except httpx.HTTPError as exc:
        # Discovery is fetched lazily, so an outage first shows up here.
        return _provider_unreachable(request, exc)


@router.get("/callback")
async def callback(request: Request, oidc: OidcDep) -> Response:
    """Finish the sign-in: validate the ID token and start the session.

    Args:
        request: The incoming request.
        oidc: The configured OIDC client, if any.

    Returns:
        A redirect to the requested page, or an error message page.
    """
    if oidc is None:
        return _message(
            request,
            title="Sign-in unavailable",
            message="Single sign-on is not configured for this site.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    # The login state lives in the session, so it is read now and the session
    # is only replaced after the token exchange has used it.
    target = safe_next(request.session.get(_LOGIN_NEXT_KEY))
    try:
        token = await oidc.authorize_access_token(request)
    except httpx.HTTPError as exc:
        return _provider_unreachable(request, exc)
    except (OAuthError, JoseError) as exc:
        logger.warning(
            "oidc_callback_rejected",
            error=type(exc).__name__,
            correlation_id=get_correlation_id(),
        )
        return _message(
            request,
            title="Sign-in failed",
            message="The sign-in response could not be verified. Please try again.",
            status_code=status.HTTP_400_BAD_REQUEST,
            show_login=True,
        )

    raw_claims = token.get("userinfo")
    claims = (
        cast("dict[str, Any]", raw_claims) if isinstance(raw_claims, dict) else None
    )
    if claims is None or not claims.get("sub"):
        logger.warning(
            "oidc_callback_without_identity",
            correlation_id=get_correlation_id(),
        )
        return _message(
            request,
            title="Sign-in failed",
            message="The sign-in response did not identify a user.",
            status_code=status.HTTP_400_BAD_REQUEST,
            show_login=True,
        )

    role = resolve_role(
        claims,
        groups_claim=settings.authentik_groups_claim,
        admin_group=settings.admin_group,
        viewer_group=settings.viewer_group,
    )
    if role is None:
        logger.warning(
            "oidc_user_without_role",
            sub=str(claims["sub"]),
            correlation_id=get_correlation_id(),
        )
        request.session.clear()
        return _message(
            request,
            title="Access denied",
            message=(
                "Your account is not a member of a group that may use "
                "LLC Manager. Ask an administrator to add you."
            ),
            status_code=status.HTTP_403_FORBIDDEN,
        )

    name = claims.get("name") or claims.get("preferred_username")
    store_user(
        request.session,
        SessionUser(
            sub=str(claims["sub"]),
            email=claims.get("email"),
            name=name,
            role=role,
            auth_method="oidc",
        ),
        max_age=settings.session_max_age_seconds,
    )
    logger.info(
        "login_succeeded",
        method="oidc",
        sub=str(claims["sub"]),
        role=role.value,
        correlation_id=get_correlation_id(),
    )
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout", dependencies=[Depends(verify_csrf)])
async def logout(request: Request) -> Response:
    """End the local session.

    The Authentik session is not ended, so the next sign-in may be silent.

    Args:
        request: The incoming request.

    Returns:
        A message page confirming sign-out.
    """
    request.session.clear()
    return _message(
        request,
        title="Signed out",
        message="You have been signed out of LLC Manager.",
        status_code=status.HTTP_200_OK,
        show_login=True,
    )
````

````html
<!DOCTYPE html>
<html lang="en" class="h-full">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{{ title }} | LLC Manager</title>
  <link rel="stylesheet" href="/static/css/output.css" />
</head>
<body class="h-full bg-gray-50">
  <main class="mx-auto max-w-md px-4 py-16">
    <h1 class="text-xl font-semibold text-gray-900">{{ title }}</h1>
    <p class="mt-3 text-sm text-gray-700">{{ message }}</p>
    <div class="mt-6 flex gap-4 text-sm">
      {% if show_login %}<a class="text-brand-600 underline" href="/auth/login">Sign in</a>{% endif %}
      {% if show_local_login %}<a class="text-brand-600 underline" href="/auth/local-login">Use the local administrator login</a>{% endif %}
    </div>
  </main>
</body>
</html>
````

- [ ] **Step 5: Wire the middleware and router into the app**

`SessionMiddleware` is added after the existing middleware so that it wraps them. The cookie is `Secure` whenever `public_base_url` is `https://`, so plain-HTTP local runs and the test client still work. No route gets a gate here.

````diff
--- a/src/llc_manager/main.py
+++ b/src/llc_manager/main.py
@@ -7,10 +7,14 @@
 from fastapi import FastAPI
 from fastapi.middleware.cors import CORSMiddleware
 from fastapi.staticfiles import StaticFiles
+from starlette.middleware.sessions import SessionMiddleware

 from llc_manager.api.health import router as health_router
 from llc_manager.api.ui import router as ui_router
 from llc_manager.api.v1 import router as v1_router
+from llc_manager.auth.oidc import build_oidc_client
+from llc_manager.auth.routes import router as auth_router
+from llc_manager.auth.session import SESSION_COOKIE
 from llc_manager.core.config import settings
 from llc_manager.middleware.correlation import CorrelationMiddleware
 from llc_manager.middleware.security import (
@@ -42,6 +46,11 @@
             "api_key_not_configured",
             effect="every /api/v1 request is refused with 503",
         )
+    if settings.auth_dev_mode:
+        logger.warning(
+            "auth_dev_mode_enabled",
+            effect="every web request is treated as a signed-in administrator",
+        )
     yield
     # Shutdown

@@ -104,9 +113,24 @@
     app.add_middleware(RateLimitMiddleware)
     app.add_middleware(SSRFPreventionMiddleware)

+    # Cookie session for the browser UI. Added after the middleware above so it
+    # wraps them, and the cookie is Secure whenever the public URL is https.
+    # #ASSUME the site is served over https in production (enforced by the
+    # public_base_url validator). #VERIFY the cookie carries the Secure flag.
+    app.add_middleware(
+        SessionMiddleware,
+        secret_key=settings.secret_key,
+        session_cookie=SESSION_COOKIE,
+        max_age=settings.session_max_age_seconds,
+        same_site="lax",
+        https_only=(settings.public_base_url or "").startswith("https://"),
+    )
+    app.state.oidc_client = build_oidc_client(settings)
+
     # Include routers
     app.include_router(health_router, prefix="/api", tags=["Health"])
     app.include_router(v1_router, prefix="/api/v1")
+    app.include_router(auth_router)
     app.include_router(ui_router)
     app.include_router(web_router)
````

- [ ] **Step 6: Run the tests and see them pass**

```bash
uv run pytest tests/unit/test_auth_oidc_flow.py tests/unit/test_auth_wiring.py -v -o addopts=""
```

Expected: `35 passed` (28 in the flow file, 7 in the wiring file). The `AuthlibDeprecationWarning` about `httpx` is expected and harmless.

- [ ] **Step 7: Prove nothing else changed**

```bash
uv run pytest tests/unit/test_auth_settings.py::TestUnconfiguredProductionIsUnchanged tests/unit/test_auth_wiring.py::test_web_routes_are_still_open tests/unit/test_web_entities.py -v -o addopts=""
```

Expected: all pass. `test_web_routes_are_still_open` is the proof that PR 2 gates no page.

- [ ] **Step 8: Commit**

```bash
git add src/llc_manager/auth/oidc.py src/llc_manager/auth/routes.py src/llc_manager/templates/auth/message.html src/llc_manager/main.py tests/oidc_fake.py tests/unit/test_auth_oidc_flow.py tests/unit/test_auth_wiring.py
git commit -S -m "feat(auth): add authentik oidc login, callback, and logout" -m "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

### Task 2.6: Finish PR 2

depends-on: Task 2.1 [completion], Task 2.2 [completion], Task 2.3 [completion], Task 2.4 [completion], Task 2.5 [completion]

- [ ] **Step 1: Add the changelog bullet under `## [Unreleased]`**

In `CHANGELOG.md`, replace this text:

````markdown
## [Unreleased]

### Added
````

with:

````markdown
## [Unreleased]

### Added

- `feat(auth)`: Authentik OIDC sign-in (authorization code with PKCE) at
  `/auth/login`, `/auth/callback`, and `/auth/logout`, with a signed-cookie
  session (`llc_session`), admin and viewer roles from group membership, a
  per-session CSRF token, and a dev mode (`auth_dev_mode`). The gates
  (`require_user`, `require_admin`, `verify_csrf`) are implemented and tested
  but not yet attached to the web routes.
````

- [ ] **Step 2: Run the whole suite with the repository defaults**

```bash
uv run pytest
```

Expected: all tests pass and coverage stays above 80 percent. The verification run had 700 passing with the Excel import tests excluded.

- [ ] **Step 3: Lint, type-check, and pre-commit**

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run basedpyright src/llc_manager/auth src/llc_manager/main.py
pre-commit run --files CHANGELOG.md src/llc_manager/main.py src/llc_manager/auth/__init__.py src/llc_manager/auth/csrf.py src/llc_manager/auth/dependencies.py src/llc_manager/auth/oidc.py src/llc_manager/auth/redirects.py src/llc_manager/auth/roles.py src/llc_manager/auth/routes.py src/llc_manager/auth/session.py src/llc_manager/templates/auth/message.html tests/auth_helpers.py tests/oidc_fake.py tests/unit/test_auth_gates.py tests/unit/test_auth_oidc_flow.py tests/unit/test_auth_redirects.py tests/unit/test_auth_roles.py tests/unit/test_auth_session.py tests/unit/test_auth_wiring.py
git status --short
```

Expected: `All checks passed!`, `0 errors` (warnings about the untyped `authlib` imports are not errors), and every hook passes. If `.secrets.baseline` changed, `git add` it and re-run the hook.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -S -m "docs(changelog): record the oidc login and session" -m "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

- [ ] **Step 5: Open the PR (orchestrator only)**

```bash
git push -u origin feat/auth-oidc-session
gh pr create --title "feat(auth): add authentik oidc login, session, roles, and csrf" --body "$(cat <<'EOF'
## Summary

- New `auth/` package: OIDC authorization code flow with PKCE, signed-cookie session with an absolute expiry, admin and viewer roles from group membership, per-session CSRF token, and a dev-mode user.
- `/auth/login`, `/auth/callback`, and `/auth/logout` are live. With no auth settings `/auth/login` answers 503.
- `require_user`, `require_admin`, and `verify_csrf` are tested but not attached to any web route, so no page behaves differently.

## Test plan

- [ ] `uv run pytest` passes
- [ ] OIDC flow tests use a fake in-memory provider; no network
- [ ] `test_web_routes_are_still_open` shows the web routes are unchanged

Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Not run by an implementer. depends-on: Task 2.6 Step 4 [completion].

## PR 3: break-glass login, throttle, proxy trust

Branch `feat/auth-break-glass`. Adds the second login path, which is off by default (404 unless the switch and a hash are both set), plus the proxy-header handling the throttle and the `Secure` cookie need behind Traefik. No gate is attached to the web routes, and an unconfigured production environment starts as before: an empty `trusted_proxy_ips` adds no middleware.

### Task 3.0: Worktree for PR 3

depends-on: PR 2 merged to `main`

- [ ] **Step 1: Create the worktree from the updated `main`**

```bash
cd /home/byron/dev/llc-manager
git fetch origin
git worktree add .worktrees/auth-break-glass -b feat/auth-break-glass origin/main
cd .worktrees/auth-break-glass
uv sync --all-extras
uv run pytest tests/unit/test_auth_oidc_flow.py tests/unit/test_auth_wiring.py -v -o addopts=""
```

Expected: `35 passed`. If PR 2 is not on `origin/main`, stop.

### Task 3.1: Failure throttle

depends-on: Task 3.0 [completion]

Files:

- Create: `src/llc_manager/auth/throttle.py`, `tests/unit/test_auth_throttle.py`

A sliding window: 5 failures per 900 seconds per client, memory bounded at 10,000 clients. State is per process, so with the two replicas that `docker-compose.prod.yml` defaults to, the effective limit is per replica.

- [ ] **Step 1: Write the failing tests**

````python
"""Tests for the break-glass failure throttle."""

import pytest

from llc_manager.auth.throttle import LoginThrottle


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> _Clock:
    return _Clock()


@pytest.fixture
def throttle(clock: _Clock) -> LoginThrottle:
    return LoginThrottle(max_failures=5, window_seconds=900, clock=clock)


def _fail(throttle: LoginThrottle, key: str, times: int) -> None:
    for _ in range(times):
        throttle.record_failure(key)


def test_blocks_on_the_fifth_failure(throttle: LoginThrottle) -> None:
    _fail(throttle, "1.2.3.4", 4)
    assert not throttle.is_blocked("1.2.3.4")

    throttle.record_failure("1.2.3.4")

    assert throttle.is_blocked("1.2.3.4")


def test_clients_are_tracked_separately(throttle: LoginThrottle) -> None:
    _fail(throttle, "1.2.3.4", 5)

    assert throttle.is_blocked("1.2.3.4")
    assert not throttle.is_blocked("5.6.7.8")


def test_failures_expire_after_the_window(
    throttle: LoginThrottle, clock: _Clock
) -> None:
    _fail(throttle, "1.2.3.4", 5)
    clock.now += 899
    assert throttle.is_blocked("1.2.3.4")

    clock.now += 2

    assert not throttle.is_blocked("1.2.3.4")


def test_window_slides_rather_than_resetting(
    throttle: LoginThrottle, clock: _Clock
) -> None:
    _fail(throttle, "k", 3)
    clock.now += 600
    _fail(throttle, "k", 2)
    assert throttle.is_blocked("k")

    clock.now += 301  # the first three age out, the last two remain

    assert not throttle.is_blocked("k")
    _fail(throttle, "k", 3)
    assert throttle.is_blocked("k")


def test_reset_forgets_the_client(throttle: LoginThrottle) -> None:
    _fail(throttle, "k", 5)

    throttle.reset("k")

    assert not throttle.is_blocked("k")
    throttle.reset("never-seen")  # must not raise


def test_retry_after_counts_down(throttle: LoginThrottle, clock: _Clock) -> None:
    assert throttle.retry_after("k") == 0
    _fail(throttle, "k", 5)
    assert throttle.retry_after("k") == 901

    clock.now += 600

    assert throttle.retry_after("k") == 301


def test_memory_is_bounded(clock: _Clock) -> None:
    small = LoginThrottle(max_failures=1, max_tracked=3, clock=clock)
    for index in range(10):
        small.record_failure(f"client-{index}")

    assert small.is_blocked("client-9")
    assert not small.is_blocked("client-0")
    assert small.tracked_clients == 3
````

- [ ] **Step 2: Run them and see them fail**

```bash
uv run pytest tests/unit/test_auth_throttle.py -v -o addopts=""
```

Expected: `ModuleNotFoundError: No module named 'llc_manager.auth.throttle'`.

- [ ] **Step 3: Implement**

````python
"""Failure throttle for the break-glass login."""

import time
from collections import OrderedDict, deque
from collections.abc import Callable

DEFAULT_MAX_FAILURES = 5
DEFAULT_WINDOW_SECONDS = 15 * 60
DEFAULT_MAX_TRACKED = 10_000


class LoginThrottle:
    """Block a client after too many failed attempts in a sliding window.

    State is held in process memory. #ASSUME the app runs a single worker
    (``api_workers`` defaults to 1), so one process sees every attempt.
    #VERIFY raise the worker count only together with a shared store.
    """

    def __init__(
        self,
        *,
        max_failures: int = DEFAULT_MAX_FAILURES,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        max_tracked: int = DEFAULT_MAX_TRACKED,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Create a throttle.

        Args:
            max_failures: Failures within the window that trigger a block.
            window_seconds: Length of the sliding window.
            max_tracked: Most distinct clients remembered; the least recently
                active client is forgotten first, which bounds memory.
            clock: Monotonic time source (injectable for tests).
        """
        self._max_failures = max_failures
        self._window = window_seconds
        self._max_tracked = max_tracked
        self._clock = clock
        self._failures: OrderedDict[str, deque[float]] = OrderedDict()

    @property
    def tracked_clients(self) -> int:
        """How many distinct clients currently have recorded failures."""
        return len(self._failures)

    def _recent(self, key: str) -> deque[float]:
        """Return the client's failures inside the window, pruning old ones."""
        failures = self._failures.get(key)
        if failures is None:
            return deque()
        cutoff = self._clock() - self._window
        while failures and failures[0] <= cutoff:
            failures.popleft()
        if not failures:
            del self._failures[key]
            return deque()
        return failures

    def is_blocked(self, key: str) -> bool:
        """Whether the client has used up its failures.

        Args:
            key: Client identifier, normally the IP address.

        Returns:
            True when the client must not be allowed another attempt.
        """
        return len(self._recent(key)) >= self._max_failures

    def retry_after(self, key: str) -> int:
        """Seconds until the oldest counted failure leaves the window.

        Args:
            key: Client identifier.

        Returns:
            Whole seconds to wait, at least 1 while blocked, else 0.
        """
        failures = self._recent(key)
        if len(failures) < self._max_failures:
            return 0
        remaining = failures[0] + self._window - self._clock()
        return max(1, int(remaining) + 1)

    def record_failure(self, key: str) -> None:
        """Count a failed attempt.

        Args:
            key: Client identifier.
        """
        failures = self._recent(key)
        failures.append(self._clock())
        self._failures[key] = failures
        self._failures.move_to_end(key)
        while len(self._failures) > self._max_tracked:
            self._failures.popitem(last=False)

    def reset(self, key: str) -> None:
        """Forget a client's failures, after a successful login.

        Args:
            key: Client identifier.
        """
        self._failures.pop(key, None)
````

- [ ] **Step 4: Run the tests and see them pass**

```bash
uv run pytest tests/unit/test_auth_throttle.py -v -o addopts=""
```

Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/llc_manager/auth/throttle.py tests/unit/test_auth_throttle.py
git commit -S -m "feat(auth): add a sliding-window login failure throttle" -m "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

### Task 3.2: Break-glass login route

depends-on: Task 3.1 [output: `LoginThrottle`]

Files:

- Create: `src/llc_manager/templates/auth/local_login.html`, `tests/unit/test_auth_break_glass.py`
- Modify: `src/llc_manager/auth/routes.py`, `src/llc_manager/main.py`

`GET` and `POST /auth/local-login` answer 404 unless `local_admin_enabled` is true and a hash is set. The password is verified with argon2 off the event loop; a corrupt stored hash fails closed. The sixth attempt in the window gets 429 even with the right password. Every attempt is logged at WARNING with the client IP and correlation ID, and the password is never logged. The Authentik outage page (PR 2) already links to the form only when it is enabled; until this PR that link would point at a missing route, and it starts working here.

- [ ] **Step 1: Write the failing tests**

````python
"""Tests for the break-glass login at /auth/local-login."""

from collections.abc import Iterator
from typing import TYPE_CHECKING, cast

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from pydantic import SecretStr

from llc_manager.auth.session import SESSION_COOKIE
from llc_manager.core.config import settings
from llc_manager.main import create_app
from tests.auth_helpers import decode_session_cookie

if TYPE_CHECKING:
    from fastapi import FastAPI

PASSWORD = "correct horse battery staple"  # pragma: allowlist secret
# Cheap parameters keep the suite fast; verify() reads them from the hash.
_HASH = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(PASSWORD)
BASE_URL = "https://llc.example.test"


@pytest.fixture
def enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "public_base_url", BASE_URL)
    monkeypatch.setattr(settings, "local_admin_enabled", True)
    monkeypatch.setattr(settings, "local_admin_password_hash", SecretStr(_HASH))


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(
        create_app(), base_url=BASE_URL, follow_redirects=False
    ) as test_client:
        yield test_client


def _token(client: TestClient, path: str = "/auth/local-login") -> str:
    """Load the form (which seeds the session token) and read the hidden field."""
    html = client.get(path).text
    marker = 'name="csrf_token" value="'
    start = html.index(marker) + len(marker)
    return html[start : html.index('"', start)]


def _submit(client: TestClient, password: str, token: str, next_: str = ""):
    data = {"password": password, "csrf_token": token}
    if next_:
        data["next"] = next_
    return client.post("/auth/local-login", data=data)


class TestDisabled:
    def test_get_is_404_by_default(self, client: TestClient) -> None:
        assert client.get("/auth/local-login").status_code == 404

    def test_post_is_404_before_csrf_is_even_checked(self, client: TestClient) -> None:
        assert (
            client.post("/auth/local-login", data={"password": "x"}).status_code == 404
        )

    def test_enabled_without_a_hash_is_still_404(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "local_admin_enabled", True)
        monkeypatch.setattr(settings, "local_admin_password_hash", None)

        assert client.get("/auth/local-login").status_code == 404

    def test_hash_without_the_switch_is_still_404(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "local_admin_enabled", False)
        monkeypatch.setattr(settings, "local_admin_password_hash", SecretStr(_HASH))

        assert client.get("/auth/local-login").status_code == 404


@pytest.mark.usefixtures("enabled")
class TestEnabled:
    def test_form_is_shown_with_a_csrf_token(self, client: TestClient) -> None:
        response = client.get("/auth/local-login")

        assert response.status_code == 200
        assert 'type="password"' in response.text
        assert _token(client)

    def test_correct_password_signs_in_as_admin(self, client: TestClient) -> None:
        token = _token(client)

        response = _submit(client, PASSWORD, token, next_="/entities/3")

        assert response.status_code == 303
        assert response.headers["location"] == "/entities/3"
        session = decode_session_cookie(
            settings.secret_key, client.cookies[SESSION_COOKIE]
        )
        assert session["user"]["role"] == "admin"
        assert session["user"]["auth_method"] == "local"
        assert session["csrf"] != token  # rotated on login

    def test_unsafe_next_is_replaced(self, client: TestClient) -> None:
        response = _submit(client, PASSWORD, _token(client), next_="//evil.example")

        assert response.headers["location"] == "/entities"

    def test_wrong_password_is_rejected(self, client: TestClient) -> None:
        response = _submit(client, "wrong", _token(client))

        assert response.status_code == 401
        assert "not correct" in response.text
        assert "user" not in decode_session_cookie(
            settings.secret_key, client.cookies[SESSION_COOKIE]
        )

    def test_missing_csrf_token_is_rejected(self, client: TestClient) -> None:
        _token(client)

        response = client.post("/auth/local-login", data={"password": PASSWORD})

        assert response.status_code == 403

    def test_corrupt_stored_hash_fails_closed(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            settings, "local_admin_password_hash", SecretStr("not-an-argon2-hash")
        )

        response = _submit(client, PASSWORD, _token(client))

        assert response.status_code == 401

    def test_signed_in_user_is_sent_on(self, client: TestClient) -> None:
        _submit(client, PASSWORD, _token(client))

        response = client.get("/auth/local-login?next=/entities/9")

        assert response.status_code == 303
        assert response.headers["location"] == "/entities/9"


@pytest.mark.usefixtures("enabled")
class TestRateLimit:
    def test_sixth_attempt_is_throttled_even_with_the_right_password(
        self, client: TestClient
    ) -> None:
        token = _token(client)
        for _ in range(5):
            assert _submit(client, "wrong", token).status_code == 401

        response = _submit(client, PASSWORD, token)

        assert response.status_code == 429
        assert int(response.headers["retry-after"]) > 0
        assert "user" not in client.cookies.get(SESSION_COOKIE, "")

    def test_throttle_is_per_client_ip(self) -> None:
        app = create_app()
        with TestClient(
            app, base_url=BASE_URL, follow_redirects=False, client=("10.0.0.1", 1)
        ) as first:
            token = _token(first)
            for _ in range(5):
                _submit(first, "wrong", token)
            assert _submit(first, PASSWORD, token).status_code == 429
        with TestClient(
            app, base_url=BASE_URL, follow_redirects=False, client=("10.0.0.2", 1)
        ) as second:
            assert _submit(second, PASSWORD, _token(second)).status_code == 303

    def test_success_clears_earlier_failures(self, client: TestClient) -> None:
        # Kept under the app-wide burst limit (10 requests per second).
        token = _token(client)
        for _ in range(3):
            _submit(client, "wrong", token)
        assert _submit(client, PASSWORD, token).status_code == 303

        client.cookies.clear()
        token = _token(client)
        for _ in range(3):  # 3 + 3 > 5, so only a reset keeps these at 401
            assert _submit(client, "wrong", token).status_code == 401


@pytest.mark.usefixtures("enabled")
class TestLogging:
    def test_every_attempt_is_logged_at_warning(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        token = _token(client)
        caplog.set_level("WARNING")

        _submit(client, "wrong", token)
        _submit(client, PASSWORD, token)

        records = [r for r in caplog.records if r.name == "llc_manager.auth.routes"]
        text = " ".join(r.getMessage() for r in records)
        assert "local_login_failed" in text
        assert "local_login_succeeded" in text
        assert all(r.levelname == "WARNING" for r in records)

    def test_passwords_are_never_logged(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("DEBUG")

        _submit(client, "wrong-password-marker", _token(client))
        _submit(client, PASSWORD, _token(client))

        assert "wrong-password-marker" not in caplog.text
        assert PASSWORD not in caplog.text
        assert _HASH not in caplog.text

    def test_throttled_attempts_are_logged(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        token = _token(client)
        for _ in range(5):
            _submit(client, "wrong", token)
        caplog.set_level("WARNING")

        _submit(client, "wrong", token)

        assert "local_login_throttled" in caplog.text


class TestOutagePageLink:
    def test_link_is_hidden_when_break_glass_is_off(self, client: TestClient) -> None:
        class _Down:
            async def authorize_redirect(self, *_a: object, **_k: object) -> None:
                import httpx

                raise httpx.ConnectError("down")

        cast("FastAPI", client.app).state.oidc_client = _Down()

        response = client.get("/auth/login")

        assert response.status_code == 503
        assert "/auth/local-login" not in response.text

    @pytest.mark.usefixtures("enabled")
    def test_link_is_shown_when_break_glass_is_on(self, client: TestClient) -> None:
        import httpx

        class _Down:
            async def authorize_redirect(self, *_a: object, **_k: object) -> None:
                raise httpx.ConnectError("down")

        cast("FastAPI", client.app).state.oidc_client = _Down()

        response = client.get("/auth/login")

        assert response.status_code == 503
        assert 'href="/auth/local-login"' in response.text
````

- [ ] **Step 2: Run them and see them fail**

```bash
uv run pytest tests/unit/test_auth_break_glass.py -v -o addopts=""
```

Expected: `13 failed, 6 passed`. The failures are `ValueError: substring not found` (the helper cannot find a CSRF token because the form page does not exist) and `assert 404 == 200`. The six that already pass are the "disabled gives 404" cases and the outage-page link tests.

- [ ] **Step 3: Add the form template**

````html
<!DOCTYPE html>
<html lang="en" class="h-full">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Administrator login | LLC Manager</title>
  <link rel="stylesheet" href="/static/css/output.css" />
</head>
<body class="h-full bg-gray-50">
  <main class="mx-auto max-w-md px-4 py-16">
    <h1 class="text-xl font-semibold text-gray-900">Administrator login</h1>
    <p class="mt-3 text-sm text-gray-700">
      Break-glass access for use when single sign-on is unavailable.
    </p>
    {% if error %}
    <p role="alert" class="mt-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{{ error }}</p>
    {% endif %}
    <form method="post" action="/auth/local-login" class="mt-6 space-y-4">
      <input type="hidden" name="csrf_token" value="{{ csrf_token }}" />
      <input type="hidden" name="next" value="{{ next }}" />
      <div>
        <label for="password" class="block text-sm font-medium text-gray-900">Password</label>
        <input id="password" name="password" type="password" required autocomplete="current-password"
               class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm" />
      </div>
      <button type="submit" class="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white">Sign in</button>
    </form>
  </main>
</body>
</html>
````

- [ ] **Step 4: Add the routes**

````diff
--- a/src/llc_manager/auth/routes.py
+++ b/src/llc_manager/auth/routes.py
@@ -3,8 +3,11 @@
 from typing import Annotated, Any, cast

 import httpx
+from argon2 import PasswordHasher
+from argon2.exceptions import InvalidHashError, VerificationError
 from authlib.integrations.base_client import OAuthError  # pyright: ignore[reportMissingTypeStubs]
-from fastapi import APIRouter, Depends, Query, Request, status
+from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
+from fastapi.concurrency import run_in_threadpool
 from fastapi.responses import HTMLResponse, RedirectResponse, Response
 from joserfc.errors import JoseError

@@ -12,8 +15,9 @@
 from llc_manager.auth.dependencies import current_user
 from llc_manager.auth.oidc import OidcClient, get_oidc_client, redirect_uri
 from llc_manager.auth.redirects import safe_next
-from llc_manager.auth.roles import resolve_role
-from llc_manager.auth.session import SessionUser, store_user
+from llc_manager.auth.roles import Role, resolve_role
+from llc_manager.auth.session import SessionUser, csrf_token, store_user
+from llc_manager.auth.throttle import LoginThrottle
 from llc_manager.core.config import settings
 from llc_manager.core.templates import templates
 from llc_manager.middleware.correlation import get_correlation_id
@@ -27,6 +31,52 @@

 OidcDep = Annotated[OidcClient | None, Depends(get_oidc_client)]

+LOCAL_ADMIN_SUB = "local-admin"
+_password_hasher = PasswordHasher()
+
+
+def get_login_throttle(request: Request) -> LoginThrottle:
+    """FastAPI dependency: the break-glass throttle stored on the app.
+
+    Args:
+        request: The incoming request.
+
+    Returns:
+        The app-wide throttle.
+    """
+    return cast("LoginThrottle", request.app.state.login_throttle)
+
+
+ThrottleDep = Annotated[LoginThrottle, Depends(get_login_throttle)]
+
+
+def require_local_login_enabled() -> None:
+    """Hide the break-glass login (404) unless it is enabled and has a hash.
+
+    Raises:
+        HTTPException: 404 when the break-glass login is not available.
+    """
+    if not (settings.local_admin_enabled and settings.local_admin_password_hash):
+        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
+
+
+def _client_ip(request: Request) -> str:
+    """The throttle key: the client address as seen after proxy handling."""
+    return request.client.host if request.client else "unknown"
+
+
+async def _password_matches(password: str) -> bool:
+    """Verify ``password`` against the configured argon2 hash off the loop."""
+    stored = settings.local_admin_password_hash
+    if stored is None:
+        return False
+    try:
+        return await run_in_threadpool(
+            _password_hasher.verify, stored.get_secret_value(), password
+        )
+    except (VerificationError, InvalidHashError):
+        return False
+

 def _message(
     request: Request,
@@ -224,3 +274,117 @@
         status_code=status.HTTP_200_OK,
         show_login=True,
     )
+
+
+def _local_login_form(
+    request: Request,
+    *,
+    next_: str,
+    error: str | None = None,
+    status_code: int = status.HTTP_200_OK,
+) -> HTMLResponse:
+    """Render the break-glass form, seeding a CSRF token in the session."""
+    return templates.TemplateResponse(
+        request,
+        "auth/local_login.html",
+        {"csrf_token": csrf_token(request.session), "next": next_, "error": error},
+        status_code=status_code,
+    )
+
+
+@router.get("/local-login", dependencies=[Depends(require_local_login_enabled)])
+async def local_login_form(
+    request: Request,
+    next_: Annotated[str | None, Query(alias="next")] = None,
+) -> Response:
+    """Show the break-glass login form.
+
+    Args:
+        request: The incoming request.
+        next_: Relative path to return to after sign-in.
+
+    Returns:
+        The login form, or a redirect when already signed in.
+    """
+    target = safe_next(next_)
+    if current_user(request) is not None:
+        return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)
+    return _local_login_form(request, next_=target)
+
+
+@router.post(
+    "/local-login",
+    dependencies=[Depends(require_local_login_enabled), Depends(verify_csrf)],
+)
+async def local_login_submit(
+    request: Request,
+    throttle: ThrottleDep,
+    password: Annotated[str, Form()],
+    next_: Annotated[str | None, Form(alias="next")] = None,
+) -> Response:
+    """Check the break-glass password and start an administrator session.
+
+    #CRITICAL this is a second login path; it stays off by default, uses an
+    argon2 hash, is throttled per client IP, and logs every attempt.
+    #VERIFY ``tests/unit/test_auth_break_glass.py`` covers each of those.
+
+    Args:
+        request: The incoming request.
+        throttle: The failure throttle.
+        password: The submitted password.
+        next_: Relative path to return to after sign-in.
+
+    Returns:
+        A redirect on success, else the form again (401) or a throttle page (429).
+    """
+    target = safe_next(next_)
+    client_ip = _client_ip(request)
+    correlation_id = get_correlation_id()
+
+    if throttle.is_blocked(client_ip):
+        logger.warning(
+            "local_login_throttled",
+            client_ip=client_ip,
+            correlation_id=correlation_id,
+        )
+        response = _message(
+            request,
+            title="Too many attempts",
+            message="Too many failed attempts. Try again later.",
+            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
+        )
+        response.headers["Retry-After"] = str(throttle.retry_after(client_ip))
+        return response
+
+    if not await _password_matches(password):
+        throttle.record_failure(client_ip)
+        logger.warning(
+            "local_login_failed",
+            client_ip=client_ip,
+            correlation_id=correlation_id,
+        )
+        return _local_login_form(
+            request,
+            next_=target,
+            error="That password is not correct.",
+            status_code=status.HTTP_401_UNAUTHORIZED,
+        )
+
+    throttle.reset(client_ip)
+    store_user(
+        request.session,
+        SessionUser(
+            sub=LOCAL_ADMIN_SUB,
+            email=None,
+            name="Local administrator",
+            role=Role.ADMIN,
+            auth_method="local",
+        ),
+        max_age=settings.session_max_age_seconds,
+    )
+    logger.warning(
+        "local_login_succeeded",
+        client_ip=client_ip,
+        correlation_id=correlation_id,
+    )
+    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)
````

- [ ] **Step 5: Create the throttle on the app**

````diff
--- a/src/llc_manager/main.py
+++ b/src/llc_manager/main.py
@@ -15,6 +15,7 @@
 from llc_manager.auth.oidc import build_oidc_client
 from llc_manager.auth.routes import router as auth_router
 from llc_manager.auth.session import SESSION_COOKIE
+from llc_manager.auth.throttle import LoginThrottle
 from llc_manager.core.config import settings
 from llc_manager.middleware.correlation import CorrelationMiddleware
 from llc_manager.middleware.security import (
@@ -126,6 +127,7 @@
         https_only=(settings.public_base_url or "").startswith("https://"),
     )
     app.state.oidc_client = build_oidc_client(settings)
+    app.state.login_throttle = LoginThrottle()

     # Include routers
     app.include_router(health_router, prefix="/api", tags=["Health"])
````

- [ ] **Step 6: Run the tests and see them pass**

```bash
uv run pytest tests/unit/test_auth_break_glass.py -v -o addopts=""
```

Expected: `19 passed`.

- [ ] **Step 7: Commit**

```bash
git add src/llc_manager/auth/routes.py src/llc_manager/main.py src/llc_manager/templates/auth/local_login.html tests/unit/test_auth_break_glass.py
git commit -S -m "feat(auth): add the throttled break-glass admin login" -m "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

### Task 3.3: Proxy trust

depends-on: Task 3.2 [output: `app.state.login_throttle` in `main.py`]

Files:

- Create: `tests/unit/test_auth_proxy_trust.py`
- Modify: `src/llc_manager/main.py`

Behind Traefik the app would otherwise see `http` and the proxy address for every request, which breaks the `Secure` cookie logic and makes the throttle and the existing rate limiter treat all users as one client. The plan keeps the `Dockerfile` `CMD` unchanged and adds uvicorn's `ProxyHeadersMiddleware` as the outermost layer, only when `trusted_proxy_ips` is not empty (see "Verified facts", item 1).

- [ ] **Step 1: Write the failing tests**

````python
"""Tests for trusted-proxy handling of X-Forwarded-For and X-Forwarded-Proto."""

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from llc_manager.core.config import settings
from llc_manager.main import create_app

FORWARDED = {"X-Forwarded-For": "203.0.113.9", "X-Forwarded-Proto": "https"}


def _app_with_probe(monkeypatch: pytest.MonkeyPatch, trusted: list[str]):
    monkeypatch.setattr(settings, "trusted_proxy_ips", trusted)
    app = create_app()

    @app.get("/_whoami")
    async def whoami(request: Request) -> dict[str, str]:
        client = request.client.host if request.client else "none"
        return {"client": client, "scheme": request.url.scheme}

    return app


def _whoami(app, peer: str, headers: dict[str, str]) -> dict[str, str]:
    with TestClient(app, client=(peer, 5000)) as client:
        return client.get("/_whoami", headers=headers).json()


def test_forwarded_headers_are_honoured_from_a_trusted_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app_with_probe(monkeypatch, ["10.0.0.5"])

    assert _whoami(app, "10.0.0.5", FORWARDED) == {
        "client": "203.0.113.9",
        "scheme": "https",
    }


def test_cidr_ranges_are_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _app_with_probe(monkeypatch, ["172.18.0.0/16"])

    assert _whoami(app, "172.18.4.2", FORWARDED)["client"] == "203.0.113.9"


def test_forwarded_headers_are_ignored_from_an_untrusted_peer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app_with_probe(monkeypatch, ["10.0.0.5"])

    # A direct client cannot pick its own IP, which would defeat the throttle.
    assert _whoami(app, "198.51.100.7", FORWARDED) == {
        "client": "198.51.100.7",
        "scheme": "http",
    }


def test_nothing_is_trusted_when_the_list_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app_with_probe(monkeypatch, [])

    assert _whoami(app, "10.0.0.5", FORWARDED)["client"] == "10.0.0.5"


def test_spoofed_leftmost_entry_does_not_win(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _app_with_probe(monkeypatch, ["10.0.0.5"])
    headers = {"X-Forwarded-For": "1.1.1.1, 203.0.113.9", "X-Forwarded-Proto": "https"}

    # The proxy appended the real client; the caller-supplied prefix is not trusted.
    assert _whoami(app, "10.0.0.5", headers)["client"] == "203.0.113.9"


def test_break_glass_throttle_keys_on_the_forwarded_client_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argon2 import PasswordHasher
    from pydantic import SecretStr

    password_hash = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash("pw")
    monkeypatch.setattr(settings, "local_admin_enabled", True)
    monkeypatch.setattr(settings, "local_admin_password_hash", SecretStr(password_hash))
    app = _app_with_probe(monkeypatch, ["10.0.0.5"])

    def session_for(forwarded_for: str) -> tuple[TestClient, str]:
        client = TestClient(
            app,
            client=("10.0.0.5", 1),
            follow_redirects=False,
            headers={"X-Forwarded-For": forwarded_for},
        )
        page = client.get("/auth/local-login").text
        marker = 'name="csrf_token" value="'
        start = page.index(marker) + len(marker)
        return client, page[start : page.index('"', start)]

    def attempt(session: tuple[TestClient, str], password: str) -> int:
        client, token = session
        data = {"password": password, "csrf_token": token}
        return client.post("/auth/local-login", data=data).status_code

    first = session_for("203.0.113.9")
    for _ in range(5):
        assert attempt(first, "wrong") == 401
    assert attempt(first, "pw") == 429
    # A different user behind the same proxy is unaffected.
    assert attempt(session_for("203.0.113.10"), "pw") == 303
````

- [ ] **Step 2: Run them and see them fail**

```bash
uv run pytest tests/unit/test_auth_proxy_trust.py -v -o addopts=""
```

Expected: `4 failed, 2 passed`. The two that pass are the "nothing is trusted" cases, which hold before the change.

- [ ] **Step 3: Implement**

````diff
--- a/src/llc_manager/main.py
+++ b/src/llc_manager/main.py
@@ -8,6 +8,7 @@
 from fastapi.middleware.cors import CORSMiddleware
 from fastapi.staticfiles import StaticFiles
 from starlette.middleware.sessions import SessionMiddleware
+from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

 from llc_manager.api.health import router as health_router
 from llc_manager.api.ui import router as ui_router
@@ -129,6 +130,18 @@
     app.state.oidc_client = build_oidc_client(settings)
     app.state.login_throttle = LoginThrottle()

+    # Trust X-Forwarded-For/-Proto only from the configured proxies, so the
+    # client IP (throttle, rate limit) and scheme are the real ones behind
+    # Traefik. Added last so it is the outermost layer. When the list is empty
+    # nothing is added and uvicorn's own default (127.0.0.1 only) applies.
+    # #ASSUME the reverse proxy sets X-Forwarded-For and X-Forwarded-Proto.
+    # #VERIFY log request.url.scheme and the client IP from a real request.
+    if settings.trusted_proxy_ips:
+        app.add_middleware(
+            ProxyHeadersMiddleware,
+            trusted_hosts=settings.trusted_proxy_ips,
+        )
+
     # Include routers
     app.include_router(health_router, prefix="/api", tags=["Health"])
     app.include_router(v1_router, prefix="/api/v1")
````

- [ ] **Step 4: Run the tests and see them pass**

```bash
uv run pytest tests/unit/test_auth_proxy_trust.py -v -o addopts=""
```

Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/llc_manager/main.py tests/unit/test_auth_proxy_trust.py
git commit -S -m "feat(auth): trust forwarded headers only from configured proxies" -m "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

### Task 3.4: Finish PR 3

depends-on: Task 3.1 [completion], Task 3.2 [completion], Task 3.3 [completion]

- [ ] **Step 1: Add the changelog bullet under `## [Unreleased]`**

In `CHANGELOG.md`, replace this text:

````markdown
## [Unreleased]

### Added
````

with:

````markdown
## [Unreleased]

### Added

- `feat(auth)`: break-glass local admin login at `/auth/local-login` (404
  unless `local_admin_enabled` and an argon2 hash are set), limited to 5
  failures per 15 minutes per client IP, with every attempt logged at WARNING.
  The app trusts `X-Forwarded-For` and `X-Forwarded-Proto` only from the proxies
  listed in `trusted_proxy_ips`.
````

- [ ] **Step 2: Re-check the hard rule and run the whole suite**

```bash
uv run pytest tests/unit/test_auth_settings.py::TestUnconfiguredProductionIsUnchanged tests/unit/test_auth_wiring.py::test_web_routes_are_still_open -v -o addopts=""
uv run pytest
```

Expected: the two named tests pass, then the full suite passes with coverage above 80 percent. The verification run had 732 passing with the Excel import tests excluded.

- [ ] **Step 3: Lint, type-check, and pre-commit**

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run basedpyright src/llc_manager/auth src/llc_manager/main.py
pre-commit run --files CHANGELOG.md src/llc_manager/main.py src/llc_manager/auth/routes.py src/llc_manager/auth/throttle.py src/llc_manager/templates/auth/local_login.html tests/unit/test_auth_break_glass.py tests/unit/test_auth_proxy_trust.py tests/unit/test_auth_throttle.py
git status --short
```

Expected: `All checks passed!`, `0 errors`, every hook passes. If `.secrets.baseline` changed, `git add` it and re-run the hook.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -S -m "docs(changelog): record the break-glass login and proxy trust" -m "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

- [ ] **Step 5: Open the PR (orchestrator only)**

```bash
git push -u origin feat/auth-break-glass
gh pr create --title "feat(auth): add the break-glass admin login and proxy trust" --body "$(cat <<'EOF'
## Summary

- `/auth/local-login`: 404 unless `local_admin_enabled` and an argon2 hash are set; verified off the event loop; 5 failures per 15 minutes per client IP, then 429; every attempt logged at WARNING with the correlation ID.
- Forwarded headers are trusted only from `trusted_proxy_ips`. An empty list adds no middleware, so this PR does not change an unconfigured deployment.
- The Authentik outage page link added in PR 2 now leads to a working form.

No web route is gated by this PR.

## Test plan

- [ ] `uv run pytest` passes
- [ ] `test_web_routes_are_still_open` and `TestUnconfiguredProductionIsUnchanged` pass

Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Not run by an implementer. depends-on: Task 3.4 Step 4 [completion].

## PR 4: attach the gate, templates, production requirement, docs

Branch `feat/auth-gate-web`. This is the only PR that changes behavior for a deployed instance: every web page needs a session, editing needs the admin role and a CSRF token, and a non-development app refuses to start without a working sign-in method. Read "Deploy prerequisites for PR 4" before the orchestrator merges it.

### Task 4.0: Worktree for PR 4

depends-on: PR 3 merged to `main`

- [ ] **Step 1: Create the worktree from the updated `main`**

```bash
cd /home/byron/dev/llc-manager
git fetch origin
git worktree add .worktrees/auth-gate-web -b feat/auth-gate-web origin/main
cd .worktrees/auth-gate-web
uv sync --all-extras
uv run pytest tests/unit/test_auth_break_glass.py tests/unit/test_auth_proxy_trust.py tests/unit/test_auth_throttle.py -v -o addopts=""
```

Expected: `32 passed`. If PR 3 is not on `origin/main`, stop.

### Task 4.1: Production requires a sign-in method

depends-on: Task 4.0 [completion]

Files:

- Modify: `src/llc_manager/core/config.py`, `tests/auth_helpers.py`, `tests/unit/test_auth_settings.py`, `tests/unit/test_api_key_auth.py`, `tests/unit/test_security_audit_fixes.py`

Outside development, local, and test environments, startup now fails unless `public_base_url` is set and either the full Authentik settings or the break-glass login with its hash is configured. `TestUnconfiguredProductionIsUnchanged` from PR 1 becomes `TestProductionRequiresSignIn`: the hard rule has done its job and the rule it protected now flips. Three existing tests that build production `Settings` to check an unrelated rule call a new helper so that the sign-in requirement does not mask their result.

- [ ] **Step 1: Write the failing tests and the helper**

````diff
--- a/tests/auth_helpers.py
+++ b/tests/auth_helpers.py
@@ -6,6 +6,7 @@
 from typing import Any

 import itsdangerous
+import pytest

 from llc_manager.auth.session import SESSION_COOKIE

@@ -72,3 +73,21 @@
 def cookie_name() -> str:
     """Return the session cookie name used by the app."""
     return SESSION_COOKIE
+
+
+def configure_production_sign_in(monkeypatch: pytest.MonkeyPatch) -> None:
+    """Set the environment a valid production deployment needs to sign users in.
+
+    Tests that build ``Settings`` for a production environment to check some
+    other rule call this so the sign-in requirement does not mask the result.
+
+    Args:
+        monkeypatch: The pytest monkeypatch fixture.
+    """
+    monkeypatch.setenv("LLC_MANAGER_PUBLIC_BASE_URL", "https://llc.example.com")
+    monkeypatch.setenv(
+        "LLC_MANAGER_AUTHENTIK_ISSUER",
+        "https://auth.example.com/application/o/llc-manager/",
+    )
+    monkeypatch.setenv("LLC_MANAGER_AUTHENTIK_CLIENT_ID", "llc-manager")
+    monkeypatch.setenv("LLC_MANAGER_AUTHENTIK_CLIENT_SECRET", "client-secret-value")
````

````diff
--- a/tests/unit/test_auth_settings.py
+++ b/tests/unit/test_auth_settings.py
@@ -102,15 +102,65 @@
             Settings(_env_file=None)


-class TestUnconfiguredProductionIsUnchanged:
-    """PR 1 to 3 must not change startup for a production host with no auth set."""
+class TestProductionRequiresSignIn:
+    """Outside development the gated UI needs a way to sign in (fails closed)."""

-    def test_production_without_any_auth_setting_starts(self, production: None) -> None:
+    def test_production_without_any_auth_setting_is_refused(
+        self, production: None
+    ) -> None:
+        with pytest.raises(ConfigurationError, match="PUBLIC_BASE_URL") as excinfo:
+            Settings(_env_file=None)
+
+        assert "AUTHENTIK_ISSUER" in str(excinfo.value)
+
+    def test_development_without_any_auth_setting_starts(self) -> None:
         s = Settings(_env_file=None)
+
         assert s.oidc_configured is False
         assert s.local_admin_enabled is False
         assert s.auth_dev_mode is False

+    def test_complete_oidc_is_enough(
+        self, monkeypatch: pytest.MonkeyPatch, production: None
+    ) -> None:
+        _oidc_env(monkeypatch)
+
+        assert Settings(_env_file=None).oidc_configured is True
+
+    def test_break_glass_alone_is_enough(
+        self, monkeypatch: pytest.MonkeyPatch, production: None
+    ) -> None:
+        monkeypatch.setenv("LLC_MANAGER_PUBLIC_BASE_URL", "https://llc.example.com")
+        monkeypatch.setenv("LLC_MANAGER_LOCAL_ADMIN_ENABLED", "true")
+        monkeypatch.setenv("LLC_MANAGER_LOCAL_ADMIN_PASSWORD_HASH", ARGON2_HASH)
+
+        assert Settings(_env_file=None).local_admin_enabled is True
+
+    def test_public_base_url_is_required_even_with_oidc_pieces_missing_it(
+        self, monkeypatch: pytest.MonkeyPatch, production: None
+    ) -> None:
+        monkeypatch.setenv("LLC_MANAGER_LOCAL_ADMIN_ENABLED", "true")
+        monkeypatch.setenv("LLC_MANAGER_LOCAL_ADMIN_PASSWORD_HASH", ARGON2_HASH)
+
+        with pytest.raises(ConfigurationError, match="PUBLIC_BASE_URL"):
+            Settings(_env_file=None)
+
+    def test_public_base_url_alone_is_not_enough(
+        self, monkeypatch: pytest.MonkeyPatch, production: None
+    ) -> None:
+        monkeypatch.setenv("LLC_MANAGER_PUBLIC_BASE_URL", "https://llc.example.com")
+
+        with pytest.raises(ConfigurationError, match="AUTHENTIK_ISSUER"):
+            Settings(_env_file=None)
+
+    def test_dev_mode_does_not_satisfy_the_requirement(
+        self, monkeypatch: pytest.MonkeyPatch, production: None
+    ) -> None:
+        monkeypatch.setenv("LLC_MANAGER_AUTH_DEV_MODE", "true")
+
+        with pytest.raises(ConfigurationError):
+            Settings(_env_file=None)
+

 class TestOidcConsistency:
     def test_complete_oidc_settings_are_accepted(
@@ -217,6 +267,7 @@
     def test_enabled_with_argon2_hash_is_accepted(
         self, monkeypatch: pytest.MonkeyPatch, production: None
     ) -> None:
+        monkeypatch.setenv("LLC_MANAGER_PUBLIC_BASE_URL", "https://llc.example.com")
         monkeypatch.setenv("LLC_MANAGER_LOCAL_ADMIN_ENABLED", "true")
         monkeypatch.setenv("LLC_MANAGER_LOCAL_ADMIN_PASSWORD_HASH", ARGON2_HASH)
         s = Settings(_env_file=None)
````

````diff
--- a/tests/unit/test_api_key_auth.py
+++ b/tests/unit/test_api_key_auth.py
@@ -14,7 +14,7 @@
 from llc_manager.core.config import Settings, settings
 from llc_manager.core.exceptions import ConfigurationError
 from llc_manager.main import create_app
-from tests.auth_helpers import TEST_API_KEY
+from tests.auth_helpers import TEST_API_KEY, configure_production_sign_in

 if TYPE_CHECKING:
     from collections.abc import Iterator
@@ -125,6 +125,7 @@
         monkeypatch.setenv("LLC_MANAGER_ENVIRONMENT", "production")
         monkeypatch.setenv("LLC_MANAGER_SECRET_KEY", "s" * 40)
         monkeypatch.setenv("LLC_MANAGER_API_KEY", "k" * 40)
+        configure_production_sign_in(monkeypatch)
         assert Settings().api_key is not None

     def test_short_key_allowed_in_test(self, monkeypatch: pytest.MonkeyPatch) -> None:
@@ -144,6 +145,7 @@
         monkeypatch.setenv("LLC_MANAGER_ENVIRONMENT", "production")
         monkeypatch.setenv("LLC_MANAGER_SECRET_KEY", "s" * 40)
         monkeypatch.setenv("LLC_MANAGER_API_KEY", "")
+        configure_production_sign_in(monkeypatch)
         assert Settings(_env_file=None).api_key is None

     def test_service_api_key_name_is_accepted(
````

````diff
--- a/tests/unit/test_security_audit_fixes.py
+++ b/tests/unit/test_security_audit_fixes.py
@@ -6,6 +6,7 @@

 from llc_manager.core.config import Settings
 from llc_manager.core.exceptions import ConfigurationError
+from tests.auth_helpers import configure_production_sign_in


 class TestSecretKeyMinLength:
@@ -29,6 +30,7 @@
         monkeypatch.setenv("ENVIRONMENT", "production")
         # 64 chars - well above the 32-char minimum
         long_key = "a" * 64
+        configure_production_sign_in(monkeypatch)
         settings = Settings(secret_key=long_key)  # type: ignore[call-arg]
         assert settings.secret_key == long_key
````

- [ ] **Step 2: Run them and see them fail**

```bash
uv run pytest tests/unit/test_auth_settings.py tests/unit/test_api_key_auth.py tests/unit/test_security_audit_fixes.py -v -o addopts=""
```

Expected: `3 failed, 69 passed`. The failures are `Failed: DID NOT RAISE` for the production cases that must now be refused.

- [ ] **Step 3: Implement the validator**

````diff
--- a/src/llc_manager/core/config.py
+++ b/src/llc_manager/core/config.py
@@ -508,6 +508,45 @@
                 raise ConfigurationError(message, details={"config_key": key})
         return self

+    @model_validator(mode="after")
+    def _require_a_sign_in_method_outside_development(self) -> "Settings":
+        """Refuse to start a non-development app that nobody could sign in to.
+
+        The web UI is gated, so outside development, local, and test
+        environments the app needs ``public_base_url`` and either a complete
+        Authentik configuration or the break-glass login with its hash.
+
+        Returns:
+            Settings: The validated settings.
+
+        Raises:
+            ConfigurationError: If the sign-in configuration is missing.
+        """
+        # #CRITICAL: Security - fail closed. Without this the gated UI would
+        # start and answer every page with a redirect to a login that cannot work.
+        # #VERIFY: tests/unit/test_auth_settings.py covers each missing piece.
+        if _is_development_environment():
+            return self
+        break_glass = (
+            self.local_admin_enabled and self.local_admin_password_hash is not None
+        )
+        missing: list[str] = []
+        if self.public_base_url is None:
+            missing.append("LLC_MANAGER_PUBLIC_BASE_URL")
+        if not self.oidc_configured and not break_glass:
+            missing.append(
+                "LLC_MANAGER_AUTHENTIK_ISSUER, LLC_MANAGER_AUTHENTIK_CLIENT_ID and "
+                "LLC_MANAGER_AUTHENTIK_CLIENT_SECRET (or LLC_MANAGER_LOCAL_ADMIN_ENABLED "
+                "with LLC_MANAGER_LOCAL_ADMIN_PASSWORD_HASH)"
+            )
+        if missing:
+            message = (
+                "The web UI requires sign-in outside development, local, and test "
+                "environments. Missing: " + "; ".join(missing) + "."
+            )
+            raise ConfigurationError(message, details={"config_key": "public_base_url"})
+        return self
+
     @computed_field  # type: ignore[prop-decorator]  # Pydantic pattern: decorator composition confuses pyright
     @property
     def database_url(self) -> str:
````

- [ ] **Step 4: Run the tests and see them pass**

```bash
uv run pytest tests/unit/test_auth_settings.py tests/unit/test_api_key_auth.py tests/unit/test_security_audit_fixes.py -v -o addopts=""
```

Expected: `72 passed`.

- [ ] **Step 5: Find any other test that builds production settings**

```bash
uv run pytest -o addopts="" -q --ignore=tests/unit/test_import_excel.py -x
```

Expected: pass. If a test outside the three above fails with `The web UI requires sign-in outside development, local, and test environments`, call `configure_production_sign_in(monkeypatch)` in it. The verification run found exactly the three listed above.

- [ ] **Step 6: Commit**

```bash
git add src/llc_manager/core/config.py tests/auth_helpers.py tests/unit/test_auth_settings.py tests/unit/test_api_key_auth.py tests/unit/test_security_audit_fixes.py
git commit -S -m "feat(auth)!: require a sign-in method outside development" -m "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

### Task 4.2: Attach the gate and update the templates

depends-on: Task 4.1 [completion]

Files:

- Create: `src/llc_manager/auth/templating.py`, `tests/unit/test_web_gating.py`
- Modify: `src/llc_manager/core/templates.py`, `src/llc_manager/api/ui.py`, `src/llc_manager/web/routes.py`, `src/llc_manager/templates/base.html`, `src/llc_manager/templates/entities/partials/detail_card.html`, `tests/unit/test_web_entities.py`, `tests/unit/test_auth_wiring.py`

The web router gets `require_user` and `verify_csrf` at router level, so a new route cannot be left open by forgetting a decorator. `GET` and `PATCH /entities/{entity_id}/edit` also get `require_admin`. `base.html` puts the CSRF token in `hx-headers` on `<body>`, shows the signed-in user with a logout form, and the detail card hides the edit button from viewers. `/api/v1` (`X-API-Key`), `/api/health/*`, `/auth/*`, the API docs, and `/static` stay open.

`src/llc_manager/api/ui.py` holds a seventh page route, `GET /` (the dashboard), that the spec did not count; it gets the same `require_user` dependency.

The route-enumeration test in `test_web_gating.py` is modeled on the existing check that every `/api/v1` operation declares the API key (`tests/unit/test_api_key_auth.py`). It flattens both the flat `APIRoute` list of FastAPI 0.138 (the version in `uv.lock`) and the private `_IncludedRouter` objects of newer releases, and it proves itself with a negative test (`test_enumeration_detects_an_ungated_route`).

- [ ] **Step 1: Write the failing tests**

````python
"""Every web route must be gated; behavior of the gates on the real routes.

The enumeration test is modeled on ``test_every_v1_route_declares_the_key`` in
``tests/unit/test_api_key_auth.py``: a new route that forgets its dependencies
fails here instead of shipping open.
"""

from collections.abc import Callable, Iterator, Sequence
from typing import Any, NamedTuple, cast

import pytest
from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.routing import BaseRoute, Mount, Route

from llc_manager.auth.csrf import SAFE_METHODS, verify_csrf
from llc_manager.auth.dependencies import require_admin, require_user
from llc_manager.auth.session import SESSION_COOKIE
from llc_manager.core.config import settings
from llc_manager.db.session import get_async_session
from llc_manager.main import create_app
from tests.auth_helpers import (
    TEST_CSRF_TOKEN,
    session_cookie_value,
    user_session,
)
from tests.unit.test_web_entities import FIXTURE_ID, _make_entity, _StubSession

# Path prefixes that are deliberately not behind the browser sign-in:
# /api/v1 uses the X-API-Key header, /api/health must stay open for probes,
# /api/docs, /api/redoc and /api/openapi.json are the API documentation, and
# /auth is the sign-in flow itself.
OPEN_PREFIXES = ("/api/", "/auth/")
ADMIN_ONLY = {
    ("GET", "/entities/{entity_id}/edit"),
    ("PATCH", "/entities/{entity_id}/edit"),
}


class RouteInfo(NamedTuple):
    """One concrete route: its methods, full path and every gate behind it."""

    methods: frozenset[str]
    path: str
    calls: frozenset[Callable[..., object]]


def _calls(dependant: Dependant) -> set[Callable[..., object]]:
    """Collect every dependency callable reachable from ``dependant``."""
    found: set[Callable[..., object]] = set()
    for sub in dependant.dependencies:
        if sub.call is not None:
            found.add(sub.call)
        found |= _calls(sub)
    return found


def _walk(
    routes: Sequence[BaseRoute],
    prefix: str,
    inherited: frozenset[Callable[..., object]],
) -> Iterator[BaseRoute | RouteInfo]:
    """Flatten nested routers across FastAPI versions.

    Older FastAPI copies included routes into the app; newer releases keep an
    ``_IncludedRouter`` wrapper that carries the include-time prefix and
    dependencies. Both shapes are flattened to ``RouteInfo`` here.

    Yields:
        ``RouteInfo`` for each API route, and any other route object as-is.
    """
    for route in routes:
        context = getattr(route, "include_context", None)
        if context is not None:
            extra = frozenset(
                dep.dependency
                for dep in context.dependencies
                if dep.dependency is not None
            )
            yield from _walk(
                cast("Any", route).original_router.routes,
                prefix + context.prefix,
                inherited | extra,
            )
        elif isinstance(route, APIRoute):
            yield RouteInfo(
                frozenset(route.methods),
                prefix + route.path,
                frozenset(_calls(route.dependant)) | inherited,
            )
        else:
            yield route


def web_routes(app: FastAPI) -> list[RouteInfo]:
    """Return every API route registered on ``app``, flattened."""
    return [
        item
        for item in _walk(app.routes, "", frozenset())
        if isinstance(item, RouteInfo)
    ]


def _unexpected_routes(app: FastAPI) -> list[str]:
    """Name every non-API route that is not a known framework or static route."""
    found: list[str] = []
    for item in _walk(app.routes, "", frozenset()):
        if isinstance(item, RouteInfo):
            continue
        path = getattr(item, "path", "")
        if isinstance(item, Mount):
            if path != "/static":
                found.append(f"unexpected mount {path}")
        elif not (
            isinstance(item, Route) and path.startswith((*OPEN_PREFIXES, "/docs/"))
        ):
            found.append(f"unexpected route {path}")
    return found


def _gate_findings(info: RouteInfo) -> list[str]:
    """List the gates a single route is missing."""
    findings: list[str] = []
    if info.path.startswith(OPEN_PREFIXES):
        return findings
    if require_user not in info.calls:
        findings.append(f"{info.path}: missing require_user")
    findings.extend(
        f"{method} {info.path}: missing verify_csrf"
        for method in sorted(info.methods - SAFE_METHODS)
        if verify_csrf not in info.calls
    )
    findings.extend(
        f"{method} {info.path}: missing require_admin"
        for method in sorted(info.methods)
        if (method, info.path) in ADMIN_ONLY and require_admin not in info.calls
    )
    return findings


def ungated_findings(app: FastAPI) -> list[str]:
    """List every route that is missing a gate it should have."""
    findings = _unexpected_routes(app)
    for info in web_routes(app):
        findings.extend(_gate_findings(info))
    return findings


def test_every_web_route_is_gated() -> None:
    assert ungated_findings(create_app()) == []


def test_enumeration_covers_the_known_web_routes() -> None:
    paths = {info.path for info in web_routes(create_app())}

    assert {"/", "/entities", "/entities/{entity_id}"} <= paths
    assert "/entities/{entity_id}/edit" in paths
    assert "/api/v1/entities" in paths


def test_enumeration_detects_an_ungated_route() -> None:
    app = create_app()

    @app.get("/forgotten")
    async def forgotten() -> dict[str, bool]:
        return {"oops": True}

    @app.delete("/entities/{entity_id}/remove")
    async def remove(entity_id: str) -> dict[str, str]:
        return {"id": entity_id}

    findings = ungated_findings(app)

    assert "/forgotten: missing require_user" in findings
    assert "DELETE /entities/{entity_id}/remove: missing verify_csrf" in findings


def test_admin_only_routes_really_exist() -> None:
    routes = {
        (method, info.path)
        for info in web_routes(create_app())
        for method in info.methods
    }

    assert routes >= ADMIN_ONLY


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()

    async def _override() -> Iterator[_StubSession]:
        yield _StubSession([_make_entity()])

    app.dependency_overrides[get_async_session] = _override
    with TestClient(app, follow_redirects=False) as test_client:
        yield test_client


def _sign_in(client: TestClient, role: str) -> None:
    client.cookies.set(
        SESSION_COOKIE,
        session_cookie_value(settings.secret_key, user_session(role)),
    )


EDIT_URL = f"/entities/{FIXTURE_ID}/edit"
GATED_GETS = [
    "/",
    "/entities",
    f"/entities/{FIXTURE_ID}",
    f"/entities/{FIXTURE_ID}/card",
    EDIT_URL,
]


class TestAnonymous:
    @pytest.mark.parametrize("path", GATED_GETS)
    def test_page_request_redirects_to_login_with_next(
        self, client: TestClient, path: str
    ) -> None:
        response = client.get(path)

        assert response.status_code == 303
        location = response.headers["location"]
        assert location.startswith("/auth/login?next=")

    @pytest.mark.parametrize("path", GATED_GETS)
    def test_htmx_request_gets_401_and_hx_redirect(
        self, client: TestClient, path: str
    ) -> None:
        response = client.get(
            path,
            headers={
                "HX-Request": "true",
                "HX-Current-URL": "http://testserver/entities",
            },
        )

        assert response.status_code == 401
        assert response.headers["hx-redirect"] == "/auth/login?next=%2Fentities"

    def test_patch_is_refused_without_changing_anything(
        self, client: TestClient
    ) -> None:
        response = client.patch(EDIT_URL, data={"legal_name": "Hacked"})

        assert response.status_code in {303, 403}
        assert "Hacked" not in response.text

    def test_api_key_routes_are_unaffected(self, client: TestClient) -> None:
        assert client.get("/api/health/live").status_code == 200
        assert client.get("/api/v1/entities").status_code == 401  # no X-API-Key

    def test_dev_mode_opens_the_ui_as_admin(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "auth_dev_mode", True)

        assert client.get("/entities").status_code == 200
        assert client.get(EDIT_URL).status_code == 200


class TestViewer:
    def test_can_read_pages(self, client: TestClient) -> None:
        _sign_in(client, "viewer")

        assert client.get("/entities").status_code == 200
        assert client.get(f"/entities/{FIXTURE_ID}").status_code == 200
        assert client.get(f"/entities/{FIXTURE_ID}/card").status_code == 200
        assert client.get("/").status_code == 200

    def test_cannot_open_the_edit_form(self, client: TestClient) -> None:
        _sign_in(client, "viewer")

        assert client.get(EDIT_URL).status_code == 403

    def test_cannot_save_an_edit_even_with_a_valid_csrf_token(
        self, client: TestClient
    ) -> None:
        _sign_in(client, "viewer")

        response = client.patch(
            EDIT_URL,
            data={"legal_name": "Renamed"},
            headers={"X-CSRF-Token": TEST_CSRF_TOKEN},
        )

        assert response.status_code == 403

    def test_edit_button_is_hidden(self, client: TestClient) -> None:
        _sign_in(client, "viewer")

        for path in (f"/entities/{FIXTURE_ID}", f"/entities/{FIXTURE_ID}/card"):
            body = client.get(path).text
            assert f'hx-get="/entities/{FIXTURE_ID}/edit"' not in body
            assert "Acme Holdings LLC" in body


class TestAdmin:
    def test_edit_button_is_shown(self, client: TestClient) -> None:
        _sign_in(client, "admin")

        body = client.get(f"/entities/{FIXTURE_ID}").text

        assert f'hx-get="/entities/{FIXTURE_ID}/edit"' in body

    def test_can_open_the_edit_form(self, client: TestClient) -> None:
        _sign_in(client, "admin")

        assert client.get(EDIT_URL).status_code == 200

    def test_save_without_csrf_token_is_forbidden(self, client: TestClient) -> None:
        _sign_in(client, "admin")

        response = client.patch(EDIT_URL, data={"legal_name": "Renamed"})

        assert response.status_code == 403

    def test_save_with_wrong_csrf_token_is_forbidden(self, client: TestClient) -> None:
        _sign_in(client, "admin")

        response = client.patch(
            EDIT_URL,
            data={"legal_name": "Renamed"},
            headers={"X-CSRF-Token": "forged"},
        )

        assert response.status_code == 403

    def test_save_with_csrf_token_succeeds(self, client: TestClient) -> None:
        _sign_in(client, "admin")

        response = client.patch(
            EDIT_URL,
            data={
                "legal_name": "Renamed LLC",
                "ein": "12-3456789",
                "entity_type": "llc",
            },
            headers={"X-CSRF-Token": TEST_CSRF_TOKEN},
        )

        assert response.status_code == 200
        assert "Renamed LLC" in response.text


class TestPageChrome:
    def test_body_carries_the_csrf_token_for_htmx(self, client: TestClient) -> None:
        _sign_in(client, "admin")

        body = client.get("/entities").text

        assert f'hx-headers=\'{{"X-CSRF-Token": "{TEST_CSRF_TOKEN}"}}\'' in body

    def test_signed_in_user_and_logout_form_are_shown(self, client: TestClient) -> None:
        _sign_in(client, "viewer")

        body = client.get("/entities").text

        assert "Test Viewer (viewer)" in body
        assert 'action="/auth/logout"' in body
        assert f'name="csrf_token" value="{TEST_CSRF_TOKEN}"' in body

    def test_expired_session_is_treated_as_signed_out(self, client: TestClient) -> None:
        client.cookies.set(
            SESSION_COOKIE,
            session_cookie_value(settings.secret_key, user_session("admin", exp_in=-1)),
        )

        assert client.get("/entities").status_code == 303
````

The existing web tests need an authenticated client, because the gate now applies to the routes they call. The autouse API-key fixture in `tests/conftest.py` does not cover web sessions.

````diff
--- a/tests/unit/test_web_entities.py
+++ b/tests/unit/test_web_entities.py
@@ -9,9 +9,16 @@
 import pytest
 from fastapi.testclient import TestClient

+from llc_manager.auth.session import SESSION_COOKIE
+from llc_manager.core.config import settings
 from llc_manager.db.session import get_async_session
 from llc_manager.main import create_app
 from llc_manager.models.entity import EntityType
+from tests.auth_helpers import (
+    TEST_CSRF_TOKEN,
+    session_cookie_value,
+    user_session,
+)

 FIXTURE_ID = UUID("11111111-1111-1111-1111-111111111111")

@@ -108,8 +115,13 @@

 @pytest.fixture
 def client_with_entities(fixture_entity: SimpleNamespace) -> Iterator[TestClient]:
-    """TestClient with get_async_session overridden to yield a stubbed session
-    that returns the fixture entity for both list and detail queries."""
+    """Signed-in admin TestClient with the database stubbed out.
+
+    ``get_async_session`` is overridden to yield a stubbed session that returns
+    the fixture entity for both list and detail queries. The client carries an
+    admin session cookie and the matching ``X-CSRF-Token`` header, as a browser
+    would after signing in (the web routes are gated).
+    """
     app = create_app()

     async def _override() -> AsyncIterator[_StubSession]:
@@ -118,6 +130,11 @@

     app.dependency_overrides[get_async_session] = _override
     with TestClient(app) as c:
+        c.cookies.set(
+            SESSION_COOKIE,
+            session_cookie_value(settings.secret_key, user_session("admin")),
+        )
+        c.headers["X-CSRF-Token"] = TEST_CSRF_TOKEN
         yield c
     app.dependency_overrides.clear()
````

The wiring test flips from "web routes are still open" to "web routes are gated":

````diff
--- a/tests/unit/test_auth_wiring.py
+++ b/tests/unit/test_auth_wiring.py
@@ -1,8 +1,4 @@
-"""Tests for how the auth package is wired into the app (PR 2 behavior).
-
-PR 2 adds the sign-in machinery but gates nothing, so an app with no auth
-settings must behave exactly as before.
-"""
+"""Tests for how the auth package is wired into the app."""

 from collections.abc import Iterator
 from typing import TYPE_CHECKING, cast
@@ -35,13 +31,15 @@
     assert "not configured" in response.text


-def test_web_routes_are_still_open(client: TestClient) -> None:
-    # Gating ships in a later PR; until then the root dashboard stays open.
-    assert client.get("/").status_code == 200
+def test_web_routes_are_gated(client: TestClient) -> None:
+    response = client.get("/")
+
+    assert response.status_code == 303
+    assert response.headers["location"] == "/auth/login?next=%2F"


 def test_no_cookie_is_set_for_anonymous_requests(client: TestClient) -> None:
-    response = client.get("/")
+    response = client.get("/auth/login")

     assert SESSION_COOKIE not in response.headers.get("set-cookie", "")
````

- [ ] **Step 2: Run them and see them fail**

```bash
uv run pytest tests/unit/test_web_gating.py tests/unit/test_web_entities.py tests/unit/test_auth_wiring.py -v -o addopts=""
```

Expected: `21 failed, 20 passed`. The failures include `assert 200 == 303` (a page is still open), `assert 200 == 403` (a viewer can still edit), and an enumeration failure listing the ungated routes.

- [ ] **Step 3: Add the template globals**

````python
"""Jinja helpers so templates can read the signed-in user and CSRF token."""

from typing import cast

from fastapi import Request
from fastapi.templating import Jinja2Templates

from llc_manager.auth.dependencies import current_user
from llc_manager.auth.session import SessionUser, csrf_token


def _template_current_user(request: Request) -> SessionUser | None:
    """Template global: the signed-in user for this request, if any."""
    return current_user(request)


def _template_csrf_token(request: Request) -> str:
    """Template global: this session's CSRF token, minted on first use."""
    return csrf_token(request.session)


def install_auth_globals(templates: Jinja2Templates) -> Jinja2Templates:
    """Expose ``current_user(request)`` and ``csrf_token(request)`` to templates.

    Every ``Jinja2Templates`` instance that renders pages extending
    ``base.html`` must be passed through this function.

    Args:
        templates: The templates instance to extend.

    Returns:
        The same instance, for use in an assignment.
    """
    # Jinja types ``globals`` as a narrow union; callables are valid at runtime.
    template_globals = cast("dict[str, object]", templates.env.globals)
    template_globals["current_user"] = _template_current_user
    template_globals["csrf_token"] = _template_csrf_token
    return templates
````

````diff
--- a/src/llc_manager/core/templates.py
+++ b/src/llc_manager/core/templates.py
@@ -4,4 +4,8 @@

 from fastapi.templating import Jinja2Templates

-templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
+from llc_manager.auth.templating import install_auth_globals
+
+templates = install_auth_globals(
+    Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
+)
````

- [ ] **Step 4: Gate the routers**

````diff
--- a/src/llc_manager/api/ui.py
+++ b/src/llc_manager/api/ui.py
@@ -1,11 +1,12 @@
 """HTML page routes served via Jinja2 templates."""

-from fastapi import APIRouter, Request
+from fastapi import APIRouter, Depends, Request
 from fastapi.responses import HTMLResponse

+from llc_manager.auth.dependencies import require_user
 from llc_manager.core.templates import templates

-router = APIRouter(include_in_schema=False)
+router = APIRouter(include_in_schema=False, dependencies=[Depends(require_user)])


 @router.get("/", response_class=HTMLResponse)
````

````diff
--- a/src/llc_manager/web/routes.py
+++ b/src/llc_manager/web/routes.py
@@ -11,14 +11,22 @@
 from sqlalchemy import func, select
 from sqlalchemy.ext.asyncio import AsyncSession

+from llc_manager.auth.csrf import verify_csrf
+from llc_manager.auth.dependencies import require_admin, require_user
+from llc_manager.auth.templating import install_auth_globals
 from llc_manager.db.session import get_async_session
 from llc_manager.models.entity import Entity, EntityType
 from llc_manager.schemas.entity import EntityUpdate

 TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
-templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
+templates = install_auth_globals(Jinja2Templates(directory=str(TEMPLATES_DIR)))

-router = APIRouter(tags=["Web"])
+# Every web route needs a signed-in user, and every non-safe method needs the
+# CSRF token. Routes that change data add require_admin on top.
+router = APIRouter(
+    tags=["Web"],
+    dependencies=[Depends(require_user), Depends(verify_csrf)],
+)

 DBSession = Annotated[AsyncSession, Depends(get_async_session)]

@@ -122,7 +130,11 @@
     )


-@router.get("/entities/{entity_id}/edit", response_class=HTMLResponse)
+@router.get(
+    "/entities/{entity_id}/edit",
+    response_class=HTMLResponse,
+    dependencies=[Depends(require_admin)],
+)
 async def entity_edit_form(
     request: Request,
     db: DBSession,
@@ -177,7 +189,11 @@
     )


-@router.patch("/entities/{entity_id}/edit", response_class=HTMLResponse)
+@router.patch(
+    "/entities/{entity_id}/edit",
+    response_class=HTMLResponse,
+    dependencies=[Depends(require_admin)],
+)
 async def entity_edit_save(
     request: Request,
     db: DBSession,
````

- [ ] **Step 5: Update the templates**

````diff
--- a/src/llc_manager/templates/base.html
+++ b/src/llc_manager/templates/base.html
@@ -16,7 +16,7 @@

   {% block head %}{% endblock %}
 </head>
-<body class="h-full" hx-boost="true">
+<body class="h-full" hx-boost="true" hx-headers='{{ {"X-CSRF-Token": csrf_token(request)}|tojson }}'>

   <!-- Navigation -->
   <nav class="bg-brand-600 text-white shadow-sm">
@@ -30,6 +30,16 @@
             <a href="/compliance" class="hover:text-brand-100 transition-colors">Compliance</a>
           </div>
         </div>
+        {% set user = current_user(request) %}
+        {% if user %}
+        <div class="flex items-center gap-4 text-sm">
+          <span data-testid="signed-in-user">{{ user.name or user.email or user.sub }} ({{ user.role.value }})</span>
+          <form method="post" action="/auth/logout" hx-boost="false">
+            <input type="hidden" name="csrf_token" value="{{ csrf_token(request) }}" />
+            <button type="submit" class="hover:text-brand-100 transition-colors">Sign out</button>
+          </form>
+        </div>
+        {% endif %}
       </div>
     </div>
   </nav>
````

````diff
--- a/src/llc_manager/templates/entities/partials/detail_card.html
+++ b/src/llc_manager/templates/entities/partials/detail_card.html
@@ -1,5 +1,7 @@
 <header class="card-header">
     <h1>{{ entity.legal_name }}</h1>
+    {% set user = current_user(request) %}
+    {% if user and user.is_admin %}
     <button
         type="button"
         class="btn btn-primary"
@@ -7,6 +9,7 @@
         hx-target="#entity-card"
         hx-swap="innerHTML"
     >Edit</button>
+    {% endif %}
 </header>

 <dl class="entity-fields">
````

- [ ] **Step 6: Run the tests and see them pass**

```bash
uv run pytest tests/unit/test_web_gating.py tests/unit/test_web_entities.py tests/unit/test_auth_wiring.py -v -o addopts=""
```

Expected: `41 passed` (29 in the gating file, 5 in the entity file, 7 in the wiring file).

- [ ] **Step 7: Lint and type-check**

```bash
uv run ruff format src tests
uv run ruff check src tests
uv run basedpyright src/llc_manager/auth src/llc_manager/core/templates.py src/llc_manager/web src/llc_manager/api/ui.py
```

Expected: `All checks passed!` and `0 errors`.

- [ ] **Step 8: Commit**

```bash
git add src/llc_manager/auth/templating.py src/llc_manager/core/templates.py src/llc_manager/api/ui.py src/llc_manager/web/routes.py src/llc_manager/templates/base.html src/llc_manager/templates/entities/partials/detail_card.html tests/unit/test_web_gating.py tests/unit/test_web_entities.py tests/unit/test_auth_wiring.py
git commit -S -m "feat(auth)!: require sign-in for the web ui and csrf for edits" -m "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

### Task 4.3: Guides, config entries, and stale documentation

depends-on: Task 4.1 [completion]

Files:

- Create: `docs/guides/authentik-setup.md`, `docs/guides/authentik-outage-runbook.md`
- Modify: `mkdocs.yml`, `.env.example`, `docker-compose.yml`, `docs/template_feedback.md`, `docs/planning/adr/adr-001-initial-architecture.md`, `docs/planning/adr/adr-002-individual-household-entities.md`, `docs/architecture/system-overview.md`, `docs/planning/tech-spec.md`, `docs/planning/roadmap.md`, `docs/planning/PROJECT-PLAN.md`

This task is independent of Task 4.2 and can run in parallel with it. Documentation checks replace the red-green cycle: the front-matter validator, the strict docs build, and the markdown hooks.

- [ ] **Step 1: Write the setup guide**

The guide's step 4 is the check of the `groups` claim, which is the plan's unverified assumption. `docs/guides` pages use `schema_type: common` and only tags from the validator's allow-list (`runbook`, `operations`, and `troubleshooting` are not on it).

````markdown
---
title: "Authentik Setup"
schema_type: common
status: draft
owner: core-maintainer
purpose: "How to create the Authentik application and groups, set the LLC Manager environment, and verify sign-in before deploying the gated web UI."
tags:
  - guide
  - security
  - deployment
---

The web UI signs users in through Authentik. Do every step here before you
deploy a build that includes the web gate. The application fails closed: with no
working sign-in method it refuses to start in production, and with a wrong
setting nobody can reach the pages.

## Before you start

You need admin access to Authentik, the public HTTPS hostname that serves LLC
Manager, and a place to keep secrets (not this repository).

## 1. Create the groups

Create two groups in Authentik. The names are the defaults; if you choose
others, set `LLC_MANAGER_ADMIN_GROUP` and `LLC_MANAGER_VIEWER_GROUP` to match.

| Group | Role in LLC Manager |
| --- | --- |
| `llc-manager-admins` | Admin: read everything, edit entities |
| `llc-manager-viewers` | Viewer: read only |

A user in both groups is an admin. A user in neither is refused with a 403 page.

## 2. Create the provider

Create an OAuth2/OpenID provider:

- Client type: confidential.
- Authorization flow: authorization code. The app sends a PKCE challenge.
- Redirect URI (strict): `https://<your-host>/auth/callback`.
- Signing key: any key that signs ID tokens (RS256).
- Scopes: `openid`, `profile`, `email`, plus a scope mapping that returns group
  names (see step 4).

## 3. Create the application

Create an application that uses the provider and bind it to the two groups, so
users outside them cannot even finish the Authentik login.

## 4. Confirm the groups claim

This is the assumption the whole role mapping rests on, and it was unchecked in
the project plan. Verify it before deploying.

1. Sign in to the application as a test user in one group.
2. Decode the ID token (for example with the provider's "Preview" tool, or paste
   a token into a local JWT decoder; never into a public website).
3. Confirm a `groups` claim that is a list of group **names**, for example
   `["llc-manager-admins"]`.

If the claim is missing, add a scope mapping to the provider with this
expression:

```python
return {"groups": [group.name for group in request.user.ak_groups.all()]}
```

If you use another claim name, set `LLC_MANAGER_AUTHENTIK_GROUPS_CLAIM`.

## 5. Set the environment

Set these in the secrets manager or stack environment, never in git. All names
carry the `LLC_MANAGER_` prefix.

| Variable | Value |
| --- | --- |
| `LLC_MANAGER_PUBLIC_BASE_URL` | `https://<your-host>` (HTTPS required outside development) |
| `LLC_MANAGER_AUTHENTIK_ISSUER` | `https://<authentik-host>/application/o/<slug>/` |
| `LLC_MANAGER_AUTHENTIK_CLIENT_ID` | the provider's client ID |
| `LLC_MANAGER_AUTHENTIK_CLIENT_SECRET` | the provider's client secret |
| `LLC_MANAGER_SECRET_KEY` | 32 or more random characters; rotating it signs everyone out |
| `LLC_MANAGER_TRUSTED_PROXY_IPS` | comma-separated IPs or CIDR networks of your reverse proxy |

The issuer, client ID, and client secret must be set together or not at all.

## 6. Verify behind the proxy

After deploying, open the site in a private window and confirm:

1. You are sent to Authentik and return to the page you asked for.
2. The page shows your name and role, and a viewer sees no Edit button.
3. The logs show `https` as the scheme and your real address as the client IP for
   a request through the proxy. If they show `http` and the proxy address, the
   proxy address is missing from `LLC_MANAGER_TRUSTED_PROXY_IPS`, or the proxy
   does not send `X-Forwarded-For` and `X-Forwarded-Proto`.

## Break-glass local admin (optional)

For Authentik outages you can enable one local admin login. It is off by
default. See the outage runbook for the full procedure.

1. Generate an argon2 hash on a trusted machine, typing the password at the
   prompt: `python -c "import getpass; from argon2 import PasswordHasher; print(PasswordHasher().hash(getpass.getpass()))"`.
2. Set `LLC_MANAGER_LOCAL_ADMIN_PASSWORD_HASH` to the printed hash and
   `LLC_MANAGER_LOCAL_ADMIN_ENABLED=true`. The hash contains `$`; in a `.env`
   file wrap it in single quotes so it is not interpolated.
3. The login lives at `/auth/local-login`. It is not linked from the normal UI.

## Local development

Set `LLC_MANAGER_AUTH_DEV_MODE=true` to skip Authentik and act as a fixed admin
user. Startup refuses this setting unless the environment is `development`,
`local`, or `test`.
````

- [ ] **Step 2: Write the outage runbook**

````markdown
---
title: "Authentik Outage Runbook"
schema_type: common
status: draft
owner: core-maintainer
purpose: "What to do when Authentik is unreachable and nobody can sign in to the LLC Manager web UI."
tags:
  - guide
  - security
  - deployment
---

Use this when sign-in fails because Authentik is down or unreachable. LLC Manager
shows a "Sign-in is temporarily unavailable" page (HTTP 503) in that case. The service API
(`/api/v1`, `X-API-Key`) and the health probes are not affected.

## 1. Confirm it is Authentik

1. Open the Authentik login page directly. If it does not load, the outage is on
   the Authentik side; start there.
2. Check the LLC Manager logs for the `oidc_provider_unreachable` event. It
   carries the error class and the correlation ID (the `X-Correlation-ID`
   response header of the failed request) and never the response body.
3. Check that `LLC_MANAGER_AUTHENTIK_ISSUER` still matches the provider slug. A
   renamed provider looks like an outage.

## 2. Wait or use break-glass

If Authentik will be back soon, wait. Existing sessions keep working until they
expire (8 hours by default); only new sign-ins fail.

If you need access now and the break-glass login was enabled ahead of time:

1. Open `/auth/local-login` on the public hostname.
2. Enter the break-glass password. You get a normal admin session marked
   `auth_method: local`.
3. After five failed attempts from one address in fifteen minutes the login
   answers 429 and a `Retry-After` header. Do not hammer it.

If break-glass was not enabled, you must change the environment and restart:

1. Generate an argon2 hash (see the setup guide) and set
   `LLC_MANAGER_LOCAL_ADMIN_PASSWORD_HASH` and
   `LLC_MANAGER_LOCAL_ADMIN_ENABLED=true` in the stack environment.
2. Restart the container. The OIDC settings can stay in place.

## 3. Leave no door open

When Authentik is back:

1. Set `LLC_MANAGER_LOCAL_ADMIN_ENABLED=false` (or unset it) and restart.
2. Rotate the break-glass password if it was typed anywhere other than the
   login form.
3. Review the WARNING log lines `local_login_succeeded`, `local_login_failed`,
   and `local_login_throttled` for the outage window. Every attempt is logged
   with the client IP and correlation ID. Passwords are never logged.

## Notes

- The throttle is per process. With several replicas the effective limit is the
  per-process limit times the replica count.
- To sign everyone out at once, rotate `LLC_MANAGER_SECRET_KEY` and restart.
- Never use `LLC_MANAGER_AUTH_DEV_MODE` in production; startup refuses it.
````

- [ ] **Step 3: Add the guides to the site navigation**

In `mkdocs.yml`, replace this text:

````yaml
      - Manifest Dry Run: guides/document-manifest-dry-run.md
````

with:

````yaml
      - Manifest Dry Run: guides/document-manifest-dry-run.md
      - Authentik Setup: guides/authentik-setup.md
      - Authentik Outage Runbook: guides/authentik-outage-runbook.md
````

- [ ] **Step 4: Add the settings to `.env.example` and the compose file**

Compose variables for booleans and numbers keep real defaults because an empty string is not a valid bool or int; the argon2 hash contains `$` and must be single-quoted in env files.

In `.env.example`, replace this text:

````bash
# LLC_MANAGER_API_KEY=
````

with:

````bash
# LLC_MANAGER_API_KEY=

# Browser sign-in (Authentik OIDC). Outside development the web UI will not
# start unless PUBLIC_BASE_URL is https and either the full OIDC set or the
# break-glass login is configured. Setup steps: docs/guides/authentik-setup.md
# LLC_MANAGER_PUBLIC_BASE_URL=https://llc.example.com
# LLC_MANAGER_AUTHENTIK_ISSUER=https://auth.example.com/application/o/llc-manager/
# LLC_MANAGER_AUTHENTIK_CLIENT_ID=
# LLC_MANAGER_AUTHENTIK_CLIENT_SECRET=
# Claim and group names; these are the defaults.
# LLC_MANAGER_AUTHENTIK_GROUPS_CLAIM=groups
# LLC_MANAGER_ADMIN_GROUP=llc-manager-admins
# LLC_MANAGER_VIEWER_GROUP=llc-manager-viewers
# Absolute session lifetime in seconds (8 hours).
# LLC_MANAGER_SESSION_MAX_AGE_SECONDS=28800
# Reverse proxies whose X-Forwarded-For/-Proto headers are trusted:
# comma-separated IPs or CIDR networks. Empty trusts none.
# LLC_MANAGER_TRUSTED_PROXY_IPS=
# Break-glass local admin for Authentik outages. Off by default. The value
# is an argon2 hash, never a password; single-quote it because it contains $.
# LLC_MANAGER_LOCAL_ADMIN_ENABLED=false
# LLC_MANAGER_LOCAL_ADMIN_PASSWORD_HASH='$argon2id$...'
# Development only: sign in as a fixed admin without Authentik. Startup
# refuses this outside development, local, and test environments.
# LLC_MANAGER_AUTH_DEV_MODE=false
````

In `docker-compose.yml`, replace this text:

````yaml
      LLC_MANAGER_CORS_ORIGINS: '["http://localhost:8000"]'
````

with:

````yaml
      LLC_MANAGER_CORS_ORIGINS: '["http://localhost:8000"]'

      # Browser sign-in (see docs/guides/authentik-setup.md). Empty values
      # mean unset. Booleans and numbers keep real defaults because an empty
      # string is not a valid bool or int.
      LLC_MANAGER_PUBLIC_BASE_URL: ${LLC_MANAGER_PUBLIC_BASE_URL:-}
      LLC_MANAGER_AUTHENTIK_ISSUER: ${LLC_MANAGER_AUTHENTIK_ISSUER:-}
      LLC_MANAGER_AUTHENTIK_CLIENT_ID: ${LLC_MANAGER_AUTHENTIK_CLIENT_ID:-}
      LLC_MANAGER_AUTHENTIK_CLIENT_SECRET: ${LLC_MANAGER_AUTHENTIK_CLIENT_SECRET:-}
      LLC_MANAGER_AUTHENTIK_GROUPS_CLAIM: ${LLC_MANAGER_AUTHENTIK_GROUPS_CLAIM:-groups}
      LLC_MANAGER_ADMIN_GROUP: ${LLC_MANAGER_ADMIN_GROUP:-llc-manager-admins}
      LLC_MANAGER_VIEWER_GROUP: ${LLC_MANAGER_VIEWER_GROUP:-llc-manager-viewers}
      LLC_MANAGER_SESSION_MAX_AGE_SECONDS: ${LLC_MANAGER_SESSION_MAX_AGE_SECONDS:-28800}
      LLC_MANAGER_TRUSTED_PROXY_IPS: ${LLC_MANAGER_TRUSTED_PROXY_IPS:-}
      LLC_MANAGER_LOCAL_ADMIN_ENABLED: ${LLC_MANAGER_LOCAL_ADMIN_ENABLED:-false}
      LLC_MANAGER_LOCAL_ADMIN_PASSWORD_HASH: ${LLC_MANAGER_LOCAL_ADMIN_PASSWORD_HASH:-}
      LLC_MANAGER_AUTH_DEV_MODE: ${LLC_MANAGER_AUTH_DEV_MODE:-false}
````

- [ ] **Step 5: Fix the stale statements in the ADRs and the system overview**

In `docs/planning/adr/adr-001-initial-architecture.md`, replace this text:

````markdown
- [ ] Authentik SSO login/logout functional
````

with:

````markdown
- [ ] Authentik SSO login/logout functional (implemented by ADR-003; tick after the live check in `docs/guides/authentik-setup.md`)
````

In `docs/planning/adr/adr-001-initial-architecture.md`, replace this text:

````markdown
- **No auth layer in Phase 0**: The current deployment has no authentication
  or authorization. The application must not be exposed on a public network
  interface until Authentik OIDC integration (planned for Phase 1) is
  complete and validated.
````

with:

````markdown
- **Authentication**: Browser users sign in through Authentik OIDC and the
  service API uses the `X-API-Key` header (decision and rollout in
  [ADR-003](adr-003-authentik-sso-web-login.md)). Do not expose the
  application on a public network interface until the Authentik application
  and groups exist and the live check in `docs/guides/authentik-setup.md`
  has passed.
````

In `docs/planning/adr/adr-002-individual-household-entities.md`, replace this text:

````markdown
- The entity API is not yet authenticated, and its responses now include
  personal names (individual and household rows) and bank account last-4
  digits. Real individual or household data must not be loaded into a
  database that API serves beyond localhost until authentication lands.
````

with:

````markdown
- The entity API is protected by one shared `X-API-Key` (no per-user
  identity), and its responses now include personal names (individual and
  household rows) and bank account last-4 digits. Real individual or
  household data must not be loaded into a database that API serves beyond
  localhost until the key is configured and the deployment is verified. The
  browser UI is covered separately by ADR-003.
````

In `docs/architecture/system-overview.md`, replace this text:

````markdown
small team of 5-15 users authenticated via Authentik OIDC. The system runs as a
````

with:

````markdown
small team of 5-15 users who sign in through Authentik OIDC (roles come from group
membership, see [ADR-003](../planning/adr/adr-003-authentik-sso-web-login.md)).
Service clients call `/api/v1/` with the `X-API-Key` header. The system runs as a
````

In `docs/architecture/system-overview.md`, replace this text:

````markdown
- **Authentik**: OIDC identity provider handling login and session management
````

with:

````markdown
- **Authentik**: OIDC identity provider that authenticates browser users and supplies
  their group membership; the app keeps the session itself in a signed cookie
````

In `docs/architecture/system-overview.md`, replace this text:

````markdown
  |-- api/health.py        Kubernetes liveness / readiness / startup probes
````

with:

````markdown
  |-- api/health.py        Kubernetes liveness / readiness / startup probes
  |-- auth/                OIDC login, signed-cookie session, roles, CSRF, break-glass login
````

- [ ] **Step 6: Fix the tech-spec to match the code**

The tech-spec used unprefixed variable names and described a username and plaintext-named password for the local admin; the code uses `LLC_MANAGER_*` and a hash only.

In `docs/planning/tech-spec.md`, replace this text:

````markdown
| POST   | `/auth/logout`   | Logout, clear session | Yes  |
````

with:

````markdown
| POST   | `/auth/logout`   | Logout, clear session | Yes  |
| GET    | `/auth/local-login`  | Break-glass login form (404 unless enabled) | No   |
| POST   | `/auth/local-login`  | Break-glass login (rate limited)            | No   |
````

In `docs/planning/tech-spec.md`, replace this text:

````markdown
- **Purpose**: Emergency access when Authentik is unavailable
- **Username**: Configured via `LOCAL_ADMIN_USERNAME` env var
- **Password**: Configured via `LOCAL_ADMIN_PASSWORD` env var (hashed with argon2)
- **Access**: Full admin privileges; bypasses OIDC flow
- **Login Path**: `GET /auth/local-login` (hidden from main UI)
- **Audit**: All local admin actions logged with `auth_method: local`
````

with:

````markdown
- **Purpose**: Emergency access when Authentik is unavailable
- **Account**: One fixed admin account (subject `local-admin`); there is no username
- **Password**: `LLC_MANAGER_LOCAL_ADMIN_PASSWORD_HASH` holds an argon2 hash, never a
  plaintext password
- **Switch**: `LLC_MANAGER_LOCAL_ADMIN_ENABLED` (default `false`); the login answers 404
  unless it is true and a hash is set
- **Access**: Full admin privileges; bypasses the OIDC flow
- **Login Path**: `GET` and `POST /auth/local-login` (not linked from the main UI)
- **Throttle**: 5 failed attempts per 15 minutes per client IP, then 429
- **Audit**: Every attempt is logged at WARNING with the client IP and correlation ID;
  the session is marked `auth_method: local`
````

In `docs/planning/tech-spec.md`, replace this text:

````markdown
- Set `AUTH_DEV_MODE=true` to bypass OIDC
- Auto-login as admin role for local testing
````

with:

````markdown
- Set `LLC_MANAGER_AUTH_DEV_MODE=true` to bypass OIDC
- Auto-login as a fixed admin user for local testing
- Startup refuses the setting unless the environment is development, local, or test
````

In `docs/planning/tech-spec.md`, replace this text:

````markdown
| `AUTHENTIK_ISSUER`        | OIDC issuer URL                     | `https://auth.example.com/application/o/llc-manager/`   |
| `AUTHENTIK_CLIENT_ID`     | OAuth client ID                     | `llc-manager`                                           |
| `AUTHENTIK_CLIENT_SECRET` | OAuth client secret                 | (secret)                                                |
| `APPRISE_URL`             | Apprise notification URL            | `http://apprise:8000/notify`                            |
| `SECRET_KEY`              | Session encryption                  | (32+ byte random)                                       |
| `LOCAL_ADMIN_USERNAME`    | Local admin username                | `localadmin`                                            |
| `LOCAL_ADMIN_PASSWORD`    | Local admin password (argon2 hash)  | (secret)                                                |
| `AUTH_DEV_MODE`           | Bypass OIDC for local dev           | `true` or `false`                                       |
````

with:

````markdown
| `LLC_MANAGER_PUBLIC_BASE_URL` | Public HTTPS origin; redirect URIs are built from it | `https://llc.example.com`           |
| `LLC_MANAGER_AUTHENTIK_ISSUER`        | OIDC issuer URL             | `https://auth.example.com/application/o/llc-manager/`   |
| `LLC_MANAGER_AUTHENTIK_CLIENT_ID`     | OAuth client ID             | `llc-manager`                                           |
| `LLC_MANAGER_AUTHENTIK_CLIENT_SECRET` | OAuth client secret         | (secret)                                                |
| `LLC_MANAGER_AUTHENTIK_GROUPS_CLAIM`  | Claim holding group names   | `groups`                                                |
| `LLC_MANAGER_ADMIN_GROUP`             | Group mapped to admin       | `llc-manager-admins`                                    |
| `LLC_MANAGER_VIEWER_GROUP`            | Group mapped to viewer      | `llc-manager-viewers`                                   |
| `LLC_MANAGER_SESSION_MAX_AGE_SECONDS` | Absolute session lifetime   | `28800`                                                 |
| `LLC_MANAGER_SECRET_KEY`              | Session cookie signing key  | (32+ byte random)                                       |
| `LLC_MANAGER_TRUSTED_PROXY_IPS`       | Proxies whose X-Forwarded-* headers are trusted | `10.0.0.5,172.18.0.0/16`    |
| `LLC_MANAGER_LOCAL_ADMIN_ENABLED`     | Break-glass login switch    | `true` or `false`                                       |
| `LLC_MANAGER_LOCAL_ADMIN_PASSWORD_HASH` | Break-glass argon2 hash   | (secret)                                                |
| `LLC_MANAGER_AUTH_DEV_MODE`           | Bypass OIDC for local dev   | `true` or `false`                                       |
| `APPRISE_URL`             | Apprise notification URL            | `http://apprise:8000/notify`                            |
````

- [ ] **Step 7: Align the roadmap to the project plan and tick completed items**

`PROJECT-PLAN.md` calls Authentik SSO M1 and carries the git branch names, so the roadmap follows it. The new table rows also include the data import milestone that the plan numbers M0.5.

In `docs/planning/roadmap.md`, replace the eight milestone rows from `| M0: Dev Environment Ready` through `| M7: Docker Deployment` (their Status column holds a pause-symbol emoji followed by the word Planned; match the rows exactly as they appear in the file) with:

````markdown
| M0: Dev Environment Ready | Week 1 | Planned     | None         |
| M0.5: Data Import         | Week 1 | Planned     | M0           |
| M1: Authentik SSO Working | Week 2 | In progress | M0.5         |
| M2: Entity Dashboard      | Week 3 | Planned     | M1           |
| M3: Entity Detail         | Week 3 | Planned     | M2           |
| M4: Entity CRUD           | Week 4 | Planned     | M3           |
| M5: Compliance Dashboard  | Week 5 | Planned     | M4           |
| M6: Apprise Notifications | Week 6 | Planned     | M5           |
| M7: Docker Deployment     | Week 6 | Planned     | M6           |
````

In `docs/planning/roadmap.md`, replace this text:

````markdown
- [ ] Authentik OIDC authentication working
````

with:

````markdown
- [x] Authentik OIDC authentication working
````

In `docs/planning/roadmap.md`, replace this text:

````markdown
- [ ] Login redirects to Authentik
- [ ] Successful auth creates session
- [ ] Logout clears session and redirects
- [ ] Unauthenticated users redirected to login
````

with:

````markdown
- [x] Login redirects to Authentik
- [x] Successful auth creates session
- [x] Logout clears session and redirects
- [x] Unauthenticated users redirected to login
````

In `docs/planning/PROJECT-PLAN.md`, replace this text:

````markdown
- [ ] Login redirects to Authentik and returns with session
- [ ] Logout clears session and redirects
- [ ] CSRF tokens validated on all state-changing requests
- [ ] Cookies set with Secure, HttpOnly, SameSite=Lax
- [ ] `llc-manager-admins` group → admin role
- [ ] `llc-manager-viewers` group → viewer role
- [ ] Role changes in Authentik reflected within session timeout
- [ ] Local admin works when `AUTH_DEV_MODE=true`
````

with:

````markdown
- [x] Login redirects to Authentik and returns with session
- [x] Logout clears session and redirects
- [x] CSRF tokens validated on all state-changing requests
- [x] Cookies set with Secure, HttpOnly, SameSite=Lax
- [x] `llc-manager-admins` group → admin role
- [x] `llc-manager-viewers` group → viewer role
- [x] Role changes in Authentik reflected within session timeout
- [x] Local admin login works when `LLC_MANAGER_LOCAL_ADMIN_ENABLED=true` and a hash is set;
  `LLC_MANAGER_AUTH_DEV_MODE=true` gives a dev admin outside production
````

- [ ] **Step 8: Record the template feedback**

The project's `CLAUDE.md` requires template issues to be logged in `docs/template_feedback.md`.

In `docs/template_feedback.md`, replace this text:

````markdown
---

## Submitting Feedback
````

with:

````markdown
### Compose files forward no application secrets or auth settings

- **Priority**: Medium
- **Category**: Configuration
- **Discovered**: 2026-11-06

**Issue**: `docker-compose.yml` and `docker-compose.prod.yml` pass `ENVIRONMENT`,
logging, and database settings to the app container but no `LLC_MANAGER_SECRET_KEY`,
`LLC_MANAGER_API_KEY`, or other application settings, and there is no `env_file`.
Values set in a stack environment only reach the container if the compose file
interpolates them. Separately, `docs/planning/roadmap.md` and
`docs/planning/PROJECT-PLAN.md` are generated with different milestone numbering
(roadmap M2 is the plan's M1).

**Context**: Adding Authentik sign-in settings to a project whose production compose
override could not have delivered them, while aligning the roadmap to the plan.

**Suggested Fix**: Generate an `env_file: .env` entry (or explicit `${VAR:-}`
passthroughs for every required setting) in the compose files, and have the planning
skill derive roadmap milestone numbers from `PROJECT-PLAN.md` so the two cannot diverge.

**Affected Files**: `docker-compose.yml`, `docker-compose.prod.yml`,
`docs/planning/roadmap.md`, `docs/planning/PROJECT-PLAN.md` (all under
`{{cookiecutter.project_slug}}/` in the template)

---

## Submitting Feedback
````

- [ ] **Step 9: Verify the documentation and configuration**

```bash
python tools/validate_front_matter.py docs
uv run mkdocs build --strict 2>&1 | tail -5
docker compose -f docker-compose.yml config -q
pre-commit run --files docs/guides/authentik-setup.md docs/guides/authentik-outage-runbook.md mkdocs.yml .env.example docker-compose.yml docs/template_feedback.md docs/planning/adr/adr-001-initial-architecture.md docs/planning/adr/adr-002-individual-household-entities.md docs/architecture/system-overview.md docs/planning/tech-spec.md docs/planning/roadmap.md docs/planning/PROJECT-PLAN.md
git status --short
```

Expected: the validator exits 0 with no error lines; the docs build ends with `Documentation built in ...` and no `WARNING` (pages outside the navigation give INFO only); `docker compose config -q` prints nothing; every hook passes. The `detect-secrets` hook rewrites `.secrets.baseline` because an audited line in `docs/planning/tech-spec.md` moves (446 to 454 in the verification run). Run `git add .secrets.baseline` and re-run the `pre-commit` command until it passes.

- [ ] **Step 10: Commit**

```bash
git add docs/guides/authentik-setup.md docs/guides/authentik-outage-runbook.md mkdocs.yml .env.example docker-compose.yml docs/template_feedback.md docs/planning/adr/adr-001-initial-architecture.md docs/planning/adr/adr-002-individual-household-entities.md docs/architecture/system-overview.md docs/planning/tech-spec.md docs/planning/roadmap.md docs/planning/PROJECT-PLAN.md .secrets.baseline
git commit -S -m "docs(auth): add the authentik setup guide and outage runbook" -m "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

If `.secrets.baseline` was not modified, `git add` of it is a no-op and the command is still correct.

### Task 4.4: Finish PR 4

depends-on: Task 4.1 [completion], Task 4.2 [completion], Task 4.3 [completion]

- [ ] **Step 1: Add the changelog entries under `## [Unreleased]`**

In `CHANGELOG.md`, replace this text:

````markdown
## [Unreleased]

### Added
````

with:

````markdown
## [Unreleased]

### Added

- `docs(auth)`: `docs/guides/authentik-setup.md` (Authentik application, groups,
  claim check, environment, proxy verification) and
  `docs/guides/authentik-outage-runbook.md`. `.env.example` and
  `docker-compose.yml` gain the sign-in settings.
````

In `CHANGELOG.md`, replace this text:

````markdown
### Changed

- `chore(ci)`: converted the Trivy suppressions from the plain-text `.trivyignore`
````

with:

````markdown
### Changed

- `feat(auth)!`: the web UI now requires sign-in. Every page route needs a
  session; editing an entity needs the admin role and a CSRF token; viewers
  see no edit controls. `/api/v1` (`X-API-Key`), `/api/health/*`, and static
  files are unchanged. Outside development, local, and test environments the
  app refuses to start unless `public_base_url` is https and either the full
  Authentik settings or the break-glass login is configured. Create the
  Authentik application and set the environment before deploying (see
  `docs/guides/authentik-setup.md`).
- `chore(ci)`: converted the Trivy suppressions from the plain-text `.trivyignore`
````

In `CHANGELOG.md`, replace this text:

````markdown
### Security

- `fix(security)`: document unfixed libexpat1
````

with:

````markdown
### Security

- `fix(security)`: the entity edit form and `PATCH /entities/{id}/edit` were
  reachable without authentication. They now require an admin session and a
  CSRF token.
- `fix(security)`: document unfixed libexpat1
````

- [ ] **Step 2: Run the whole suite with the repository defaults**

```bash
uv run pytest
uv run pytest tests/unit/test_web_gating.py tests/unit/test_api_key_auth.py -v -o addopts=""
```

Expected: all tests pass and coverage stays above 80 percent (767 passing in the verification run with the Excel import tests excluded). The second command shows both route-enumeration tests, the web one and the API-key one, passing together.

- [ ] **Step 3: Lint, type-check, and pre-commit**

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run basedpyright src/
pre-commit run --all-files
git status --short
```

Expected: `All checks passed!`; basedpyright reports no new errors against the base (the verification environment lacked `sentry_sdk` and `redis` and showed 12 unrelated import errors; an environment with all extras installed should show none); every hook passes. If `.secrets.baseline` changed, `git add` it and re-run.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -S -m "docs(changelog): record the web sign-in requirement" -m "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

- [ ] **Step 5: Confirm the deploy prerequisites with the owner (orchestrator only)**

Before pushing, check every item in "Deploy prerequisites for PR 4" with the owner. This PR makes the application fail closed, and a host-side watcher may deploy the image that `main` builds. Do not enable auto-merge on this PR.

- [ ] **Step 6: Open the PR (orchestrator only)**

```bash
git push -u origin feat/auth-gate-web
gh pr create --title "feat(auth)!: require sign-in for the web ui" --body "$(cat <<'EOF'
## Summary

- Attaches `require_user` and `verify_csrf` to the web router and `require_admin` to the entity edit routes; viewers see no edit controls; `base.html` carries the CSRF token for HTMX.
- Outside development, local, and test environments the app now refuses to start unless `public_base_url` is https and either the full Authentik settings or the break-glass login is configured.
- Adds the Authentik setup guide, the outage runbook, `.env.example` and compose entries, and corrects stale statements in ADR-001, ADR-002, the system overview, the tech-spec, and the roadmap.

## Deploy note

Do not merge until the Authentik application, the two groups, and the environment values exist and a test ID token shows a `groups` claim (`docs/guides/authentik-setup.md`). After merge the app fails closed. `/api/v1` and `/api/health/*` are unchanged.

## Test plan

- [ ] `uv run pytest` passes
- [ ] `test_every_web_route_is_gated` passes
- [ ] Live check after deploy: sign in as an admin and as a viewer; confirm the proxy headers (`request.url.scheme` and the client IP in the logs)

Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Not run by an implementer. depends-on: Task 4.4 Step 5 [completion].

- [ ] **Step 7: Post-deploy verification (orchestrator and owner)**

`#VERIFY` after the deploy, in this order: sign in through Authentik as an admin and as a viewer; confirm a viewer gets no edit button and a 403 on `GET /entities/{id}/edit`; confirm the logs show `https` and the real client IP for a request through the proxy; with the break-glass login enabled in a maintenance window, sign in once and confirm the `local_login_succeeded` WARNING log line. Record the results in `docs/guides/authentik-setup.md` and tick the live-check item in `docs/planning/adr/adr-001-initial-architecture.md`.

## Open risks

Each risk names the check that closes it. None blocks starting PR 1 to PR 3.

| Risk | Tag | Status and check |
| --- | --- | --- |
| Authentik may not emit a `groups` claim with the chosen scopes. | `#ASSUME` | Unverified, and the plan's own open assumption (`PROJECT-PLAN.md` line 800). `#VERIFY` step 4 of `docs/guides/authentik-setup.md` before PR 4 deploys. Without the claim every sign-in lands on the 403 page. |
| The compose files forward neither `LLC_MANAGER_SECRET_KEY` nor `LLC_MANAGER_API_KEY`, and there is no `env_file`. | `#ASSUME` | PR 4 forwards only the new auth settings. How production gets the secret key (the cookie signing key) is not visible in the repository. `#VERIFY` that the production deployment delivers a 32-character-or-longer `LLC_MANAGER_SECRET_KEY`; if it does not, the app already refuses to start outside development, so the failure is loud. |
| The break-glass throttle is per process, and production runs two replicas. | `#ASSUME` | Effective limit is 5 failures per 15 minutes per client IP per replica. Accepted for a single break-glass account behind a switch that is off by default. Shared state (Redis) is a follow-up if the limit must be global. |
| Proxy trust has not been exercised against the real Traefik or Pangolin. | `#ASSUME` | The tests use the test client with a synthetic peer address. `#VERIFY` task 4.4 step 7: log `request.url.scheme` and the client IP from a real request through the proxy, then set `LLC_MANAGER_TRUSTED_PROXY_IPS` to the proxy network. |
| PR 4 fails closed. A host-side watcher may auto-pull the image built on each `main` merge. | `#CRITICAL` | Do not auto-merge PR 4. Merge only after the deploy prerequisites hold. PR 1 to PR 3 are safe to auto-merge: an unconfigured production environment starts as before. |
| A signed cookie cannot be revoked before it expires. | `#ASSUME` | Bounded by `session_max_age_seconds` (8 hours). Rotating `LLC_MANAGER_SECRET_KEY` signs everyone out at once. Recorded in `session.py` and ADR-003. |
| `authlib` 1.9 prints a deprecation warning that its `httpx` module is deprecated in favor of `httpx2`. | none | Harmless today: the repository does not turn warnings into errors. Watch for an `authlib` release that drops the old module and re-run the OIDC flow tests when upgrading. |
| FastAPI changed how included routers appear in `app.routes` between the locked 0.138.2 and 0.162. | `#EDGE` | The route-enumeration test flattens both shapes and was run on both versions. A future major change could break the walker; the negative test `test_enumeration_detects_an_ungated_route` fails loudly if it stops seeing routes. |
| Three problems exist already and are out of scope: the CSP says `script-src 'self'` while `base.html` loads HTMX and Alpine from a CDN; `/api/docs` and `/api/openapi.json` are unauthenticated; the navigation links `/documents` and `/compliance` have no routes. | none | File each as its own issue. This plan does not touch them. The CSP mismatch could surface once real users reach the gated pages; check the browser console after the first deploy. |

## Self-review

### Spec coverage

Each row maps a spec clause to the task step that implements it and, where the plan departs from the spec, says so. "Test" names the test that proves it.

| Spec clause | Implemented in | Test or note |
| --- | --- | --- |
| Decision: M1 protects the web UI only; `/api/v1` keeps `X-API-Key` | Task 4.2 Step 4 gates `web/routes.py` and `api/ui.py` only | `TestAnonymous::test_api_key_routes_are_unaffected`; Task 4.4 Step 2 |
| Decision: Authentik application and groups do not exist yet; ship a checklist and a token check | Task 4.3 Step 1 | Guide step 4 checks the `groups` claim |
| Decision: break-glass local admin, argon2, off by default | Task 1.3 Step 3 (settings), Task 3.2 Steps 3 and 4 | `TestBreakGlassSettings`, `TestDisabled` |
| Decision: HTTPS behind Traefik needs a public base URL and trusted proxies | Task 1.3 Step 3, Task 3.3 Step 3 | `TestPublicBaseUrl`, `test_auth_proxy_trust.py` |
| Decision: signed cookie via `SessionMiddleware`, no server table | Task 2.3 Step 3, Task 2.5 Step 5 | `test_auth_session.py` |
| Non-goal: delete `authentik_jwks_url` and `authentik_audience` | Task 1.3 Steps 1 to 3, Task 1.4 Step 1 | `test_removed_bearer_jwt_settings_are_gone` |
| Non-goal: logout clears the app session only | Task 2.5 Step 4 (`logout`) | `TestLogout::test_logout_clears_the_session` |
| Non-goal: roles are global | Task 2.2 Step 3 | `Role` has two values, no per-entity scope |
| Architecture: `oidc.py` | Task 2.5 Step 3 | `TestClientConstruction` |
| Architecture: `roles.py` | Task 2.2 Step 3 | `test_auth_roles.py` |
| Architecture: `session.py` | Task 2.3 Step 3 | `test_auth_session.py` |
| Architecture: `csrf.py` | Task 2.4 Step 3 | `TestVerifyCsrf`. The token itself is minted in `session.py` (`csrf_token`); `csrf.py` holds only the check |
| Architecture: `dependencies.py` with `require_user`, `require_admin`, `verify_csrf` | Task 2.4 Step 3 | Departure: `verify_csrf` lives in `csrf.py`, not `dependencies.py`, to avoid a cycle with `session.py` |
| Architecture: `routes.py` with login, callback, logout, local login | Task 2.5 Step 4, Task 3.2 Step 4 | `test_auth_oidc_flow.py`, `test_auth_break_glass.py` |
| Architecture: extra modules not in the spec | Task 2.1 (`redirects.py`), Task 3.1 (`throttle.py`), Task 4.2 Step 3 (`templating.py`) | Each holds one job the spec described in prose |
| Architecture: cookie signed with `secret_key` | Task 2.5 Step 5 | `test_session_signed_with_another_key_is_rejected` |
| Architecture: new runtime dependencies | Task 1.2 | `test_auth_packaging.py` |
| Settings: all twelve, with the stated defaults | Task 1.3 Step 3 | `TestDefaults::test_defaults` |
| Settings: `public_base_url` required in production and `https://` | Task 1.3 Step 3 (https), Task 4.1 Step 3 (required) | `TestPublicBaseUrl`, `TestProductionRequiresSignIn` |
| Production validation: dev mode refused | Task 1.3 Step 3 | `TestDevMode::test_refused_in_production` |
| Production validation: incomplete OIDC unless break-glass is the only login | Task 1.3 Step 3 (partial set rejected), Task 4.1 Step 3 (production needs OIDC or break-glass) | `TestOidcConsistency`, `test_break_glass_alone_is_enough` |
| Production validation: break-glass enabled without a hash | Task 1.3 Step 3 | `TestBreakGlassSettings::test_enabled_without_hash_is_rejected` |
| Gating: `require_user` at router level; open paths `/auth/*`, `/api/health/*`, static | Task 4.2 Step 4 | `test_every_web_route_is_gated` |
| Gating: page request gets 303 to `/auth/login?next=` | Task 2.4 Step 3 | `test_page_request_without_session_redirects_to_login` |
| Gating: HTMX request gets 401 plus `HX-Redirect` | Task 2.4 Step 3 | `test_htmx_request_gets_401_with_hx_redirect`, `TestAnonymous::test_htmx_request_gets_401_and_hx_redirect` |
| Gating: `next` is relative with a single `/`, checked when stored and after the callback | Task 2.1 Step 3, Task 2.5 Step 4 | `test_auth_redirects.py`, `test_unsafe_next_is_replaced_by_default` |
| Roles: viewer reads three pages | Task 4.2 Step 4 | `TestViewer::test_can_read_pages` |
| Roles: admin also edits; viewer gets 403; templates hide edit controls | Task 4.2 Steps 4 and 5 | `TestViewer`, `TestAdmin::test_edit_button_is_shown` |
| Login 1: `/auth/login` creates state, nonce, PKCE and redirects | Task 2.5 Step 4 | `test_redirects_to_provider_with_state_nonce_and_pkce` |
| Login 2: callback validates issuer, audience, nonce, expiry | Task 2.5 Step 4 | `test_invalid_id_token_is_rejected_without_a_session`, `test_state_mismatch_is_rejected` |
| Login 3: groups map to a role, admin wins; no group or claim renders 403 and logs | Task 2.2 Step 3, Task 2.5 Step 4 | `test_user_without_a_known_group_gets_403_page` |
| Login 4: clear the old session, new session, new CSRF token, expiry | Task 2.3 Step 3 | `test_new_login_mints_a_new_csrf_token`, `test_absolute_expiry_is_enforced` |
| Login 5: redirect to the validated `next` or `/entities` | Task 2.5 Step 4 | `test_admin_login_creates_session_and_returns_to_next` |
| Logout: `POST /auth/logout` with CSRF; Authentik session stays | Task 2.5 Step 4 | `test_logout_requires_csrf_token`, `test_get_logout_is_not_allowed` |
| Cookie: `llc_session`, `HttpOnly`, `Secure`, `SameSite=Lax`, `max_age` | Task 2.5 Step 5 | `test_session_cookie_is_hardened`. Departure: `Secure` only when `public_base_url` is https (see "Verified facts", item 14) |
| CSRF: token in `hx-headers` on `<body>` | Task 4.2 Step 5 | `TestPageChrome::test_body_carries_the_csrf_token_for_htmx` |
| CSRF: `verify_csrf` on every non-safe web request and `POST /auth/logout`, constant time, 403 | Task 2.4 Step 3, Task 4.2 Step 4 | `TestVerifyCsrf`, `TestAdmin::test_save_without_csrf_token_is_forbidden` |
| CSRF: plain forms carry a hidden field; the break-glass form seeds a token | Task 3.2 Steps 3 and 4 | `test_form_is_shown_with_a_csrf_token` |
| Break-glass: 404 unless enabled and a hash is set | Task 3.2 Step 4 | `TestDisabled` (four cases) |
| Break-glass: one admin account; argon2 check | Task 3.2 Step 4 | `test_correct_password_signs_in_as_admin`, `test_corrupt_stored_hash_fails_closed` |
| Break-glass: 5 failures per 15 minutes per client IP | Task 3.1 Step 3, Task 3.2 Step 4 | `test_auth_throttle.py`, `TestRateLimit` |
| Break-glass: every attempt logged at WARNING with the correlation ID | Task 3.2 Step 4 | `TestLogging` |
| Break-glass: outage page links to the form only if enabled | Task 2.5 Step 4 (link), Task 3.2 Step 4 (form) | `TestOutagePageLink` |
| Proxy trust: forwarded headers honored only from `trusted_proxy_ips` | Task 3.3 Step 3 | `test_auth_proxy_trust.py`. Departure: in-app `ProxyHeadersMiddleware`, `Dockerfile` unchanged (see "Verified facts", item 1) |
| Proxy trust: `#VERIFY` scheme and client IP from a real request | Task 4.4 Step 7 | Manual, after deploy |
| Dev mode: fixed admin, refused in production, startup warning | Task 1.3 Step 3, Task 2.4 Step 3, Task 2.5 Step 5 | `TestDevMode`, `test_dev_mode_acts_as_admin_without_a_session`, `test_dev_mode_logs_a_startup_warning` |
| Errors: 503 on an unreachable Authentik | Task 2.5 Step 4 | `test_provider_outage_during_discovery_shows_retry_page`, `test_provider_outage_shows_retry_page` |
| Errors: 400 on state, nonce, or token failure | Task 2.5 Step 4 | `test_invalid_id_token_is_rejected_without_a_session`, `test_state_mismatch_is_rejected`, `test_provider_error_response_is_rejected` |
| Errors: 403 for no matching group; redirect for no session; 403 for CSRF | Task 2.5 Step 4, Task 2.4 Step 3 | `test_user_without_a_known_group_gets_403_page`, `TestRequireUser`, `TestVerifyCsrf` |
| Testing: role mapping parametrized (admin, viewer, both, neither, missing, wrong case) | Task 2.2 Step 1 | `test_auth_roles.py` |
| Testing: `next`, CSRF, session expiry, settings validators | Tasks 2.1, 2.4, 2.3, 1.3 | Their test files |
| Testing: OIDC flow with the token exchange mocked, no network | Task 2.5 Step 1 | `tests/oidc_fake.py`, `test_auth_oidc_flow.py` |
| Testing: break-glass disabled, wrong password, rate limit, logging | Task 3.2 Step 1 | `test_auth_break_glass.py` |
| Testing: route enumeration fails on an ungated route | Task 4.2 Step 1 | `test_every_web_route_is_gated`, `test_enumeration_detects_an_ungated_route` |
| Testing: existing web tests get an authenticated client | Task 4.2 Step 1 | `test_web_entities.py` diff |
| Setup checklist steps 1 to 5 | Task 4.3 Step 1 | `docs/guides/authentik-setup.md` |
| Docs: ADR-003 | Task 1.1 | Docs build |
| Docs: `.env.example` entries | Task 4.3 Step 4 | Pre-commit |
| Docs: outage runbook | Task 4.3 Step 2 | Front-matter validator, docs build |
| Docs: ADR-001, ADR-002, system overview, tech-spec env names | Task 4.3 Steps 5 and 6 | Docs build |
| Docs: align roadmap numbering to `PROJECT-PLAN.md` | Task 4.3 Step 7 | Manual review |
| Delivery: four PRs, gating last | Delivery map; Tasks 1.4, 2.6, 3.4, 4.4 | Hard rule re-checked in Tasks 2.5 Step 7 and 3.4 Step 2 |
| Delivery: deployment order for PR 4 | "Deploy prerequisites for PR 4"; Task 4.4 Steps 5 and 7 | Orchestrator checklist |
| Out of scope: CSP and CDN, open API docs, unrouted nav links | "Open risks" | Not changed |
| Risk: group renamed in Authentik | Task 1.3 (names are settings), Task 4.3 Step 1 (guide records them) | Guide |
| Risk: cookie cannot be revoked | `#ASSUME` in `session.py`; "Open risks" | Documented |
| Risk: redirect URI built from a spoofed `Host` | Task 2.5 Step 3 (`redirect_uri`) | `test_redirect_uri_is_under_the_public_origin` |
| Risk: locked out after gating deploys | Task 3.2 (break-glass ships first), "Deploy prerequisites for PR 4" | Ordering |

### Type and name consistency

Every name below is defined once and used with the same spelling and signature in later tasks.

| Name | Defined in | Used by |
| --- | --- | --- |
| `safe_next(value: str \| None) -> str`, `DEFAULT_NEXT` | `auth/redirects.py` (Task 2.1) | `auth/dependencies.py` (2.4), `auth/routes.py` (2.5, 3.2) |
| `Role` (`ADMIN`, `VIEWER`), `resolve_role(claims, *, groups_claim, admin_group, viewer_group) -> Role \| None` | `auth/roles.py` (Task 2.2) | `auth/session.py` (2.3), `auth/dependencies.py` (2.4), `auth/routes.py` (2.5, 3.2) |
| `SessionUser`, `store_user(session, user, *, max_age, now=None)`, `load_user(session, *, now=None)`, `csrf_token(session)`, `expected_csrf_token(session)`, `SESSION_COOKIE` | `auth/session.py` (Task 2.3) | `auth/csrf.py`, `auth/dependencies.py` (2.4), `auth/routes.py` (2.5, 3.2), `auth/templating.py` (4.2), `main.py` (2.5), `tests/auth_helpers.py` (2.4) |
| `verify_csrf`, `SAFE_METHODS`, `CSRF_HEADER`, `CSRF_FORM_FIELD` | `auth/csrf.py` (Task 2.4) | `auth/routes.py` (2.5, 3.2), `web/routes.py` (4.2), `tests/unit/test_web_gating.py` (4.2) |
| `require_user`, `require_admin`, `current_user`, `is_htmx`, `LOGIN_PATH` | `auth/dependencies.py` (Task 2.4) | `auth/routes.py` (2.5), `auth/templating.py`, `api/ui.py`, `web/routes.py` (4.2) |
| `OidcClient`, `build_oidc_client(config)`, `get_oidc_client(request)`, `discovery_url`, `redirect_uri`, `CLIENT_NAME` | `auth/oidc.py` (Task 2.5) | `auth/routes.py` (2.5), `main.py` (2.5), `tests/oidc_fake.py` and `tests/unit/test_auth_oidc_flow.py` (2.5) |
| `LoginThrottle` (`is_blocked`, `retry_after`, `record_failure`, `reset`) | `auth/throttle.py` (Task 3.1) | `auth/routes.py` (3.2), `main.py` (`app.state.login_throttle`, 3.2) |
| `install_auth_globals(templates)` | `auth/templating.py` (Task 4.2) | `core/templates.py` (4.2) |
| `configure_production_sign_in(monkeypatch)` | `tests/auth_helpers.py` (Task 4.1) | `test_api_key_auth.py`, `test_security_audit_fixes.py` (4.1) |
| `Settings` fields `public_base_url`, `authentik_issuer`, `authentik_client_id`, `authentik_client_secret`, `authentik_groups_claim`, `admin_group`, `viewer_group`, `session_max_age_seconds`, `local_admin_enabled`, `local_admin_password_hash`, `trusted_proxy_ips`, `auth_dev_mode`, property `oidc_configured` | `core/config.py` (Task 1.3) | `auth/oidc.py`, `auth/routes.py`, `auth/dependencies.py`, `main.py` (2.5, 3.2, 3.3), the production validator (4.1) |
| Environment names `LLC_MANAGER_<FIELD>` in upper case | Task 1.3 | `.env.example`, `docker-compose.yml`, the guides, and the tech-spec table (4.3) |
| Branch and worktree slugs `auth-settings`, `auth-oidc-session`, `auth-break-glass`, `auth-gate-web` | Delivery map | Tasks 1.0, 2.0, 3.0, 4.0 and each PR step |

Checks run on this plan:

- Every code block was produced from the scratch tree that passed each stage; the assembled stage-by-stage replay of Tasks 2.1 to 4.2 (tests, then implementation) reproduced the final PR 4 tree exactly and passed 767 tests, excluding only `tests/unit/test_import_excel.py`.
- The full test file for each task was run red and then green in that replay; the failure counts quoted in the "see it fail" steps come from that run.
- `git apply --check` accepted every diff block against the state it applies to.
- No em-dash characters and no emojis appear in the plan.
- The roadmap edit in Task 4.3 Step 7 names its old rows in words, because the real rows carry emoji that this plan does not reproduce.
