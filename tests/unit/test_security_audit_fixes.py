"""Tests for the OWASP audit fixes applied in SECURITY-FINDINGS.md."""

from __future__ import annotations

import pytest

from llc_manager.core.config import Settings
from llc_manager.core.exceptions import ConfigurationError


class TestSecretKeyMinLength:
    """Validates A02-1 fix: secret_key minimum length enforced outside dev."""

    @pytest.mark.unit
    @pytest.mark.security
    def test_short_key_rejected_in_production(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", "production")
        with pytest.raises(ConfigurationError) as exc_info:
            Settings(secret_key="too-short")  # type: ignore[call-arg]
        assert exc_info.value.details["config_key"] == "secret_key"

    @pytest.mark.unit
    @pytest.mark.security
    def test_long_key_accepted_in_production(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", "production")
        # 64 chars - well above the 32-char minimum
        long_key = "a" * 64
        settings = Settings(secret_key=long_key)  # type: ignore[call-arg]
        assert settings.secret_key == long_key

    @pytest.mark.unit
    @pytest.mark.security
    def test_short_key_allowed_in_development(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", "development")
        settings = Settings(secret_key="short")  # type: ignore[call-arg]
        assert settings.secret_key == "short"

    @pytest.mark.unit
    @pytest.mark.security
    def test_default_placeholder_still_rejected_in_production(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The pre-existing placeholder validator still runs first, before the
        # length validator, so a short value equal to the placeholder is
        # rejected with the placeholder error path.
        monkeypatch.setenv("ENVIRONMENT", "production")
        with pytest.raises(ConfigurationError):
            Settings(secret_key="change-me-in-production")  # type: ignore[call-arg]


class TestAuthentikConfigPlaceholders:
    """Validates A01-1 scaffolding: Authentik settings exist and default to None."""

    @pytest.mark.unit
    def test_authentik_fields_default_none(self) -> None:
        settings = Settings()
        assert settings.authentik_issuer is None
        assert settings.authentik_jwks_url is None
        assert settings.authentik_audience is None

    @pytest.mark.unit
    def test_authentik_fields_loadable_from_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_AUTHENTIK_ISSUER", "https://auth.example.com")
        monkeypatch.setenv(
            "LLC_MANAGER_AUTHENTIK_JWKS_URL",
            "https://auth.example.com/jwks/",
        )
        monkeypatch.setenv("LLC_MANAGER_AUTHENTIK_AUDIENCE", "llc-manager-api")
        settings = Settings()
        assert settings.authentik_issuer == "https://auth.example.com"
        assert settings.authentik_jwks_url == "https://auth.example.com/jwks/"
        assert settings.authentik_audience == "llc-manager-api"


class TestCacheControlOnApiResponses:
    """Validates A05-2 fix: Cache-Control: no-store on /api/v1/* responses."""

    @pytest.mark.unit
    @pytest.mark.security
    def test_health_endpoint_is_not_no_store(self) -> None:
        # Health probes are intentionally cacheable for short windows; the
        # no-store header is scoped to /api/v1/* (data endpoints) only.
        from fastapi.testclient import TestClient

        from llc_manager.main import create_app

        client = TestClient(create_app())
        response = client.get("/api/health/live")
        assert response.headers.get("Cache-Control") != "no-store"

    @pytest.mark.unit
    @pytest.mark.security
    def test_api_v1_path_gets_no_store(self) -> None:
        from fastapi.testclient import TestClient

        from llc_manager.main import create_app

        client = TestClient(create_app())
        # Hit a non-existent route under /api/v1/ — FastAPI's router 404s
        # before any DB dependency runs, but the middleware still wraps the
        # response so the privacy headers are observable without needing
        # the test to reach a working PostgreSQL.
        response = client.get("/api/v1/does-not-exist")
        assert response.headers.get("Cache-Control") == "no-store"
        assert response.headers.get("Pragma") == "no-cache"


class TestCorsHardening:
    """Validates A05-1 fix: CORS uses explicit method/header allowlists."""

    @pytest.mark.unit
    @pytest.mark.security
    def test_cors_does_not_advertise_wildcard_methods(self) -> None:
        # Verify the configured middleware does not echo a wildcard back on
        # preflight; we should see the explicit method list.
        from fastapi.testclient import TestClient

        from llc_manager.main import create_app

        client = TestClient(create_app())
        response = client.options(
            "/api/v1/entities",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
        )
        allow_methods = response.headers.get("access-control-allow-methods", "")
        assert "*" not in allow_methods
        assert "GET" in allow_methods
        assert "POST" in allow_methods
        assert "DELETE" in allow_methods
