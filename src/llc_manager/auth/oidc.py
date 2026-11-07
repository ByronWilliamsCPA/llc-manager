"""Authentik OpenID Connect client, wrapped behind a small typed protocol."""

from typing import Protocol, cast

from authlib.integrations.starlette_client import OAuth
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

    async def authorize_access_token(
        self, request: Request, *, claims_options: dict[str, dict[str, object]]
    ) -> dict[str, object]:
        """Exchange the callback code and validate the ID token."""
        ...


def discovery_url(issuer: str) -> str:
    """Build the OIDC discovery document URL for an issuer.

    Args:
        issuer (str): The issuer URL, with or without a trailing slash.

    Returns:
        str: The ``.well-known/openid-configuration`` URL.
    """
    return issuer.rstrip("/") + "/.well-known/openid-configuration"


def issuer_claims_options(issuer: str) -> dict[str, dict[str, object]]:
    """Build the ID token claim rules that pin the issuer.

    Both trailing-slash spellings are accepted, so the configured issuer and
    the one Authentik emits cannot disagree over a slash alone.

    Args:
        issuer (str): The configured issuer URL.

    Returns:
        dict[str, dict[str, object]]: Rules for ``authorize_access_token``.
    """
    # #CRITICAL: without explicit options authlib trusts the issuer advertised
    # by the discovery document, so a substituted document would vouch for
    # itself. The expected issuer must come from configuration.
    # #VERIFY: TestConfiguredIssuerIsEnforced.
    base = issuer.rstrip("/")
    return {"iss": {"essential": True, "values": [base, base + "/"]}}


def redirect_uri(public_base_url: str) -> str:
    """Build the callback URL registered with Authentik.

    Args:
        public_base_url (str): The normalized public origin.

    Returns:
        str: The absolute callback URL.
    """
    # #CRITICAL: the redirect URI must come from configuration only. Building it
    # from the request Host header would let an attacker steer the code
    # exchange to another origin.
    # #VERIFY: test_redirect_uri_ignores_the_request_host.
    return public_base_url + CALLBACK_PATH


def build_oidc_client(config: Settings) -> OidcClient | None:
    """Create the OIDC client, or ``None`` when OIDC is not configured.

    Discovery is lazy: no network call happens until the first login, so an
    unreachable Authentik cannot stop the app from starting.

    Args:
        config (Settings): Application settings.

    Returns:
        OidcClient | None: A configured client, or ``None``.
    """
    if (
        not config.oidc_configured
        or config.authentik_issuer is None
        or config.authentik_client_id is None
        or config.authentik_client_secret is None
    ):
        return None
    # #ASSUME: Authentik emits the configured groups claim in the ID token
    # (spec "Authentik setup checklist", step 4); without it every sign-in
    # lands on the 403 page.
    # #VERIFY: sign in as a member of each group and read the groups claim.
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
        request (Request): The incoming request.

    Returns:
        OidcClient | None: The configured client, or ``None`` when OIDC is not
        configured.
    """
    return cast("OidcClient | None", getattr(request.app.state, "oidc_client", None))
