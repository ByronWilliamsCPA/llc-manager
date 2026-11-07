"""Sign-in, callback and sign-out routes, mounted at ``/auth``."""

import json
from typing import Annotated, cast

import httpx
from authlib.integrations.base_client import OAuthError
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

# A provider that cannot be reached, or whose discovery or token response is
# unusable, is an outage for our purposes. authlib raises RuntimeError for a
# discovery document that lacks an endpoint or key set, and KeyError for one
# that lacks a required field; neither may surface as a 500.
# #EDGE: only the exception class name is logged, never its message, because a
# message can echo provider-supplied text.
# #VERIFY: tests/unit/test_auth_oidc_flow.py::TestBrokenDiscoveryDocument.
_PROVIDER_FAILURES = (
    httpx.HTTPError,
    json.JSONDecodeError,
    RuntimeError,
    KeyError,
)


def _message(
    request: Request,
    *,
    title: str,
    message: str,
    status_code: int,
    show_login: bool = False,
) -> HTMLResponse:
    """Render the standalone message page.

    Args:
        request (Request): The incoming request.
        title (str): Page heading.
        message (str): Explanatory text.
        status_code (int): HTTP status of the response.
        show_login (bool): Whether to offer a link to sign in again.

    Returns:
        HTMLResponse: The rendered page.
    """
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


def _not_configured(request: Request) -> HTMLResponse:
    """Render the page shown when single sign-on is not configured.

    Args:
        request (Request): The incoming request.

    Returns:
        HTMLResponse: A 503 message page.
    """
    return _message(
        request,
        title="Sign-in unavailable",
        message="Single sign-on is not configured for this site.",
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def _provider_unreachable(request: Request, exc: Exception) -> HTMLResponse:
    """Log and render the page shown when Authentik cannot be reached.

    Args:
        request (Request): The incoming request.
        exc (Exception): The transport or decoding failure.

    Returns:
        HTMLResponse: A 503 message page with a retry link.
    """
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


def _text_claim(claims: dict[str, object], key: str) -> str | None:
    """Return a claim only if it is text.

    Args:
        claims (dict[str, object]): Verified ID token claims.
        key (str): Claim name.

    Returns:
        str | None: The claim value, or ``None`` when absent or not text.
    """
    value = claims.get(key)
    return value if isinstance(value, str) and value else None


@router.get("/login")
async def login(
    request: Request,
    oidc: OidcDep,
    next_: Annotated[str | None, Query(alias="next")] = None,
) -> Response:
    """Start the Authentik sign-in, remembering where to return to.

    Args:
        request (Request): The incoming request.
        oidc (OidcDep): The configured OIDC client, if any.
        next_ (Annotated[str | None, Query(alias="next")]): Relative path to
            return to after sign-in.

    Returns:
        Response: A redirect to Authentik, or a message page when sign-in is
        unavailable.
    """
    target = safe_next(next_)
    if current_user(request) is not None:
        return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)
    base_url = settings.public_base_url
    if oidc is None or base_url is None:
        return _not_configured(request)
    # #EDGE: `next` is attacker-controlled and is validated here and again in
    # the callback, because the session round-trips through the browser.
    # #VERIFY: tests/unit/test_auth_oidc_flow.py (hostile next, planted session).
    request.session[_LOGIN_NEXT_KEY] = target
    try:
        return await oidc.authorize_redirect(request, redirect_uri(base_url))
    except _PROVIDER_FAILURES as exc:
        # Discovery is fetched lazily, so an outage first shows up here.
        return _provider_unreachable(request, exc)


@router.get("/callback")
async def callback(request: Request, oidc: OidcDep) -> Response:
    """Finish the sign-in: validate the ID token and start the session.

    Args:
        request (Request): The incoming request.
        oidc (OidcDep): The configured OIDC client, if any.

    Returns:
        Response: A redirect to the requested page, or an error message page.
    """
    if oidc is None:
        return _not_configured(request)
    # The login state lives in the session, so it is read now and the session
    # is only replaced after the token exchange has used it.
    target = safe_next(request.session.get(_LOGIN_NEXT_KEY))
    try:
        token = await oidc.authorize_access_token(request)
    except _PROVIDER_FAILURES as exc:
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
        cast("dict[str, object]", raw_claims) if isinstance(raw_claims, dict) else None
    )
    sub = _text_claim(claims, "sub") if claims is not None else None
    if claims is None or sub is None:
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
            sub=sub,
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

    # #CRITICAL: session fixation - store_user clears the pre-login session
    # (state, nonce, PKCE verifier, login_next) before writing the user.
    # #VERIFY: test_session_is_rebuilt_not_reused_on_callback.
    store_user(
        request.session,
        SessionUser(
            sub=sub,
            email=_text_claim(claims, "email"),
            name=_text_claim(claims, "name")
            or _text_claim(claims, "preferred_username"),
            role=role,
            auth_method="oidc",
        ),
        max_age=settings.session_max_age_seconds,
    )
    logger.info(
        "login_succeeded",
        method="oidc",
        sub=sub,
        role=role.value,
        correlation_id=get_correlation_id(),
    )
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout", dependencies=[Depends(verify_csrf)])
async def logout(request: Request) -> Response:
    """End the local session.

    The Authentik session is not ended, so the next sign-in may be silent.

    Args:
        request (Request): The incoming request.

    Returns:
        Response: A message page confirming sign-out.
    """
    request.session.clear()
    return _message(
        request,
        title="Signed out",
        message="You have been signed out of LLC Manager.",
        status_code=status.HTTP_200_OK,
        show_login=True,
    )
