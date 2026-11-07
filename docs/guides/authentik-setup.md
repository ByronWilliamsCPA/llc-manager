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

The web UI signs users in through Authentik. Hostnames and the application slug
in this guide (`<your-host>`, `<authentik-host>`, `<slug>`) are placeholders;
use your own values.

!!! warning "Do this before you deploy the build that gates the web UI"
    The Authentik application, the two groups, and every environment variable
    in step 5 must exist **before** you deploy a build that includes the web
    gate. The application now fails closed: outside an explicit development,
    local, or test environment it refuses to start (a `ConfigurationError`
    naming the missing variables) unless `LLC_MANAGER_PUBLIC_BASE_URL` is set
    and either the full Authentik settings or the break-glass login is
    configured. If a host watcher pulls the image on every merge, a deploy with
    a missing value leaves the container crash-looping, and the previous image
    keeps serving only if your tooling rolls back.

## Before you start

You need admin access to Authentik, the public HTTPS hostname that serves LLC
Manager, and a place to keep secrets (never this repository).

## 1. Create the groups

Create two groups in Authentik. The names below are the defaults; if you choose
others, set `LLC_MANAGER_ADMIN_GROUP` and `LLC_MANAGER_VIEWER_GROUP` to match.
Matching is exact and case-sensitive.

| Group | Role in LLC Manager |
| --- | --- |
| `llc-manager-admins` | Admin: read everything, edit entities |
| `llc-manager-viewers` | Viewer: read only, no edit controls |

A user in both groups is an admin. A user in neither is refused with a 403
page, and any session is cleared.

## 2. Create the provider

Create an OAuth2/OpenID provider:

- Client type: confidential.
- Authorization flow: authorization code. The app sends a PKCE challenge
  (`S256`).
- Redirect URI (strict match): `https://<your-host>/auth/callback`.
- Signing key: a key that signs ID tokens.
- Scopes: `openid`, `profile`, `email`. The app asks for exactly
  `openid profile email`.
- The `groups` claim must be inside the ID token (see step 4).

## 3. Create the application

Create an application that uses the provider, with slug `<slug>`. The issuer
the app must be given is
`https://<authentik-host>/application/o/<slug>/`. Bind the application to the
two groups so users outside them cannot finish the Authentik login either.

## 4. Confirm the groups claim

This is the assumption the whole role mapping rests on, and it has not been
checked against the real Authentik instance. Verify it before deploying. The
app reads roles from the **ID token** only; it never calls the userinfo
endpoint, so a claim that appears only there does not count.

1. Open the provider in the Authentik admin interface and use its **Preview**
   tab to pick a test user in one of the groups, or obtain a real ID token for
   that user from a test sign-in.
2. Decode the token payload on your own machine (never paste a token into a
   public website). With the token in the `ID_TOKEN` shell variable:

   ```bash
   python3 -c "import base64, json, os; p = os.environ['ID_TOKEN'].split('.')[1]; print(json.dumps(json.loads(base64.urlsafe_b64decode(p + '=' * (-len(p) % 4))), indent=2))"
   ```

   This only decodes; it does not verify the signature, which is fine for
   this check.
3. Confirm a `groups` claim that is a list of group **names**, for example
   `["llc-manager-admins"]`, and that `iss` equals the issuer you will
   configure.

If the claim is missing, add a scope mapping to the provider with this
expression and attach it to the `profile` scope:

```python
return {"groups": [group.name for group in request.user.ak_groups.all()]}
```

If your token uses another claim name, set `LLC_MANAGER_AUTHENTIK_GROUPS_CLAIM`.
Without a usable claim every sign-in lands on the 403 page.

## 5. Set the environment

Set these in the secrets manager or stack environment, never in git. Variable
names carry the `LLC_MANAGER_` prefix (the environment name may also be given
unprefixed as `ENVIRONMENT`; the prefixed name wins).

Required in production:

