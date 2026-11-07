"""Signed-cookie session helpers: the signed-in user and the CSRF token."""

import secrets
import time
from collections.abc import MutableMapping
from dataclasses import dataclass
from typing import Literal, cast, get_args

from llc_manager.auth.roles import Role

SESSION_COOKIE = "llc_session"
_USER_KEY = "user"
_CSRF_KEY = "csrf"

AuthMethod = Literal["oidc", "local", "dev"]
_AUTH_METHODS: tuple[str, ...] = get_args(AuthMethod)
Session = MutableMapping[str, object]


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
        session (Session): The request session mapping.
        user (SessionUser): The user to sign in.
        max_age (int): Absolute lifetime in seconds.
        now (float | None): Current epoch seconds (injectable for tests).
    """
    # #ASSUME: a signed cookie cannot be revoked server-side before `exp`; the
    # 8 hour lifetime is the only bound on a stolen cookie.
    # #VERIFY: rotating LLC_MANAGER_SECRET_KEY invalidates every session at once.
    # #CRITICAL: session fixation - nothing from before sign-in may survive.
    # #VERIFY: tests/unit/test_auth_session.py asserts pre-login keys are gone.
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


def _optional_text(value: object) -> str | None:
    """Return ``value`` if it is a string, ``None`` if absent.

    Args:
        value (object): A stored field.

    Returns:
        str | None: The text, or ``None`` when the field is absent.

    Raises:
        TypeError: If the field is present but not a string.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    message = "session user field must be text"
    raise TypeError(message)


def load_user(session: Session, *, now: float | None = None) -> SessionUser | None:
    """Return the signed-in user, or ``None`` if absent, expired or malformed.

    Args:
        session (Session): The request session mapping.
        now (float | None): Current epoch seconds (injectable for tests).

    Returns:
        SessionUser | None: The stored user, or ``None``.
    """
    raw = session.get(_USER_KEY)
    if not isinstance(raw, dict):
        return None
    data = cast("dict[str, object]", raw)
    current = time.time() if now is None else now
    exp = data.get("exp")
    if not isinstance(exp, int | float) or exp <= current:
        return None
    sub = data.get("sub")
    method = data.get("auth_method")
    if not isinstance(sub, str) or not sub or method not in _AUTH_METHODS:
        return None
    try:
        return SessionUser(
            sub=sub,
            email=_optional_text(data.get("email")),
            name=_optional_text(data.get("name")),
            role=Role(data["role"]),
            auth_method=cast("AuthMethod", method),
        )
    except (KeyError, ValueError, TypeError):
        return None


def csrf_token(session: Session) -> str:
    """Return the session CSRF token, minting one if none exists yet.

    Args:
        session (Session): The request session mapping.

    Returns:
        str: The token to embed in forms and the ``X-CSRF-Token`` header.
    """
    token = session.get(_CSRF_KEY)
    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        session[_CSRF_KEY] = token
    return token


def expected_csrf_token(session: Session) -> str | None:
    """Return the stored CSRF token without minting one.

    Args:
        session (Session): The request session mapping.

    Returns:
        str | None: The stored token, or ``None`` if the session has none.
    """
    token = session.get(_CSRF_KEY)
    return token if isinstance(token, str) and token else None
