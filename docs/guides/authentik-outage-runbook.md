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

Use this when sign-in fails because Authentik is down or unreachable. LLC
Manager shows a "Sign-in is temporarily unavailable" page (HTTP 503) in that
case. The service API (`/api/v1`, `X-API-Key`) and the health probes are not
affected.

## 1. Confirm it is Authentik

1. Open the Authentik login page directly. If it does not load, the outage is
   on the Authentik side; start there.
2. Check the LLC Manager logs for the `oidc_provider_unreachable` event. It
   carries the error class and the correlation ID (the `X-Correlation-ID`
   response header of the failed request) and never the response body.
3. Check that `LLC_MANAGER_AUTHENTIK_ISSUER` still matches the provider slug. A
   renamed provider looks like an outage.

A sign-in that fails with "Sign-in failed" (HTTP 400) or "Access denied"
(HTTP 403) is not an outage: the first means the response could not be
verified, the second means the account is in neither group.

## 2. Wait or use break-glass

If Authentik will be back soon, wait. Existing sessions keep working until they
expire (8 hours by default); only new sign-ins fail.

If you need access now and the break-glass login was enabled ahead of time:

1. Open `/auth/local-login` on the public hostname.
2. Enter the break-glass password. You get a normal admin session marked
   `auth_method: local`.
3. After five failed attempts from one address in fifteen minutes the login
   answers 429 with a `Retry-After` header. Do not hammer it.

If break-glass was not enabled, you must change the environment and restart:

1. Generate an argon2 hash (see the [setup guide](authentik-setup.md)) and set
   `LLC_MANAGER_LOCAL_ADMIN_PASSWORD_HASH` and
   `LLC_MANAGER_LOCAL_ADMIN_ENABLED=true` in the stack environment.
2. Restart the container. The Authentik settings can stay in place.

## 3. Leave no door open

When Authentik is back:

1. Set `LLC_MANAGER_LOCAL_ADMIN_ENABLED=false` (or unset it) and restart. If
   break-glass is your only sign-in method the application will refuse to start
   without it, so keep the Authentik settings configured.
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
