"""Tests for the OWASP audit fixes applied in SECURITY-FINDINGS.md."""

from __future__ import annotations

from pathlib import Path

import pytest

from llc_manager.core.config import Settings
from llc_manager.core.exceptions import ConfigurationError
from tests.auth_helpers import configure_production_sign_in


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
        configure_production_sign_in(monkeypatch)
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


def _unset_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every environment name so the process names no environment."""
    monkeypatch.delenv("LLC_MANAGER_ENVIRONMENT", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("LLC_MANAGER_SECRET_KEY", raising=False)
    monkeypatch.delenv("LLC_MANAGER_API_KEY", raising=False)
    monkeypatch.delenv("LLC_MANAGER_SERVICE_API_KEY", raising=False)


class TestUnsetEnvironmentIsProduction:
    """An unset environment name must be treated as production by every check."""

    @pytest.mark.unit
    @pytest.mark.security
    def test_unset_environment_rejects_default_secret_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _unset_environment(monkeypatch)
        configure_production_sign_in(monkeypatch)
        with pytest.raises(ConfigurationError) as exc_info:
            Settings(_env_file=None)
        assert exc_info.value.details["config_key"] == "secret_key"

    @pytest.mark.unit
    @pytest.mark.security
    def test_unset_environment_rejects_short_secret_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _unset_environment(monkeypatch)
        configure_production_sign_in(monkeypatch)
        monkeypatch.setenv("LLC_MANAGER_SECRET_KEY", "too-short")
        with pytest.raises(ConfigurationError) as exc_info:
            Settings(_env_file=None)
        assert exc_info.value.details["config_key"] == "secret_key"

    @pytest.mark.unit
    @pytest.mark.security
    def test_unset_environment_rejects_short_api_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _unset_environment(monkeypatch)
        configure_production_sign_in(monkeypatch)
        monkeypatch.setenv("LLC_MANAGER_SECRET_KEY", "s" * 40)
        monkeypatch.setenv("LLC_MANAGER_API_KEY", "short")
        with pytest.raises(ConfigurationError) as exc_info:
            Settings(_env_file=None)
        assert exc_info.value.details["config_key"] == "api_key"

    @pytest.mark.unit
    @pytest.mark.security
    def test_unset_environment_with_good_keys_passes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _unset_environment(monkeypatch)
        configure_production_sign_in(monkeypatch)
        monkeypatch.setenv("LLC_MANAGER_SECRET_KEY", "s" * 40)
        monkeypatch.setenv("LLC_MANAGER_API_KEY", "k" * 40)
        settings = Settings(_env_file=None)
        assert settings.secret_key == "s" * 40

    @pytest.mark.unit
    @pytest.mark.security
    def test_dotenv_production_rejects_default_secret_key(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _unset_environment(monkeypatch)
        configure_production_sign_in(monkeypatch)
        env_file = tmp_path / ".env"
        env_file.write_text("ENVIRONMENT=production\n")
        with pytest.raises(ConfigurationError) as exc_info:
            Settings(_env_file=str(env_file))
        assert exc_info.value.details["config_key"] == "secret_key"

    @pytest.mark.unit
    @pytest.mark.security
    def test_dotenv_development_allows_default_secret_key(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _unset_environment(monkeypatch)
        env_file = tmp_path / ".env"
        env_file.write_text("ENVIRONMENT=development\n")
        settings = Settings(_env_file=str(env_file))
        assert settings.secret_key.startswith("change-")


class TestPlaceholderSecretKeys:
    """Shipped example values and any ``change-`` prefix are never real keys."""

    @pytest.mark.unit
    @pytest.mark.security
    @pytest.mark.parametrize(
        "value",
        [
            "change-this-in-production-use-a-long-random-string",
            "change-me-please-" + "x" * 30,
            "CHANGE-anything-" + "x" * 30,
            "Change-Me-" + "x" * 30,
        ],
    )
    def test_placeholder_rejected_in_production(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", "production")
        configure_production_sign_in(monkeypatch)
        monkeypatch.setenv("LLC_MANAGER_SECRET_KEY", value)
        assert len(value) >= 32
        with pytest.raises(ConfigurationError) as exc_info:
            Settings(_env_file=None)
        assert exc_info.value.details["config_key"] == "secret_key"

    @pytest.mark.unit
    @pytest.mark.security
    def test_placeholder_allowed_in_development(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", "development")
        value = "change-this-in-production-use-a-long-random-string"
        monkeypatch.setenv("LLC_MANAGER_SECRET_KEY", value)
        settings = Settings(_env_file=None)
        assert settings.secret_key == value

    @pytest.mark.unit
    @pytest.mark.security
    def test_blank_key_in_development_falls_back_to_the_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # ``.env.example`` ships ``LLC_MANAGER_SECRET_KEY=`` with no value, so a
        # copied file must behave like no key at all, never an empty signing key.
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("LLC_MANAGER_SECRET_KEY", "")
        settings = Settings(_env_file=None)
        assert settings.secret_key.startswith("change-")

    @pytest.mark.unit
    @pytest.mark.security
    def test_blank_key_rejected_in_production(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", "production")
        configure_production_sign_in(monkeypatch)
        monkeypatch.setenv("LLC_MANAGER_SECRET_KEY", "  ")
        with pytest.raises(ConfigurationError) as exc_info:
            Settings(_env_file=None)
        assert exc_info.value.details["config_key"] == "secret_key"

    @pytest.mark.unit
    @pytest.mark.security
    def test_random_key_with_change_inside_is_accepted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", "production")
        configure_production_sign_in(monkeypatch)
        value = "a1b2-change-" + "f" * 30
        monkeypatch.setenv("LLC_MANAGER_SECRET_KEY", value)
        settings = Settings(_env_file=None)
        assert settings.secret_key == value


class TestAuthentikConfigPlaceholders:
    """Validates A01-1 scaffolding: Authentik settings exist and default to None."""

    @pytest.mark.unit
    def test_authentik_fields_default_none(self) -> None:
        settings = Settings()
        assert settings.authentik_issuer is None
        assert settings.authentik_client_id is None
        assert settings.authentik_client_secret is None
        assert not hasattr(settings, "authentik_jwks_url")
        assert not hasattr(settings, "authentik_audience")

    @pytest.mark.unit
    def test_authentik_fields_loadable_from_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_PUBLIC_BASE_URL", "https://llc.example.com")
        monkeypatch.setenv("LLC_MANAGER_AUTHENTIK_ISSUER", "https://auth.example.com")
        monkeypatch.setenv("LLC_MANAGER_AUTHENTIK_CLIENT_ID", "llc-manager")
        monkeypatch.setenv("LLC_MANAGER_AUTHENTIK_CLIENT_SECRET", "not-a-real-secret")
        settings = Settings()
        assert settings.authentik_issuer == "https://auth.example.com"
        assert settings.authentik_client_id == "llc-manager"
        assert settings.authentik_client_secret is not None
        assert settings.authentik_client_secret.get_secret_value() == (
            "not-a-real-secret"
        )


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
        # Hit a non-existent route under /api/v1/ -- FastAPI's router 404s
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