| Variable | Value |
| --- | --- |
| `LLC_MANAGER_ENVIRONMENT` | `production` (any name other than `development`, `local`, `test`). An unset or blank name counts as production for every startup check: the sign-in requirement, the secret key, and the API key length. The name may also come from a `.env` file |
| `LLC_MANAGER_PUBLIC_BASE_URL` | `https://<your-host>` (https only, no path) |
| `LLC_MANAGER_AUTHENTIK_ISSUER` | `https://<authentik-host>/application/o/<slug>/` (https) |
| `LLC_MANAGER_AUTHENTIK_CLIENT_ID` | the provider's client ID |
| `LLC_MANAGER_AUTHENTIK_CLIENT_SECRET` | the provider's client secret |
| `LLC_MANAGER_SECRET_KEY` | 32 or more random characters (`openssl rand -hex 32`); it signs the session cookie, and rotating it signs everyone out. The default and any value starting with `change-` are refused at startup |
| `LLC_MANAGER_API_KEY` | 32 or more characters for the service API (`/api/v1`); unset makes every `/api/v1` call answer 503. `docker-compose.prod.yml` refuses to start without it |

The issuer, client ID, client secret, and public base URL must be set
together. The break-glass login can replace the three Authentik values (see
below) but never `LLC_MANAGER_PUBLIC_BASE_URL`.

Strongly recommended:

| Variable | Value |
| --- | --- |
| `LLC_MANAGER_TRUSTED_PROXY_IPS` | comma-separated IPs or CIDR networks of your reverse proxy; empty trusts none |

Optional, with defaults:

| Variable | Default |
| --- | --- |
| `LLC_MANAGER_ADMIN_GROUP` | `llc-manager-admins` |
| `LLC_MANAGER_VIEWER_GROUP` | `llc-manager-viewers` |
| `LLC_MANAGER_AUTHENTIK_GROUPS_CLAIM` | `groups` |
| `LLC_MANAGER_SESSION_MAX_AGE_SECONDS` | `28800` (8 hours, absolute) |
| `LLC_MANAGER_LOCAL_ADMIN_ENABLED` | `false` |
| `LLC_MANAGER_LOCAL_ADMIN_PASSWORD_HASH` | unset |

`LLC_MANAGER_AUTH_DEV_MODE` is for local development only; startup refuses it
outside an explicit development, local, or test environment.

## 6. Verify behind the proxy

After deploying, open the site in a private window and confirm:

1. You are sent to Authentik and return to the page you asked for.
2. The page shows your name and role, and a viewer sees no Edit button and gets
   a 403 on `/entities/<id>/edit`.
3. The logs show `https` as the scheme and your real address as the client IP
   for a request through the proxy. If they show `http` and the proxy address,
   the proxy address is missing from `LLC_MANAGER_TRUSTED_PROXY_IPS`, or the
   proxy does not send `X-Forwarded-For` and `X-Forwarded-Proto`.
4. Signing out returns the "Signed out" page and a protected page sends you
   back to sign in.

Record the results here and tick the live-check item in
`docs/planning/adr/adr-001-initial-architecture.md`.

## Break-glass local admin (optional)

For Authentik outages you can enable one local admin login. It is off by
default, is not in the normal navigation, and is linked only from the
sign-in message pages when it is enabled. See the
[outage runbook](authentik-outage-runbook.md) for the procedure.

1. Generate an argon2 hash on a trusted machine, typing the password at the
   prompt (the hash, not the password, is what you store):

   ```bash
   uv run python -c "import getpass; from argon2 import PasswordHasher; print(PasswordHasher().hash(getpass.getpass()))"
   ```

2. Set `LLC_MANAGER_LOCAL_ADMIN_PASSWORD_HASH` to the printed hash and
   `LLC_MANAGER_LOCAL_ADMIN_ENABLED=true`. The hash contains `$`; in a `.env`
   file wrap it in single quotes so it is not interpolated.
3. The login lives at `/auth/local-login` and answers 404 unless both values
   are set.

## Local development

Set `LLC_MANAGER_ENVIRONMENT=development` (the `.env.example` default
`ENVIRONMENT=development` does this) and `LLC_MANAGER_AUTH_DEV_MODE=true` to
skip Authentik and act as a fixed admin user. A development environment starts
without any sign-in settings; every other environment name does not.
An unset name is not development: it needs a real secret key as well as the
sign-in settings, so set the name explicitly on every local machine.
