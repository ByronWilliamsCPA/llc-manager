"""Sign-in, callback and sign-out routes, mounted at ``/auth``."""

import contextlib
import json
import secrets
from functools import cache
from typing import Annotated, cast

import anyio
import anyio.to_thread
import httpx
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from authlib.integrations.base_client import OAuthError
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from joserfc.errors import JoseError

from llc_manager.auth.csrf import verify_csrf
from llc_manager.auth.dependencies import current_user
from llc_manager.auth.oidc import (
    OidcClient,
    get_oidc_client,
    issuer_claims_options,
    redirect_uri,
)
from llc_manager.auth.redirects import safe_next
from llc_manager.auth.roles import Role, resolve_role
from llc_manager.auth.session import SessionUser, csrf_token, store_user
from llc_manager.auth.throttle import GLOBAL_KEY, LoginThrottle, client_key
from llc_manager.core.config import settings
from llc_manager.core.templates import templates
from llc_manager.middleware.correlation import get_correlation_id
from llc_manager.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"], include_in_schema=False)

_LOGIN_NEXT_KEY = "login_next"

OidcDep = Annotated[OidcClient | None, Depends(get_oidc_client)]

LOCAL_ADMIN_SUB = "local-admin"
# Longer input is refused before any hashing: argon2 cost grows with input size.
_MAX_PASSWORD_LENGTH = 1024
_password_hasher = PasswordHasher()

# #CRITICAL: one argon2 verification allocates 64 MiB with the default
# parameters (more if the operator chose a costlier hash), and the production
# container is limited to 512 MiB. Running them in the shared thread pool
# (about 40 threads) would let a burst of attempts exhaust memory, so only one
# verification runs at a time per process. Attempts are already counted per
# client and globally before they get here, which bounds how many can queue.
# #VERIFY: test_concurrent_verifications_never_overlap.
_VERIFY_LIMITER = anyio.CapacityLimiter(1)


def get_login_throttle(request: Request) -> LoginThrottle:
    """FastAPI dependency: the break-glass throttle stored on the app.

    Args:
        request (Request): The incoming request.

    Returns:
        LoginThrottle: The app-wide throttle.
    """
    return cast("LoginThrottle", request.app.state.login_throttle)


ThrottleDep = Annotated[LoginThrottle, Depends(get_login_throttle)]


def get_global_login_throttle(request: Request) -> LoginThrottle:
    """FastAPI dependency: the failure budget shared by all clients.

    Args:
        request (Request): The incoming request.

    Returns:
        LoginThrottle: The app-wide budget.
    """
    return cast("LoginThrottle", request.app.state.global_login_throttle)


GlobalThrottleDep = Annotated[LoginThrottle, Depends(get_global_login_throttle)]


def require_local_login_enabled() -> None:
    """Hide the break-glass login (404) unless it is enabled and has a hash.

    Raises:
        HTTPException: 404 when the break-glass login is not available.
    """
    if not (settings.local_admin_enabled and settings.local_admin_password_hash):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


def _client_ip(request: Request) -> str:
    """Return the throttle key: the client address after proxy handling.

    Args:
        request (Request): The incoming request.

    Returns:
        str: ``request.client.host``, which the proxy-header middleware has
            already rewritten to the real client behind a trusted proxy.
    """
    # #CRITICAL: the throttle is only as good as this address. The raw
    # X-Forwarded-For header must never be read here; only the middleware may
    # rewrite request.client, and only for peers in trusted_proxy_ips.
    # #VERIFY: tests/unit/test_auth_proxy_trust.py (spoofed header, untrusted peer).
    return request.client.host if request.client else "unknown"


@cache
def _dummy_hash() -> str:
    """Return an argon2 hash of a random secret that nobody knows.

    Returns:
        str: A hash with the default parameters, computed once per process.
    """
    return _password_hasher.hash(secrets.token_urlsafe(32))


