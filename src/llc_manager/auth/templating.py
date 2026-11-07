"""Jinja helpers so templates can read the signed-in user and CSRF token."""

from typing import cast

from fastapi import Request
from fastapi.templating import Jinja2Templates

from llc_manager.auth.dependencies import current_user
from llc_manager.auth.session import SessionUser, csrf_token


def _template_current_user(request: Request) -> SessionUser | None:
    """Template global: the signed-in user for this request, if any.

    Args:
        request (Request): The request being rendered.

    Returns:
        SessionUser | None: The signed-in user, or ``None``.
    """
    return current_user(request)


def _template_csrf_token(request: Request) -> str:
    """Template global: this session's CSRF token, minted on first use.

    Args:
        request (Request): The request being rendered.

    Returns:
        str: The token for the ``X-CSRF-Token`` header or a hidden form field.
    """
    return csrf_token(request.session)


def install_auth_globals(templates: Jinja2Templates) -> Jinja2Templates:
    """Expose ``current_user(request)`` and ``csrf_token(request)`` to templates.

    Every ``Jinja2Templates`` instance that renders pages extending
    ``base.html`` must be passed through this function.

    Args:
        templates (Jinja2Templates): The templates instance to extend.

    Returns:
        Jinja2Templates: The same instance, for use in an assignment.
    """
    # Jinja types ``globals`` as a narrow union; callables are valid at runtime.
    template_globals = cast("dict[str, object]", templates.env.globals)
    template_globals["current_user"] = _template_current_user
    template_globals["csrf_token"] = _template_csrf_token
    return templates
