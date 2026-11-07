"""Tests for how the auth package is wired into the app."""

from collections.abc import Iterator
from typing import TYPE_CHECKING, cast

import pytest
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from llc_manager.auth.session import SESSION_COOKIE
from llc_manager.core.config import settings
from llc_manager.main import create_app

if TYPE_CHECKING:
    from fastapi import FastAPI

pytestmark = [pytest.mark.unit, pytest.mark.security]


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), follow_redirects=False) as test_client:
        yield test_client


def test_unconfigured_app_has_no_oidc_client(client: TestClient) -> None:
    assert cast("FastAPI", client.app).state.oidc_client is None


def test_unconfigured_login_is_a_clear_503_not_a_crash(client: TestClient) -> None:
    response = client.get("/auth/login")

    assert response.status_code == 503
    assert "not configured" in response.text


def test_unconfigured_callback_is_a_clear_503_not_a_crash(client: TestClient) -> None:
    response = client.get("/auth/callback", params={"code": "c", "state": "s"})

    assert response.status_code == 503


def test_web_routes_are_gated(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 303
    assert response.headers["location"] == "/auth/login?next=%2F"


def test_no_cookie_is_set_for_anonymous_requests(client: TestClient) -> None:
    response = client.get("/auth/login")

    assert SESSION_COOKIE not in response.headers.get("set-cookie", "")


def test_auth_routes_are_hidden_from_the_openapi_schema(client: TestClient) -> None:
    paths = client.get("/api/openapi.json").json()["paths"]

    assert not [path for path in paths if path.startswith("/auth")]


def test_dev_mode_login_goes_straight_to_next(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_dev_mode", True)
    with TestClient(create_app(), follow_redirects=False) as dev_client:
        response = dev_client.get("/auth/login?next=/entities/5")

    assert response.status_code == 303
    assert response.headers["location"] == "/entities/5"


def test_dev_mode_logs_a_startup_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(settings, "auth_dev_mode", True)

    with TestClient(create_app()):
        pass

    assert "auth_dev_mode_enabled" in caplog.text


def test_no_dev_mode_warning_when_dev_mode_is_off(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(settings, "auth_dev_mode", False)

    with TestClient(create_app()):
        pass

    assert "auth_dev_mode_enabled" not in caplog.text


def _session_https_only() -> object:
    app = create_app()
    for middleware in app.user_middleware:
        if middleware.cls is SessionMiddleware:
            return middleware.kwargs["https_only"]
    pytest.fail("SessionMiddleware is not installed")


@pytest.mark.parametrize(
    ("base_url", "environment", "expected"),
    [
        (None, None, True),
        (None, "production", True),
        ("http://llc.example.test", None, True),
        ("https://llc.example.test", None, True),
        ("https://llc.example.test", "development", True),
        (None, "development", False),
        (None, "local", False),
        (None, "test", False),
        ("http://localhost:8000", "development", False),
    ],
)
def test_session_cookie_is_secure_unless_explicitly_development(
    monkeypatch: pytest.MonkeyPatch,
    base_url: str | None,
    environment: str | None,
    expected: bool,
) -> None:
    monkeypatch.setattr(settings, "public_base_url", base_url)
    monkeypatch.setattr(settings, "environment", environment)

    assert _session_https_only() is expected