def _verify(stored_hash: str, password: str) -> bool:
    """Check ``password`` against ``stored_hash``; any failure is a mismatch.

    A stored value that is not a usable hash (argon2 raises ``InvalidHashError``
    or a plain ``VerificationError`` for it) fails immediately, which would
    answer faster than a real mismatch, so a dummy hash is verified instead to
    spend comparable time.

    Args:
        stored_hash (str): The configured argon2 hash.
        password (str): The submitted password.

    Returns:
        bool: True only when the password matches the hash.
    """
    # #ASSUME: the cost of a wrong-password check is the cost of one argon2
    # verification whether or not the stored hash is usable.
    # #VERIFY: test_a_corrupt_hash_still_costs_a_real_verification.
    try:
        return _password_hasher.verify(stored_hash, password)
    except VerifyMismatchError:
        return False
    except (VerificationError, InvalidHashError):
        # A malformed stored hash fails before any hashing work is done.
        with contextlib.suppress(VerificationError):
            _password_hasher.verify(_dummy_hash(), password)
        return False


async def _password_matches(password: str) -> bool:
    """Verify ``password`` against the configured hash off the event loop.

    Verifications are serialized per process; see ``_VERIFY_LIMITER``.

    Args:
        password (str): The submitted password.

    Returns:
        bool: True only when a hash is configured and the password matches.
    """
    stored = settings.local_admin_password_hash
    if stored is None:
        return False
    return await anyio.to_thread.run_sync(
        _verify,
        stored.get_secret_value(),
        password,
        limiter=_VERIFY_LIMITER,
    )


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
    if oidc is None or settings.authentik_issuer is None:
        return _not_configured(request)
    # The login state lives in the session, so it is read now and the session
    # is only replaced after the token exchange has used it.
    target = safe_next(request.session.get(_LOGIN_NEXT_KEY))
    try:
        token = await oidc.authorize_access_token(
            request, claims_options=issuer_claims_options(settings.authentik_issuer)
        )
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

    # #CRITICAL: the break-glass identity is reserved. A directory account with
    # this subject would otherwise be indistinguishable from the local
    # administrator in logs and audit trails.
    # #VERIFY: test_a_token_claiming_the_break_glass_subject_is_rejected.
    reserved = sub == LOCAL_ADMIN_SUB
    role = (
        None
        if reserved
        else resolve_role(
            claims,
            groups_claim=settings.authentik_groups_claim,
            admin_group=settings.admin_group,
            viewer_group=settings.viewer_group,
        )
    )
    if role is None:
        if reserved:
            logger.warning(
                "oidc_reserved_subject_rejected",
                correlation_id=get_correlation_id(),
            )
        else:
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
                "This account cannot sign in to LLC Manager."
                if reserved
                else "Your account is not a member of a group that may use "
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


def _local_login_form(
    request: Request,
    *,
    next_: str,
    error: str | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    """Render the break-glass form, seeding a CSRF token in the session.

    Args:
        request (Request): The incoming request.
        next_ (str): A validated in-site path to return to after sign-in.
        error (str | None): Message to show above the form.
        status_code (int): HTTP status of the response.

    Returns:
        HTMLResponse: The rendered form.
    """
    return templates.TemplateResponse(
        request,
        "auth/local_login.html",
        {"csrf_token": csrf_token(request.session), "next": next_, "error": error},
        status_code=status_code,
    )


@router.get("/local-login", dependencies=[Depends(require_local_login_enabled)])
async def local_login_form(
    request: Request,
    next_: Annotated[str | None, Query(alias="next")] = None,
) -> Response:
    """Show the break-glass login form.

    Args:
        request (Request): The incoming request.
        next_ (Annotated[str | None, Query(alias="next")]): Relative path to
            return to after sign-in.

    Returns:
        Response: The login form, or a redirect when already signed in.
    """
    target = safe_next(next_)
    if current_user(request) is not None:
        return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)
    return _local_login_form(request, next_=target)


