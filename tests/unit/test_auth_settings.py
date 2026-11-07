"""Settings and validators for browser login (Authentik OIDC, break-glass)."""

from __future__ import annotations

from pathlib import Path

import pytest
from argon2 import PasswordHasher
from pydantic import SecretStr

from llc_manager.core.config import Settings
from llc_manager.core.exceptions import ConfigurationError

pytestmark = [pytest.mark.unit, pytest.mark.security]

AUTH_ENV_NAMES = (
    "PUBLIC_BASE_URL",
    "AUTHENTIK_ISSUER",
    "AUTHENTIK_CLIENT_ID",
    "AUTHENTIK_CLIENT_SECRET",
    "AUTHENTIK_GROUPS_CLAIM",
    "AUTHENTIK_JWKS_URL",
    "AUTHENTIK_AUDIENCE",
    "ADMIN_GROUP",
    "VIEWER_GROUP",
    "SESSION_MAX_AGE_SECONDS",
    "LOCAL_ADMIN_ENABLED",
    "LOCAL_ADMIN_PASSWORD_HASH",
    "TRUSTED_PROXY_IPS",
    "AUTH_DEV_MODE",
)

ARGON2_HASH = PasswordHasher().hash("correct horse battery staple")


@pytest.fixture(autouse=True)
def clean_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test with no auth settings in the process environment."""
    for name in AUTH_ENV_NAMES:
        monkeypatch.delenv(f"LLC_MANAGER_{name}", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("LLC_MANAGER_ENVIRONMENT", raising=False)


@pytest.fixture
def production(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the process look like a production deployment."""
    monkeypatch.setenv("LLC_MANAGER_ENVIRONMENT", "production")
    monkeypatch.setenv("LLC_MANAGER_SECRET_KEY", "s" * 40)


def _oidc_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLC_MANAGER_PUBLIC_BASE_URL", "https://llc.example.com")
    monkeypatch.setenv(
        "LLC_MANAGER_AUTHENTIK_ISSUER",
        "https://auth.example.com/application/o/llc-manager/",
    )
    monkeypatch.setenv("LLC_MANAGER_AUTHENTIK_CLIENT_ID", "llc-manager")
    monkeypatch.setenv("LLC_MANAGER_AUTHENTIK_CLIENT_SECRET", "client-secret-value")


