"""Tests for the session user and CSRF token helpers."""

from __future__ import annotations

import pytest

from llc_manager.auth.roles import Role
from llc_manager.auth.session import (
    SessionUser,
    csrf_token,
    expected_csrf_token,
    load_user,
    store_user,
)

pytestmark = [pytest.mark.unit, pytest.mark.security]

USER = SessionUser(
    sub="u1",
    email="u1@example.test",
    name="U One",
    role=Role.VIEWER,
    auth_method="oidc",
)


def test_round_trip_and_flags() -> None:
    """A stored user loads back, and pre-login state is dropped."""
    session: dict[str, object] = {"stale": "pre-login state"}
    store_user(session, USER, max_age=100, now=1000.0)

    assert "stale" not in session
    assert load_user(session, now=1050.0) == USER
    assert USER.is_admin is False
    assert expected_csrf_token(session)


def test_absolute_expiry_is_enforced() -> None:
    """The payload's own expiry ends the session regardless of the cookie."""
    session: dict[str, object] = {}
    store_user(session, USER, max_age=100, now=1000.0)

    assert load_user(session, now=1099.9) is not None
    assert load_user(session, now=1100.0) is None
    assert load_user(session, now=5000.0) is None


def test_new_login_mints_a_new_csrf_token() -> None:
    """Every sign-in gets its own CSRF token."""
    first: dict[str, object] = {}
    second: dict[str, object] = {}
    store_user(first, USER, max_age=100)
    store_user(second, USER, max_age=100)

    assert expected_csrf_token(first) != expected_csrf_token(second)


def test_malformed_session_is_treated_as_signed_out() -> None:
    """Anything that is not a well-formed, unexpired user means signed out."""
    assert load_user({}) is None
    assert load_user({"user": "admin"}) is None
    assert load_user({"user": {"sub": "x"}}) is None
    assert load_user({"user": {"sub": "x", "role": "root", "exp": 9e12}}) is None
    assert load_user({"user": {"sub": "x", "role": "admin", "exp": "never"}}) is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"auth_method": "root"},
        {"auth_method": None},
        {"email": 5},
        {"name": ["x"]},
        {"sub": None},
        {"sub": ""},
    ],
)
def test_unexpected_field_types_are_treated_as_signed_out(
    overrides: dict[str, object],
) -> None:
    """A user record with a wrong-typed field is rejected, not coerced."""
    record: dict[str, object] = {
        "sub": "x",
        "email": None,
        "name": None,
        "role": "admin",
        "auth_method": "oidc",
        "exp": 9e12,
    }
    record.update(overrides)

    assert load_user({"user": record}) is None


def test_csrf_token_is_minted_once_and_stable() -> None:
    """``csrf_token`` mints lazily and then returns the same value."""
    session: dict[str, object] = {}
    assert expected_csrf_token(session) is None

    token = csrf_token(session)

    assert token
    assert csrf_token(session) == token
    assert expected_csrf_token(session) == token
