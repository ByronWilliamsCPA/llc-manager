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
        request (Request): The incoming request.

    Returns:
        bool: True when the ``HX-Request`` header is ``true``.
    """
    return request.headers.get("HX-Request", "").lower() == "true"


def current_user(request: Request) -> SessionUser | None:
    """Return the signed-in user without enforcing anything.

    Args:
        request (Request): The incoming request.

    Returns:
        SessionUser | None: The dev user in dev mode, else the session user,
        else ``None``.
    """
    # #CRITICAL: dev mode signs everyone in as admin; the settings validator
    # refuses it outside development, local, and test environments.
    # #VERIFY: tests/unit/test_auth_settings.py covers the production refusal.
    if settings.auth_dev_mode:
        return _DEV_USER
    return load_user(request.session)


def _login_target(request: Request) -> str:
    """Pick where the user should land after signing in.

    Args:
        request (Request): The unauthenticated request.

    Returns:
        str: A validated in-site path.
    """
    # #EDGE: HX-Current-URL is client-supplied; safe_next rejects anything that
    # is not an in-site path.
    # #VERIFY: test_hostile_hx_current_url_falls_back_to_default.
    if is_htmx(request):
        try:
            current = urlsplit(request.headers.get("HX-Current-URL", ""))
        except ValueError:
            # #EDGE: a malformed URL such as `http://[` makes urlsplit raise;
            # the gate must still answer 401, not 500.
            # #VERIFY: test_malformed_hx_current_url_still_answers_401.
            return safe_next(None)
        candidate = current.path + (f"?{current.query}" if current.query else "")
        return safe_next(candidate)
    if request.method in {"GET", "HEAD"}:
        query = f"?{request.url.query}" if request.url.query else ""
        return safe_next(request.url.path + query)
    return safe_next(None)


async def require_user(request: Request) -> SessionUser:
    """Require a signed-in user.

    Args:
        request (Request): The incoming request.

    Returns:
        SessionUser: The signed-in user.

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


CurrentUser = Annotated[SessionUser, Depends(require_user)]


async def require_admin(user: CurrentUser) -> SessionUser:
    """Require a signed-in administrator.

    Args:
        user (CurrentUser): The signed-in user.

    Returns:
        SessionUser: The administrator.

    Raises:
        HTTPException: 403 when the user is not an administrator.
    """
    # #CRITICAL: viewers must never reach a write route; admin is the only
    # role that passes.
    # #VERIFY: TestRequireAdmin.test_viewer_is_forbidden.
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required",
        )
    return user