class TestDefaults:
    def test_defaults(self) -> None:
        s = Settings(_env_file=None)
        assert s.public_base_url is None
        assert s.authentik_issuer is None
        assert s.authentik_client_id is None
        assert s.authentik_client_secret is None
        assert s.authentik_groups_claim == "groups"
        assert s.admin_group == "llc-manager-admins"
        assert s.viewer_group == "llc-manager-viewers"
        assert s.session_max_age_seconds == 28800
        assert s.local_admin_enabled is False
        assert s.local_admin_password_hash is None
        assert s.trusted_proxy_ips == []
        assert s.auth_dev_mode is False
        assert s.oidc_configured is False

    def test_removed_bearer_jwt_settings_are_gone(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_AUTHENTIK_JWKS_URL", "https://x/jwks/")
        monkeypatch.setenv("LLC_MANAGER_AUTHENTIK_AUDIENCE", "llc-manager-api")
        s = Settings(_env_file=None)
        assert not hasattr(s, "authentik_jwks_url")
        assert not hasattr(s, "authentik_audience")

    @pytest.mark.parametrize(
        "name", ["AUTHENTIK_GROUPS_CLAIM", "ADMIN_GROUP", "VIEWER_GROUP"]
    )
    def test_blank_group_settings_are_rejected(
        self, monkeypatch: pytest.MonkeyPatch, name: str
    ) -> None:
        # An empty group name must never silently match a user's group list.
        monkeypatch.setenv(f"LLC_MANAGER_{name}", "")
        with pytest.raises(ValueError, match="String should have at least 1"):
            Settings(_env_file=None)

    def test_session_max_age_must_be_positive(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_SESSION_MAX_AGE_SECONDS", "0")
        with pytest.raises(ValueError, match="session_max_age_seconds"):
            Settings(_env_file=None)


class TestUnconfiguredProductionIsUnchanged:
    """PR 1 to 3 must not change startup for a production host with no auth set."""

    def test_production_without_any_auth_setting_starts(self, production: None) -> None:
        s = Settings(_env_file=None)
        assert s.oidc_configured is False
        assert s.local_admin_enabled is False
        assert s.auth_dev_mode is False

    def test_unset_environment_without_any_auth_setting_starts(self) -> None:
        s = Settings(_env_file=None)
        assert s.oidc_configured is False
        assert s.auth_dev_mode is False
        assert s.explicit_development_environment is False

    def test_legacy_issuer_alone_still_starts_in_production(
        self, monkeypatch: pytest.MonkeyPatch, production: None
    ) -> None:
        # authentik_issuer was a standalone setting before ADR-003; a host that
        # sets only it (even over http) must keep starting until PR 4.
        monkeypatch.setenv(
            "LLC_MANAGER_AUTHENTIK_ISSUER", "http://auth.example.com/application/o/x/"
        )
        s = Settings(_env_file=None)
        assert s.oidc_configured is False

    def test_removed_bearer_jwt_env_vars_do_not_break_production(
        self, monkeypatch: pytest.MonkeyPatch, production: None
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_AUTHENTIK_JWKS_URL", "https://x/jwks/")
        monkeypatch.setenv("LLC_MANAGER_AUTHENTIK_AUDIENCE", "llc-manager-api")
        assert Settings(_env_file=None).oidc_configured is False


class TestOidcConsistency:
    def test_complete_oidc_settings_are_accepted(
        self, monkeypatch: pytest.MonkeyPatch, production: None
    ) -> None:
        _oidc_env(monkeypatch)
        s = Settings(_env_file=None)
        assert s.oidc_configured is True
        assert isinstance(s.authentik_client_secret, SecretStr)
        assert s.authentik_client_secret.get_secret_value() == "client-secret-value"

    @pytest.mark.parametrize(
        "missing",
        [
            "PUBLIC_BASE_URL",
            "AUTHENTIK_ISSUER",
            "AUTHENTIK_CLIENT_ID",
            "AUTHENTIK_CLIENT_SECRET",
        ],
    )
    def test_partial_oidc_settings_are_rejected(
        self, monkeypatch: pytest.MonkeyPatch, missing: str
    ) -> None:
        _oidc_env(monkeypatch)
        monkeypatch.delenv(f"LLC_MANAGER_{missing}")
        with pytest.raises(ConfigurationError, match="must all be set together"):
            Settings(_env_file=None)

    def test_blank_values_count_as_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLC_MANAGER_AUTHENTIK_ISSUER", "")
        monkeypatch.setenv("LLC_MANAGER_AUTHENTIK_CLIENT_SECRET", "  ")
        monkeypatch.setenv("LLC_MANAGER_PUBLIC_BASE_URL", "")
        s = Settings(_env_file=None)
        assert s.authentik_issuer is None
        assert s.authentik_client_secret is None
        assert s.public_base_url is None

    def test_http_issuer_is_rejected_in_production(
        self, monkeypatch: pytest.MonkeyPatch, production: None
    ) -> None:
        _oidc_env(monkeypatch)
        monkeypatch.setenv(
            "LLC_MANAGER_AUTHENTIK_ISSUER", "http://auth.example.com/application/o/x/"
        )
        with pytest.raises(ConfigurationError, match="AUTHENTIK_ISSUER"):
            Settings(_env_file=None)

    def test_http_issuer_is_allowed_in_development(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_ENVIRONMENT", "development")
        _oidc_env(monkeypatch)
        monkeypatch.setenv("LLC_MANAGER_PUBLIC_BASE_URL", "http://localhost:8000")
        monkeypatch.setenv(
            "LLC_MANAGER_AUTHENTIK_ISSUER", "http://localhost:9000/application/o/x/"
        )
        assert Settings(_env_file=None).oidc_configured is True


class TestPublicBaseUrl:
    def test_trailing_slash_is_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLC_MANAGER_PUBLIC_BASE_URL", "https://llc.example.com/")
        assert Settings(_env_file=None).public_base_url == "https://llc.example.com"

    @pytest.mark.parametrize(
        "value",
        [
            "llc.example.com",
            "ftp://llc.example.com",
            "https://llc.example.com/app",
            "https://llc.example.com/?x=1",
            "https://llc.example.com/#frag",
            "https://",
        ],
    )
    def test_non_origin_values_are_rejected(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_PUBLIC_BASE_URL", value)
        with pytest.raises(ConfigurationError, match="PUBLIC_BASE_URL"):
            Settings(_env_file=None)

    def test_http_is_rejected_in_production(
        self, monkeypatch: pytest.MonkeyPatch, production: None
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_PUBLIC_BASE_URL", "http://llc.example.com")
        with pytest.raises(ConfigurationError, match="https://"):
            Settings(_env_file=None)

    def test_http_is_allowed_in_development(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_ENVIRONMENT", "development")
        monkeypatch.setenv("LLC_MANAGER_PUBLIC_BASE_URL", "http://localhost:8000")
        assert Settings(_env_file=None).public_base_url == "http://localhost:8000"

    def test_http_is_rejected_when_the_environment_name_is_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_PUBLIC_BASE_URL", "http://localhost:8000")
        with pytest.raises(ConfigurationError, match="https://"):
            Settings(_env_file=None)

    def test_http_is_rejected_when_dotenv_says_production(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(
            "ENVIRONMENT=production\nLLC_MANAGER_PUBLIC_BASE_URL=http://llc.example.com\n"
        )
        with pytest.raises(ConfigurationError, match="https://"):
            Settings(_env_file=str(env_file))


class TestBreakGlassSettings:
    def test_enabled_without_hash_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_LOCAL_ADMIN_ENABLED", "true")
        with pytest.raises(ConfigurationError, match="LOCAL_ADMIN_PASSWORD_HASH"):
            Settings(_env_file=None)

    def test_enabled_with_argon2_hash_is_accepted(
        self, monkeypatch: pytest.MonkeyPatch, production: None
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_LOCAL_ADMIN_ENABLED", "true")
        monkeypatch.setenv("LLC_MANAGER_LOCAL_ADMIN_PASSWORD_HASH", ARGON2_HASH)
        s = Settings(_env_file=None)
        assert s.local_admin_enabled is True
        assert s.local_admin_password_hash is not None

    @pytest.mark.parametrize("value", ["hunter2", "$2b$12$abcdefghijklmnopqrstuv"])
    def test_non_argon2_value_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_LOCAL_ADMIN_PASSWORD_HASH", value)
        with pytest.raises(ConfigurationError, match="argon2"):
            Settings(_env_file=None)

    def test_hash_alone_does_not_enable_the_login(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_LOCAL_ADMIN_PASSWORD_HASH", ARGON2_HASH)
        assert Settings(_env_file=None).local_admin_enabled is False

    def test_hash_is_not_exposed_in_repr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLC_MANAGER_LOCAL_ADMIN_PASSWORD_HASH", ARGON2_HASH)
        assert ARGON2_HASH not in repr(Settings(_env_file=None))


class TestDevMode:
    def test_refused_in_production(
        self, monkeypatch: pytest.MonkeyPatch, production: None
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_AUTH_DEV_MODE", "true")
        with pytest.raises(ConfigurationError, match="AUTH_DEV_MODE"):
            Settings(_env_file=None)

    @pytest.mark.parametrize("environment", ["development", "local", "test"])
    def test_allowed_in_development_class_environments(
        self, monkeypatch: pytest.MonkeyPatch, environment: str
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_ENVIRONMENT", environment)
        monkeypatch.setenv("LLC_MANAGER_AUTH_DEV_MODE", "true")
        assert Settings(_env_file=None).auth_dev_mode is True

    @pytest.mark.parametrize("environment", ["development", "local", "test"])
    def test_unprefixed_environment_name_counts(
        self, monkeypatch: pytest.MonkeyPatch, environment: str
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", environment)
        monkeypatch.setenv("LLC_MANAGER_AUTH_DEV_MODE", "true")
        assert Settings(_env_file=None).auth_dev_mode is True

    def test_refused_when_the_environment_name_is_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_AUTH_DEV_MODE", "true")
        with pytest.raises(ConfigurationError, match="AUTH_DEV_MODE"):
            Settings(_env_file=None)

    def test_refused_when_the_environment_name_is_blank(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_ENVIRONMENT", " ")
        monkeypatch.setenv("LLC_MANAGER_SECRET_KEY", "s" * 40)
        monkeypatch.setenv("LLC_MANAGER_AUTH_DEV_MODE", "true")
        with pytest.raises(ConfigurationError, match="AUTH_DEV_MODE"):
            Settings(_env_file=None)

    def test_refused_when_dotenv_says_production(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("ENVIRONMENT=production\n")
        monkeypatch.setenv("LLC_MANAGER_AUTH_DEV_MODE", "true")
        with pytest.raises(ConfigurationError, match="AUTH_DEV_MODE"):
            Settings(_env_file=str(env_file))

    def test_dotenv_cannot_enable_dev_mode_without_naming_the_environment(
        self, tmp_path: Path
    ) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("LLC_MANAGER_AUTH_DEV_MODE=true\n")
        with pytest.raises(ConfigurationError, match="AUTH_DEV_MODE"):
            Settings(_env_file=str(env_file))

    def test_dotenv_naming_a_development_environment_allows_dev_mode(
        self, tmp_path: Path
    ) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(
            "\n".join(
                [
                    "LLC_MANAGER_ENVIRONMENT=development",
                    "LLC_MANAGER_AUTH_DEV_MODE=true",
                ]
            )
        )
        assert Settings(_env_file=str(env_file)).auth_dev_mode is True

    def test_process_environment_overrides_dotenv(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("ENVIRONMENT=development\n")
        monkeypatch.setenv("LLC_MANAGER_ENVIRONMENT", "production")
        monkeypatch.setenv("LLC_MANAGER_SECRET_KEY", "s" * 40)
        monkeypatch.setenv("LLC_MANAGER_AUTH_DEV_MODE", "true")
        with pytest.raises(ConfigurationError, match="AUTH_DEV_MODE"):
            Settings(_env_file=str(env_file))

    def test_prefixed_name_wins_over_unprefixed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_ENVIRONMENT", "production")
        monkeypatch.setenv("LLC_MANAGER_SECRET_KEY", "s" * 40)
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("LLC_MANAGER_AUTH_DEV_MODE", "true")
        with pytest.raises(ConfigurationError, match="AUTH_DEV_MODE"):
            Settings(_env_file=None)


class TestTrustedProxyIps:
    def test_comma_separated_list_is_parsed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_TRUSTED_PROXY_IPS", "10.0.0.5, 172.18.0.0/16")
        assert Settings(_env_file=None).trusted_proxy_ips == [
            "10.0.0.5",
            "172.18.0.0/16",
        ]

    def test_blank_value_is_an_empty_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_TRUSTED_PROXY_IPS", " ")
        assert Settings(_env_file=None).trusted_proxy_ips == []

    @pytest.mark.parametrize("value", ["*", "proxy.local", "10.0.0.5,not-an-ip"])
    def test_invalid_entries_are_rejected(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_TRUSTED_PROXY_IPS", value)
        with pytest.raises(ConfigurationError, match="TRUSTED_PROXY_IPS"):
            Settings(_env_file=None)

    @pytest.mark.parametrize(
        "value",
        [
            "10.0.0.5",
            "127.0.0.1",
            "::1",
            "10.0.0.0/8",
            "172.18.0.0/16",
            "192.168.1.0/24",
            "fd00::/16",
            "fd12:3456::/32",
            "10.0.0.5, 172.18.0.0/16, ::1",
        ],
    )
    def test_private_and_loopback_entries_are_accepted(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_TRUSTED_PROXY_IPS", value)
        assert Settings(_env_file=None).trusted_proxy_ips

    def test_host_bits_are_rejected_with_a_suggestion(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # uvicorn parses networks strictly, so a network with host bits set
        # would silently match nothing and every client would share one IP.
        monkeypatch.setenv("LLC_MANAGER_TRUSTED_PROXY_IPS", "172.18.0.5/16")
        with pytest.raises(ConfigurationError) as caught:
            Settings(_env_file=None)
        assert "TRUSTED_PROXY_IPS" in str(caught.value)
        assert "host bits" in str(caught.value)
        assert "172.18.0.0/16" in str(caught.value)

    @pytest.mark.parametrize(
        "value",
        [
            "0.0.0.0/0",
            "::/0",
            "8.8.8.8",
            "203.0.114.0/24",
            "100.64.0.0/10",
            "2001:4860::/32",
            "10.0.0.5,8.8.8.8",
        ],
    )
    def test_public_ranges_are_rejected(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_TRUSTED_PROXY_IPS", value)
        with pytest.raises(ConfigurationError, match="TRUSTED_PROXY_IPS"):
            Settings(_env_file=None)

    @pytest.mark.parametrize(
        "value", ["10.0.0.0/7", "172.0.0.0/8,0.0.0.0/4", "fc00::/7", "fd00::/15"]
    )
    def test_ranges_broader_than_the_limit_are_rejected(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv("LLC_MANAGER_TRUSTED_PROXY_IPS", value)
        with pytest.raises(ConfigurationError, match="TRUSTED_PROXY_IPS"):
            Settings(_env_file=None)
