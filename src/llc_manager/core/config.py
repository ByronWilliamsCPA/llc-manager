"""Configuration settings for LLC Manager.

Settings are loaded from environment variables with the prefix 'LLC_MANAGER_'.
Pydantic-settings handles the parsing and validation.
"""

import ipaddress
from pathlib import Path
from typing import Annotated, ClassVar, Literal
from urllib.parse import urlsplit

from pydantic import (
    AliasChoices,
    Field,
    PostgresDsn,
    SecretStr,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from llc_manager.core.exceptions import ConfigurationError

# Placeholder value shipped as the package default. Callers are expected to
# override via LLC_MANAGER_SECRET_KEY in any non-development deployment;
# see `Settings._reject_default_secret_key_outside_dev` for enforcement.
_DEFAULT_SECRET_KEY_PLACEHOLDER = "change-me-in-production"  # noqa: S105  # nosec B105 -- permanent false positive (reviewed PR #9); startup sentinel explicitly rejected by _reject_default_secret_key_outside_dev outside development

# Every shipped placeholder secret key starts with this prefix. Matched case
# insensitively; see ``_is_placeholder_secret_key``.
_PLACEHOLDER_KEY_PREFIX = "change-"

# Minimum acceptable SECRET_KEY length outside development. 32 bytes (~256 bits
# of entropy when sourced from a CSPRNG) is the OWASP recommendation for HMAC
# and signed-cookie keys. See SECURITY-FINDINGS.md A02-1.
_MIN_SECRET_KEY_LENGTH = 32

# Widest network a trusted proxy entry may name, by IP version.
_MIN_PROXY_PREFIX = {4: 8, 6: 16}

# Environment names that count as non-production for the startup checks below.
_DEVELOPMENT_ENVIRONMENTS = frozenset({"development", "local", "test"})


def _invalid_proxy_entry_message(entry: str) -> str:
    """Explain why a trusted proxy entry did not parse as a strict network.

    Args:
        entry (str): The rejected entry.

    Returns:
        str: A message that names the setting and, for a network with host bits
            set, the corrected network.
    """
    try:
        corrected = ipaddress.ip_network(entry, strict=False)
    except ValueError:
        return (
            "LLC_MANAGER_TRUSTED_PROXY_IPS entries must be IP addresses or CIDR "
            f"networks; got {entry!r}."
        )
    return (
        f"LLC_MANAGER_TRUSTED_PROXY_IPS entry {entry!r} has host bits set, which "
        f"uvicorn would silently never match; use {corrected} instead."
    )


def _is_placeholder_secret_key(value: str) -> bool:
    """Return True when a secret key looks like a shipped placeholder.

    Every placeholder this project has shipped (the package default and the
    old ``.env.example`` value) starts with ``change-``, and a value like that
    is never a random key, so the whole prefix is rejected.

    Args:
        value (str): The configured secret key.

    Returns:
        bool: True for a value starting with ``change-``, ignoring case and
            surrounding whitespace.
    """
    return value.strip().lower().startswith(_PLACEHOLDER_KEY_PREFIX)


class Settings(BaseSettings):
    """Configuration settings for the application, loaded from environment variables.

    Attributes:
        model_config (ClassVar[SettingsConfigDict]): Pydantic settings configuration (class-level config, not an instance field).
        log_level (Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]): The logging level for the application.
        json_logs (bool): Flag to enable or disable JSON formatted logs.
        include_timestamp (bool): Flag to include timestamps in logs.
        database_host (str): Database server hostname.
        database_port (int): Database server port.
        database_user (str): Database user name.
        database_password (str): Database password.
        database_name (str): Database name.
        database_echo (bool): Echo SQL statements for debugging.
        database_pool_size (int): Connection pool size.
        database_max_overflow (int): Max overflow connections beyond pool size.
        api_host (str): API server bind host.
        api_port (int): API server port.
        api_reload (bool): Enable auto-reload for development.
        api_workers (int): Number of worker processes.
        api_title (str): API documentation title.
        api_version (str): API version string.
        cors_origins (list[str]): List of allowed CORS origins.
        environment (str | None): Deployment environment name
            (``LLC_MANAGER_ENVIRONMENT``, then ``ENVIRONMENT``), read from the
            process environment and the env file. An unset name is not
            treated as development by the auth checks.
        secret_key (str): Secret key for signing tokens.
        access_token_expire_minutes (int): Token expiration time in minutes.
        public_base_url (str | None): Public ``https://`` origin of the app,
            for example ``https://llc.example.com``. OIDC redirect URIs are
            built from it, never from request headers.
        authentik_issuer (str | None): Authentik OIDC issuer URL, typically
            ``https://<authentik-host>/application/o/<slug>/``.
        authentik_client_id (str | None): OAuth2 client ID of the Authentik
            provider.
        authentik_client_secret (SecretStr | None): OAuth2 client secret.
        authentik_groups_claim (str): ID token claim that holds group names.
        admin_group (str): Group name that maps to the admin role.
        viewer_group (str): Group name that maps to the viewer role.
        session_max_age_seconds (int): Absolute lifetime of a browser session.
        local_admin_enabled (bool): Switch for the break-glass admin login.
        local_admin_password_hash (SecretStr | None): Argon2 hash of the
            break-glass password. Never a plaintext password.
        trusted_proxy_ips (Annotated[list[str], NoDecode]): Comma-separated IP
            addresses or CIDR networks of reverse proxies whose forwarded
            headers are trusted.
        auth_dev_mode (bool): Sign in as a fixed admin without Authentik.
            Refused unless the environment name is explicitly development,
            local, or test.
        api_key (SecretStr | None): Shared key that callers of ``/api/v1``
            send in the ``X-API-Key`` header. Read from
            ``LLC_MANAGER_API_KEY`` or, if that is unset,
            ``LLC_MANAGER_SERVICE_API_KEY``. An unset or empty key means
            ``/api/v1`` refuses every request with 503; there is no fallback.
        documents_root (Path): Directory that holds stored document files,
            named by document ID. Files are only ever served from here.
    """

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix="LLC_MANAGER_",
        case_sensitive=False,
        populate_by_name=True,
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # Logging settings
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    json_logs: bool = False
    include_timestamp: bool = True

    # Database settings
    database_host: str = "localhost"
    database_port: int = 5432
    database_user: str = "llc_manager"
    database_password: str = "llc_manager"  # noqa: S105  # Local-dev default matching docker-compose; production overrides via LLC_MANAGER_DATABASE_PASSWORD
    database_name: str = "llc_manager"
    database_echo: bool = False
    database_pool_size: int = 5
    database_max_overflow: int = 10

    # API settings
    api_host: str = "0.0.0.0"  # noqa: S104  # nosec B104  # Containerized app requires 0.0.0.0 to accept ingress traffic
    api_port: int = 8000
    api_reload: bool = False
    api_workers: int = 1
    api_title: str = "LLC Manager API"
    api_version: str = "0.1.0"

    # CORS settings
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Deployment environment name, read from the process environment and the
    # env file alike (``LLC_MANAGER_ENVIRONMENT``, then ``ENVIRONMENT``). An
    # unset name is *not* development; see ``explicit_development_environment``.
    environment: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LLC_MANAGER_ENVIRONMENT", "ENVIRONMENT"),
    )

    # Security settings
    secret_key: str = _DEFAULT_SECRET_KEY_PLACEHOLDER
    access_token_expire_minutes: int = 30

    # Browser login through Authentik OIDC (see ADR-003). /api/v1 keeps the
    # X-API-Key check in core/auth.py; these settings only drive the web UI.
    public_base_url: str | None = None
    authentik_issuer: str | None = None
    authentik_client_id: str | None = None
    authentik_client_secret: SecretStr | None = None
    authentik_groups_claim: str = Field(default="groups", min_length=1)
    admin_group: str = Field(default="llc-manager-admins", min_length=1)
    viewer_group: str = Field(default="llc-manager-viewers", min_length=1)
    session_max_age_seconds: int = Field(default=28800, gt=0)

    # Break-glass local admin login, off by default.
    local_admin_enabled: bool = False
    local_admin_password_hash: SecretStr | None = None

    # Reverse proxies whose X-Forwarded-* headers are trusted.
    trusted_proxy_ips: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # Fixed admin user, no Authentik. Refused unless the environment is
    # explicitly development, local, or test.
    auth_dev_mode: bool = False

    # Inbound service authentication for /api/v1 (see core/auth.py). An explicit
    # validation alias bypasses env_prefix, so both full names are listed; the
    # first one that is set wins.
    api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "LLC_MANAGER_API_KEY", "LLC_MANAGER_SERVICE_API_KEY"
        ),
    )

    # Document file store. Files are written and served as
    # ``{documents_root}/{document_id}{extension}`` and never by caller path.
    documents_root: Path = Path("/data/docs")

    @field_validator("secret_key", mode="before")
    @classmethod
    def _blank_secret_key_is_unset(cls, value: object) -> object:
        """Treat a blank secret key as unset.

        ``.env.example`` ships ``LLC_MANAGER_SECRET_KEY=`` with no value. A
        blank key falls back to the package default, which the validators below
        refuse outside development, so it is never used as a signing key.

        Args:
            value (object): The raw value.

        Returns:
            object: The package default for a blank string, else the value
                unchanged.
        """
        if isinstance(value, str) and not value.strip():
            return _DEFAULT_SECRET_KEY_PLACEHOLDER
        return value

    @field_validator("api_key", mode="after")
    @classmethod
    def _empty_api_key_is_unset(cls, value: SecretStr | None) -> SecretStr | None:
        """Treat an empty API key as unset.

        An empty value (for example ``LLC_MANAGER_API_KEY=`` in an env file)
        must behave like no key at all, so the API answers 503 as documented
        instead of the startup length check failing.

        Args:
            value (SecretStr | None): The parsed key.

        Returns:
            SecretStr | None: None for an empty key, else the key unchanged.
        """
        if value is not None and not value.get_secret_value():
            return None
        return value

    @model_validator(mode="after")
    def _enforce_api_key_min_length(self) -> "Settings":
        """Reject a short API key outside development environments.

        Returns:
            Settings: The validated settings.

        Raises:
            ConfigurationError: If the key is shorter than the minimum length
                outside development, local, and test environments.
        """
        if self.api_key is None:
            return self
        if len(self.api_key.get_secret_value()) >= _MIN_SECRET_KEY_LENGTH:
            return self
        if self.explicit_development_environment:
            return self
        message = (
            f"LLC_MANAGER_API_KEY (or LLC_MANAGER_SERVICE_API_KEY) must be at "
            f"least {_MIN_SECRET_KEY_LENGTH} characters outside development, "
            "local, and test environments. An unset environment name counts as "
            "production."
        )
        raise ConfigurationError(message, details={"config_key": "api_key"})

    @model_validator(mode="after")
    def _reject_default_secret_key_outside_dev(self) -> "Settings":
        """Block startup when a placeholder secret_key is used outside dev.

        A comment saying "change me in production" does not prevent a real
        deployment from accidentally shipping with a public default key, which
        would let anyone forge a session cookie. Anything other than an
        explicit ``development`` / ``local`` / ``test`` environment name (an
        unset name included) must supply a real key. The package default, the
        old ``.env.example`` value, and any value starting with ``change-`` are
        refused.

        Returns:
            Settings: The validated settings.

        Raises:
            ConfigurationError: If the key is a placeholder outside
                development, local, and test environments.
        """
        # #CRITICAL: Security - a public secret key lets an attacker sign an
        # admin session cookie, so an unset environment name must not relax it.
        # #VERIFY: tests/unit/test_security_audit_fixes.py::TestPlaceholderSecretKeys.
        if not _is_placeholder_secret_key(self.secret_key):
            return self

        if self.explicit_development_environment:
            return self

        message = (
            "LLC_MANAGER_SECRET_KEY must be set to a real random value (for "
            "example `openssl rand -hex 32`), not a placeholder starting with "
            "'change-', outside development, local, and test environments. An "
            "unset environment name counts as production."
        )
        raise ConfigurationError(message, details={"config_key": "secret_key"})

    @model_validator(mode="after")
    def _enforce_secret_key_min_length(self) -> "Settings":
        """Reject short secret keys outside development environments.

        The placeholder check above only catches placeholder values. A user-
        supplied but trivially short value (e.g. "secret") would otherwise
        pass. OWASP recommends >= 256 bits of entropy for HMAC/signing keys;
        we enforce 32 characters as a proxy.

        Returns:
            Settings: The validated settings.

        Raises:
            ConfigurationError: If the key is shorter than the minimum length
                outside development, local, and test environments.
        """
        if _is_placeholder_secret_key(self.secret_key):
            # Already handled by the placeholder validator above.
            return self

        if len(self.secret_key) >= _MIN_SECRET_KEY_LENGTH:
            return self

        if self.explicit_development_environment:
            return self

        message = (
            f"LLC_MANAGER_SECRET_KEY must be at least {_MIN_SECRET_KEY_LENGTH} "
            "characters outside development, local, and test environments. An "
            "unset environment name counts as production."
        )
        raise ConfigurationError(message, details={"config_key": "secret_key"})

    @field_validator(
        "public_base_url",
        "authentik_issuer",
        "authentik_client_id",
        "authentik_client_secret",
        "local_admin_password_hash",
        "environment",
        mode="before",
    )
    @classmethod
    def _blank_auth_value_is_unset(cls, value: object) -> object:
        """Treat a blank auth setting as unset.

        An empty value (for example ``LLC_MANAGER_AUTHENTIK_ISSUER=`` in an env
        file) must behave like no value at all.

        Args:
            value (object): The raw value.

        Returns:
            object: None for a blank string, else the value unchanged.
        """
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("public_base_url", mode="after")
    @classmethod
    def _normalize_public_base_url(cls, value: str | None) -> str | None:
        """Require a bare http(s) origin and strip any trailing slash.

        Args:
            value (str | None): The configured URL.

        Returns:
            str | None: The origin without a trailing slash, or None.

        Raises:
            ConfigurationError: If the value is not a bare ``http://`` or
                ``https://`` origin.
        """
        if value is None:
            return None
        parts = urlsplit(value.strip())
        is_origin = (
            parts.scheme in {"http", "https"}
            and bool(parts.hostname)
            and parts.path in {"", "/"}
            and not parts.query
            and not parts.fragment
        )
        if not is_origin:
            message = (
                "LLC_MANAGER_PUBLIC_BASE_URL must be a bare http(s) origin such "
                "as https://llc.example.com (no path, query, or fragment)."
            )
            raise ConfigurationError(message, details={"config_key": "public_base_url"})
        return f"{parts.scheme}://{parts.netloc}"

    @field_validator("local_admin_password_hash", mode="after")
    @classmethod
    def _require_argon2_hash(cls, value: SecretStr | None) -> SecretStr | None:
        """Reject a break-glass value that is not an argon2 hash.

        Args:
            value (SecretStr | None): The configured hash.

        Returns:
            SecretStr | None: The value, unchanged.

        Raises:
            ConfigurationError: If the value does not start with ``$argon2``.
        """
        if value is not None and not value.get_secret_value().startswith("$argon2"):
            message = (
                "LLC_MANAGER_LOCAL_ADMIN_PASSWORD_HASH must be an argon2 hash "
                "(it starts with $argon2). Never set a plaintext password."
            )
            raise ConfigurationError(
                message, details={"config_key": "local_admin_password_hash"}
            )
        return value

    @field_validator("trusted_proxy_ips", mode="before")
    @classmethod
    def _split_proxy_ips(cls, value: object) -> object:
        """Accept a comma-separated string of proxy addresses.

        Args:
            value (object): The raw value.

        Returns:
            object: A list of stripped, non-empty items for a string, else the
                value unchanged.
        """
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("trusted_proxy_ips", mode="after")
    @classmethod
    def _check_proxy_ips(cls, value: list[str]) -> list[str]:
        """Require each entry to be a single host or a narrow private network.

        Args:
            value (list[str]): The configured entries.

        Returns:
            list[str]: The entries, unchanged.

        Raises:
            ConfigurationError: If an entry is not an IP address or network, has
                host bits set, is a network that is not private or loopback, or
                is a network broader than ``/8`` (IPv4) or ``/16`` (IPv6).
        """
        # #CRITICAL: Security - whoever is trusted here can choose the client IP
        # that the break-glass throttle keys on, so a public or very wide
        # network would let any caller dodge it. A single host is allowed even
        # when public, because a reverse proxy may sit on a public address.
        # #VERIFY: tests/unit/test_auth_settings.py::TestTrustedProxyIps.
        for entry in value:
            try:
                network = ipaddress.ip_network(entry, strict=True)
            except ValueError as exc:
                raise ConfigurationError(
                    _invalid_proxy_entry_message(entry),
                    details={"config_key": "trusted_proxy_ips"},
                ) from exc
            if network.num_addresses == 1:
                continue
            limit = _MIN_PROXY_PREFIX[network.version]
            if not (network.is_private or network.is_loopback):
                message = (
                    "LLC_MANAGER_TRUSTED_PROXY_IPS networks must be private or "
                    "loopback; a public proxy must be listed as a single "
                    f"address, not a network; got {entry!r}."
                )
                raise ConfigurationError(
                    message, details={"config_key": "trusted_proxy_ips"}
                )
            if network.prefixlen < limit:
                message = (
                    "LLC_MANAGER_TRUSTED_PROXY_IPS entries must not be broader "
                    f"than /{limit} for IPv{network.version}; got {entry!r}. "
                    "List the proxy's address or its container network."
                )
                raise ConfigurationError(
                    message, details={"config_key": "trusted_proxy_ips"}
                )
        return value

    @property
    def explicit_development_environment(self) -> bool:
        """Whether the environment is named, and named development-class.

        The name comes from the same sources as every other setting (process
        environment and env file), so a ``.env`` file cannot turn on a
        development-only feature while naming no environment. Unlike
        a ``.env`` entry counts, and an unset or blank name does not. Every
        startup check that relaxes outside production (secret key, API key,
        sign-in requirement) uses this property.

        Returns:
            bool: True only for an explicit ``development``, ``local``, or
            ``test`` name.
        """
        # #CRITICAL: Security - dev mode makes every visitor an administrator,
        # and the cookie Secure flag and https requirement hang off this too.
        # Failing closed on an unset name keeps a mis-deployed container safe.
        # #VERIFY: tests/unit/test_auth_settings.py::TestDevMode.
        name = (self.environment or "").strip().lower()
        return name in _DEVELOPMENT_ENVIRONMENTS

    @property
    def oidc_configured(self) -> bool:
        """Whether every setting that browser OIDC login needs is present."""
        return (
            self.authentik_issuer is not None
            and self.authentik_client_id is not None
            and self.authentik_client_secret is not None
            and self.public_base_url is not None
        )

    @property
    def _oidc_intended(self) -> bool:
        """Whether a setting that only the browser login uses has been set.

        ``authentik_issuer`` is deliberately not counted. It existed before
        browser login as a standalone placeholder, so a host that sets only the
        issuer must keep starting until the gate ships.
        """
        return (
            self.authentik_client_id is not None
            or self.authentik_client_secret is not None
        )

    @model_validator(mode="after")
    def _enforce_oidc_settings_are_complete(self) -> "Settings":
        """Reject a partly configured OIDC login.

        Setting the client ID or the client secret means the issuer, the other
        credential, and ``public_base_url`` must be set too. Setting neither
        leaves OIDC login unconfigured and is valid, whatever the issuer is.

        Returns:
            Settings: The validated settings.

        Raises:
            ConfigurationError: If OIDC login is intended but incomplete.
        """
        # #CRITICAL: startup - a host that sets none of the new client settings
        # must keep starting exactly as before (PR 1 to 3 hard rule).
        # #VERIFY: TestUnconfiguredProductionIsUnchanged in
        # tests/unit/test_auth_settings.py.
        if not self._oidc_intended or self.oidc_configured:
            return self
        message = (
            "LLC_MANAGER_AUTHENTIK_ISSUER, LLC_MANAGER_AUTHENTIK_CLIENT_ID, "
            "LLC_MANAGER_AUTHENTIK_CLIENT_SECRET, and LLC_MANAGER_PUBLIC_BASE_URL "
            "must all be set together."
        )
        raise ConfigurationError(message, details={"config_key": "authentik_issuer"})

    @model_validator(mode="after")
    def _enforce_local_admin_needs_hash(self) -> "Settings":
        """Reject an enabled break-glass login that has no password hash.

        Returns:
            Settings: The validated settings.

        Raises:
            ConfigurationError: If the login is enabled without a hash.
        """
        if self.local_admin_enabled and self.local_admin_password_hash is None:
            message = (
                "LLC_MANAGER_LOCAL_ADMIN_ENABLED requires "
                "LLC_MANAGER_LOCAL_ADMIN_PASSWORD_HASH."
            )
            raise ConfigurationError(
                message, details={"config_key": "local_admin_password_hash"}
            )
        return self

    @model_validator(mode="after")
    def _refuse_dev_mode_outside_development(self) -> "Settings":
        """Block startup when the dev-mode login is on in a non-dev environment.

        Returns:
            Settings: The validated settings.

        Raises:
            ConfigurationError: If ``auth_dev_mode`` is true outside
                development, local, and test environments.
        """
        # #CRITICAL: Security - dev mode signs everyone in as admin.
        # #VERIFY: tests/unit/test_auth_settings.py covers production refusal,
        # an unset name, and a name that only a .env file supplies.
        if self.auth_dev_mode and not self.explicit_development_environment:
            message = (
                "LLC_MANAGER_AUTH_DEV_MODE must not be enabled unless "
                "LLC_MANAGER_ENVIRONMENT (or ENVIRONMENT) is explicitly "
                "development, local, or test."
            )
            raise ConfigurationError(message, details={"config_key": "auth_dev_mode"})
        return self

    @model_validator(mode="after")
    def _require_https_outside_development(self) -> "Settings":
        """Require https for the public URL, and the issuer once login is intended.

        Returns:
            Settings: The validated settings.

        Raises:
            ConfigurationError: If a configured URL is not ``https://`` and the
                environment is not explicitly development, local, or test.
        """
        if self.explicit_development_environment:
            return self
        # The issuer is only checked once browser login is intended; see
        # ``_oidc_intended``.
        checked = [("public_base_url", self.public_base_url)]
        if self._oidc_intended:
            checked.append(("authentik_issuer", self.authentik_issuer))
        for key, value in checked:
            if value is not None and not value.startswith("https://"):
                message = (
                    f"LLC_MANAGER_{key.upper()} must start with https:// unless "
                    "the environment is explicitly development, local, or test."
                )
                raise ConfigurationError(message, details={"config_key": key})
        return self

    @model_validator(mode="after")
    def _require_a_sign_in_method_outside_development(self) -> "Settings":
        """Refuse to start a non-development app that nobody could sign in to.

        The web UI is gated, so outside an explicit development, local, or test
        environment the app needs ``public_base_url`` and either a complete
        Authentik configuration or the break-glass login with its hash. An
        unset or blank environment name is not development.

        Returns:
            Settings: The validated settings.

        Raises:
            ConfigurationError: If the sign-in configuration is missing.
        """
        # #CRITICAL: Security - fail closed. Without this the gated UI would
        # start and answer every page with a redirect to a login that cannot
        # work, or (with an unnamed environment) look healthy while unusable.
        # #VERIFY: tests/unit/test_auth_settings.py::TestProductionRequiresSignIn
        # covers each missing piece, an unset name, and a blank name.
        if self.explicit_development_environment:
            return self
        break_glass = (
            self.local_admin_enabled and self.local_admin_password_hash is not None
        )
        missing: list[str] = []
        if self.public_base_url is None:
            missing.append(
                "LLC_MANAGER_PUBLIC_BASE_URL (the https address users visit)"
            )
        if not self.oidc_configured and not break_glass:
            missing.append(
                "a sign-in method: either LLC_MANAGER_AUTHENTIK_ISSUER, "
                "LLC_MANAGER_AUTHENTIK_CLIENT_ID and "
                "LLC_MANAGER_AUTHENTIK_CLIENT_SECRET, or "
                "LLC_MANAGER_LOCAL_ADMIN_ENABLED=true with "
                "LLC_MANAGER_LOCAL_ADMIN_PASSWORD_HASH"
            )
        if not missing:
            return self
        message = (
            "The web UI requires a way to sign in, and this process is not in an "
            "explicit development environment (LLC_MANAGER_ENVIRONMENT is unset "
            "or is not one of development, local, test). Missing: "
            + "; ".join(missing)
            + ". See docs/guides/authentik-setup.md. For local development set "
            "LLC_MANAGER_ENVIRONMENT=development."
        )
        raise ConfigurationError(message, details={"config_key": "public_base_url"})

    @computed_field  # type: ignore[prop-decorator]  # Pydantic pattern: decorator composition confuses pyright
    @property
    def database_url(self) -> str:
        """Construct the async database URL from components."""
        return str(
            PostgresDsn.build(
                scheme="postgresql+asyncpg",
                username=self.database_user,
                password=self.database_password,
                host=self.database_host,
                port=self.database_port,
                path=self.database_name,
            )
        )

    @computed_field  # type: ignore[prop-decorator]  # Pydantic pattern: decorator composition confuses pyright
    @property
    def database_url_sync(self) -> str:
        """Construct the sync database URL for Alembic migrations."""
        return str(
            PostgresDsn.build(
                scheme="postgresql+psycopg",
                username=self.database_user,
                password=self.database_password,
                host=self.database_host,
                port=self.database_port,
                path=self.database_name,
            )
        )


# A single, global instance of the settings
settings = Settings()
