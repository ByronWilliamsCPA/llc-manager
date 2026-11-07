"""Tests for the session user and CSRF token helpers."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from llc_manager.auth.roles import Role
from llc_manager.auth.session import (
    SessionUser,
    csrf_token,
    expected_csrf_token,
    load_user,
    store_user,
)
from llc_manager.core.config import settings

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


LOCAL_USER = SessionUser(
    sub="local-admin",
    email=None,
    name="Local administrator",
    role=Role.ADMIN,
    auth_method="local",
)
HASH_A = "$argon2id$v=19$m=8,t=1,p=1$c2FsdHNhbHQ$aGFzaGhhc2hoYXNo"  # pragma: allowlist secret
HASH_B = (
    "$argon2id$v=19$m=8,t=1,p=1$c2FsdHNhbHQ$b3RoZXJvdGhlcg"  # pragma: allowlist secret
)


@pytest.fixture
def break_glass_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enable the break-glass login with ``HASH_A`` configured."""
    monkeypatch.setattr(settings, "local_admin_enabled", True)
    monkeypatch.setattr(settings, "local_admin_password_hash", SecretStr(HASH_A))


@pytest.mark.usefixtures("break_glass_on")
class TestLocalSessionBinding:
    """A break-glass session lives only while its configuration does."""

    def test_unchanged_settings_keep_the_session_valid(self) -> None:
        session: dict[str, object] = {}
        store_user(session, LOCAL_USER, max_age=100, now=1000.0)

        assert load_user(session, now=1050.0) == LOCAL_USER

    def test_the_hash_itself_is_not_stored_in_the_cookie(self) -> None:
        session: dict[str, object] = {}
        store_user(session, LOCAL_USER, max_age=100, now=1000.0)

        assert HASH_A not in repr(session)

    def test_disabling_break_glass_signs_the_session_out(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session: dict[str, object] = {}
        store_user(session, LOCAL_USER, max_age=100, now=1000.0)

        monkeypatch.setattr(settings, "local_admin_enabled", False)

        assert load_user(session, now=1050.0) is None

    def test_removing_the_hash_signs_the_session_out(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session: dict[str, object] = {}
        store_user(session, LOCAL_USER, max_age=100, now=1000.0)

        monkeypatch.setattr(settings, "local_admin_password_hash", None)

        assert load_user(session, now=1050.0) is None

    def test_rotating_the_hash_signs_the_session_out(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session: dict[str, object] = {}
        store_user(session, LOCAL_USER, max_age=100, now=1000.0)

        monkeypatch.setattr(settings, "local_admin_password_hash", SecretStr(HASH_B))

        assert load_user(session, now=1050.0) is None

    def test_a_local_session_without_a_fingerprint_is_rejected(self) -> None:
        session: dict[str, object] = {}
        store_user(session, LOCAL_USER, max_age=100, now=1000.0)
        user = session["user"]
        assert isinstance(user, dict)
        user.pop("fp", None)

        assert load_user(session, now=1050.0) is None

    @pytest.mark.parametrize("fingerprint", ["caf\u00e9", "\u2603" * 64, "", 7, None])
    def test_a_malformed_fingerprint_signs_the_session_out(
        self, fingerprint: object
    ) -> None:
        session: dict[str, object] = {}
        store_user(session, LOCAL_USER, max_age=100, now=1000.0)
        user = session["user"]
        assert isinstance(user, dict)
        user["fp"] = fingerprint

        assert load_user(session, now=1050.0) is None

    def test_rotating_the_secret_key_signs_the_session_out(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session: dict[str, object] = {}
        store_user(session, LOCAL_USER, max_age=100, now=1000.0)

        monkeypatch.setattr(settings, "secret_key", "r" * 40)

        assert load_user(session, now=1050.0) is None

    def test_oidc_sessions_ignore_the_break_glass_settings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session: dict[str, object] = {}
        store_user(session, USER, max_age=100, now=1000.0)

        monkeypatch.setattr(settings, "local_admin_enabled", False)
        monkeypatch.setattr(settings, "local_admin_password_hash", None)

        assert load_user(session, now=1050.0) == USER