@router.post(
    "/local-login",
    dependencies=[Depends(require_local_login_enabled), Depends(verify_csrf)],
)
async def local_login_submit(
    request: Request,
    throttle: ThrottleDep,
    global_throttle: GlobalThrottleDep,
    password: Annotated[str, Form(max_length=_MAX_PASSWORD_LENGTH)],
    next_: Annotated[str | None, Form(alias="next")] = None,
) -> Response:
    """Check the break-glass password and start an administrator session.

    #CRITICAL: this is a second login path. It stays off by default, uses an
    argon2 hash, is throttled per client IP, and logs every attempt.
    #VERIFY: ``tests/unit/test_auth_break_glass.py`` covers each of those.

    #ASSUME: the throttle lives in this process, so with two replicas the
    effective limit is 5 failures per 15 minutes per replica, not in total.
    #VERIFY: ``docs/planning/adr/adr-003-authentik-sso-web-login.md`` lists
    this under Negative consequences; revisit before adding workers.

    Args:
        request (Request): The incoming request.
        throttle (ThrottleDep): The per-client failure throttle.
        global_throttle (GlobalThrottleDep): The failure budget shared by all
            clients.
        password (Annotated[str, Form(max_length=_MAX_PASSWORD_LENGTH)]): The
            submitted password, at most 1024 characters.
        next_ (Annotated[str | None, Form(alias="next")]): Relative path to
            return to after sign-in.

    Returns:
        Response: A redirect on success, else the form again (401) or a
        throttle page (429).
    """
    target = safe_next(next_)
    client_ip = _client_ip(request)
    key = client_key(client_ip)
    correlation_id = get_correlation_id()

    # #CRITICAL: two budgets. The per-client one (keyed by address, IPv6 by /64)
    # stops one source; the global one stops a distributed guesser, at the cost
    # of locking the real operator out too while it is exhausted.
    # #VERIFY: tests/unit/test_auth_break_glass.py::TestGlobalBudget.
    blocked_scope = (
        "client"
        if throttle.is_blocked(key)
        else "global"
        if global_throttle.is_blocked(GLOBAL_KEY)
        else None
    )
    if blocked_scope is not None:
        logger.warning(
            "local_login_throttled",
            client_ip=client_ip,
            scope=blocked_scope,
            correlation_id=correlation_id,
        )
        response = _message(
            request,
            title="Too many attempts",
            message="Too many failed attempts. Try again later.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )
        retry_after = max(
            throttle.retry_after(key) if throttle.is_blocked(key) else 0,
            global_throttle.retry_after(GLOBAL_KEY)
            if global_throttle.is_blocked(GLOBAL_KEY)
            else 0,
        )
        response.headers["Retry-After"] = str(retry_after)
        return response

    # #EDGE: concurrent guesses. The attempt is counted before the slow hash
    # check, with no await in between, so parallel requests cannot all pass
    # the check above; a success clears the count again.
    # #VERIFY: test_the_attempt_is_counted_before_the_hash_is_checked.
    throttle.record_failure(key)
    global_throttle.record_failure(GLOBAL_KEY)
    if not await _password_matches(password):
        logger.warning(
            "local_login_failed",
            client_ip=client_ip,
            correlation_id=correlation_id,
        )
        return _local_login_form(
            request,
            next_=target,
            error="That password is not correct.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    throttle.reset(key)
    # The shared budget only gives back this attempt: a success must not erase
    # failures that other clients made.
    global_throttle.forget_latest(GLOBAL_KEY)
    # #CRITICAL: session fixation - store_user clears the pre-login session
    # and mints a new CSRF token before the user is written.
    # #VERIFY: test_session_is_rebuilt_not_reused_on_success.
    store_user(
        request.session,
        SessionUser(
            sub=LOCAL_ADMIN_SUB,
            email=None,
            name="Local administrator",
            role=Role.ADMIN,
            auth_method="local",
        ),
        max_age=settings.session_max_age_seconds,
    )
    logger.warning(
        "local_login_succeeded",
        client_ip=client_ip,
        correlation_id=correlation_id,
    )
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)
