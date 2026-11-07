"""Tests for trusted-proxy handling of X-Forwarded-For and X-Forwarded-Proto."""

import pytest
from argon2 import PasswordHasher
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import SecretStr
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from llc_manager.core.config import settings
from llc_manager.main import create_app

pytestmark = [pytest.mark.unit, pytest.mark.security]

FORWARDED = {"X-Forwarded-For": "203.0.113.9", "X-Forwarded-Proto": "https"}


def _app_with_probe(monkeypatch: pytest.MonkeyPatch, trusted: list[str]) -> FastAPI:
    monkeypatch.setattr(settings, "trusted_proxy_ips", trusted)
    # The test client speaks plain http. Outside an explicit development
    # environment the session cookie is Secure and the client would drop it.
    monkeypatch.setattr(settings, "environment", "development")
    app = create_app()

    @app.get("/_whoami")
    async def whoami(request: Request) -> dict[str, str]:
        client = request.client.host if request.client else "none"
        return {"client": client, "scheme": request.url.scheme}

    return app


def _whoami(app: FastAPI, peer: str, headers: dict[str, str]) -> dict[str, str]:
    with TestClient(app, client=(peer, 5000)) as client:
        return client.get("/_whoami", headers=headers).json()


def test_forwarded_headers_are_honoured_from_a_trusted_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app_with_probe(monkeypatch, ["10.0.0.5"])

    assert _whoami(app, "10.0.0.5", FORWARDED) == {
        "client": "203.0.113.9",
        "scheme": "https",
    }


def test_cidr_ranges_are_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _app_with_probe(monkeypatch, ["172.18.0.0/16"])

    assert _whoami(app, "172.18.4.2", FORWARDED)["client"] == "203.0.113.9"


def test_forwarded_headers_are_ignored_from_an_untrusted_peer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app_with_probe(monkeypatch, ["10.0.0.5"])

    # A direct client cannot pick its own IP, which would defeat the throttle.
    assert _whoami(app, "198.51.100.7", FORWARDED) == {
        "client": "198.51.100.7",
        "scheme": "http",
    }


def test_nothing_is_trusted_when_the_list_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app_with_probe(monkeypatch, [])

    assert _whoami(app, "10.0.0.5", FORWARDED)["client"] == "10.0.0.5"


def test_no_middleware_is_added_when_the_list_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unconfigured host must keep exactly the middleware stack it had."""
    monkeypatch.setattr(settings, "trusted_proxy_ips", [])

    app = create_app()

    assert ProxyHeadersMiddleware not in [m.cls for m in app.user_middleware]


def test_the_middleware_is_outermost_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "trusted_proxy_ips", ["10.0.0.5"])

    app = create_app()

    assert app.user_middleware[0].cls is ProxyHeadersMiddleware


def test_spoofed_leftmost_entry_does_not_win(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _app_with_probe(monkeypatch, ["10.0.0.5"])
    headers = {"X-Forwarded-For": "1.1.1.1, 203.0.113.9", "X-Forwarded-Proto": "https"}

    # The proxy appended the real client; the caller-supplied prefix is not trusted.
    assert _whoami(app, "10.0.0.5", headers)["client"] == "203.0.113.9"


def test_break_glass_throttle_keys_on_the_forwarded_client_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    password_hash = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash("pw")
    monkeypatch.setattr(settings, "local_admin_enabled", True)
    monkeypatch.setattr(settings, "local_admin_password_hash", SecretStr(password_hash))
    app = _app_with_probe(monkeypatch, ["10.0.0.5"])

    def session_for(forwarded_for: str) -> tuple[TestClient, str]:
        client = TestClient(
            app,
            client=("10.0.0.5", 1),
            follow_redirects=False,
            headers={"X-Forwarded-For": forwarded_for},
        )
        page = client.get("/auth/local-login").text
        marker = 'name="csrf_token" value="'
        start = page.index(marker) + len(marker)
        return client, page[start : page.index('"', start)]

    def attempt(session: tuple[TestClient, str], password: str) -> int:
        client, token = session
        data = {"password": password, "csrf_token": token}
        return client.post("/auth/local-login", data=data).status_code

    first = session_for("203.0.113.9")
    for _ in range(5):
        assert attempt(first, "wrong") == 401
    assert attempt(first, "pw") == 429
    # A different user behind the same proxy is unaffected.
    assert attempt(session_for("203.0.113.10"), "pw") == 303


def test_break_glass_ignores_a_spoofed_header_from_an_untrusted_peer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rotating X-Forwarded-For must not buy a fresh throttle budget."""
    password_hash = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash("pw")
    monkeypatch.setattr(settings, "local_admin_enabled", True)
    monkeypatch.setattr(settings, "local_admin_password_hash", SecretStr(password_hash))
    app = _app_with_probe(monkeypatch, ["10.0.0.5"])
    client = TestClient(app, client=("198.51.100.7", 1), follow_redirects=False)
    page = client.get("/auth/local-login").text
    marker = 'name="csrf_token" value="'
    start = page.index(marker) + len(marker)
    token = page[start : page.index('"', start)]

    statuses = [
        client.post(
            "/auth/local-login",
            data={"password": "wrong", "csrf_token": token},  # pragma: allowlist secret
            headers={"X-Forwarded-For": f"203.0.113.{index}"},
        ).status_code
        for index in range(6)
    ]

    assert statuses == [401, 401, 401, 401, 401, 429]
