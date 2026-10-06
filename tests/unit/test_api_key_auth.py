"""X-API-Key authentication on every /api/v1 route."""

from __future__ import annotations

import hmac
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from llc_manager.core import auth
from llc_manager.core.auth import keys_match
from llc_manager.core.config import Settings, settings
from llc_manager.core.exceptions import ConfigurationError
from llc_manager.main import create_app
from tests.auth_helpers import TEST_API_KEY

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = [pytest.mark.unit, pytest.mark.security]

V1_PATHS = ["/api/v1/entities", "/api/v1/documents"]


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _v1_route_paths() -> list[str]:
    paths = create_app().openapi()["paths"]
    return [p for p in paths if p.startswith("/api/v1")]


@pytest.mark.parametrize("path", V1_PATHS)
def test_missing_key_returns_401(client: TestClient, path: str) -> None:
    resp = client.get(path)
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid or missing API key"
    assert resp.headers["www-authenticate"] == "ApiKey"


@pytest.mark.parametrize("path", V1_PATHS)
def test_wrong_key_returns_401(client: TestClient, path: str) -> None:
    resp = client.get(path, headers={"X-API-Key": TEST_API_KEY + "x"})
    assert resp.status_code == 401


def test_non_ascii_key_is_rejected_not_crashed(client: TestClient) -> None:
    resp = client.get("/api/v1/documents", headers={"X-API-Key": b"caf\xc3\xa9"})
    assert resp.status_code == 401
    assert keys_match("caf\u00e9", TEST_API_KEY) is False


@pytest.mark.parametrize("value", [None, ""])
def test_unset_key_refuses_everything(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    monkeypatch.setattr(
        settings, "api_key", None if value is None else SecretStr(value)
    )
    resp = client.get("/api/v1/entities", headers={"X-API-Key": ""})
    assert resp.status_code == 503
    assert resp.json()["detail"] == "API authentication is not configured"


def test_every_v1_route_declares_the_key() -> None:
    schema = create_app().openapi()
    routes = _v1_route_paths()
    assert routes, "no /api/v1 routes found"
    for path in routes:
        for operation in schema["paths"][path].values():
            assert {"APIKeyHeader": []} in operation.get("security", []), path


def test_health_stays_open(client: TestClient) -> None:
    assert client.get("/api/health/live").status_code == 200


def test_compare_uses_hmac_compare_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[bytes, bytes]] = []
    real = hmac.compare_digest

    def spy(a: bytes, b: bytes) -> bool:
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(auth.hmac, "compare_digest", spy)
    assert keys_match("abc", "abc") is True
    assert keys_match("abc", "abd") is False
    assert calls == [(b"abc", b"abc"), (b"abc", b"abd")]


def test_request_path_uses_constant_time_compare(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []

    def spy(supplied: str, expected: str) -> bool:
        seen.append(supplied)
        return hmac.compare_digest(supplied.encode(), expected.encode())

    monkeypatch.setattr(auth, "keys_match", spy)
    client.get("/api/v1/documents", headers={"X-API-Key": "nope"})
    assert seen == ["nope"]


class TestApiKeyLength:
    def test_short_key_rejected_in_production(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_ENVIRONMENT", "production")
        monkeypatch.setenv("LLC_MANAGER_SECRET_KEY", "s" * 40)
        monkeypatch.setenv("LLC_MANAGER_API_KEY", "short")
        with pytest.raises(ConfigurationError, match="LLC_MANAGER_API_KEY"):
            Settings()

    def test_long_key_accepted_in_production(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_ENVIRONMENT", "production")
        monkeypatch.setenv("LLC_MANAGER_SECRET_KEY", "s" * 40)
        monkeypatch.setenv("LLC_MANAGER_API_KEY", "k" * 40)
        assert Settings().api_key is not None

    def test_short_key_allowed_in_test(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLC_MANAGER_ENVIRONMENT", "test")
        monkeypatch.setenv("LLC_MANAGER_API_KEY", "short")
        assert Settings().api_key is not None

    def test_unset_key_is_allowed_at_startup(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("LLC_MANAGER_API_KEY", raising=False)
        assert Settings(_env_file=None).api_key is None

    def test_empty_key_is_treated_as_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_ENVIRONMENT", "production")
        monkeypatch.setenv("LLC_MANAGER_SECRET_KEY", "s" * 40)
        monkeypatch.setenv("LLC_MANAGER_API_KEY", "")
        assert Settings(_env_file=None).api_key is None

    def test_service_api_key_name_is_accepted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("LLC_MANAGER_API_KEY", raising=False)
        monkeypatch.setenv("LLC_MANAGER_SERVICE_API_KEY", "svc-key")
        key = Settings(_env_file=None).api_key
        assert key is not None
        assert key.get_secret_value() == "svc-key"

    def test_primary_name_wins_over_service_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_API_KEY", "primary")
        monkeypatch.setenv("LLC_MANAGER_SERVICE_API_KEY", "service")
        key = Settings(_env_file=None).api_key
        assert key is not None
        assert key.get_secret_value() == "primary"
