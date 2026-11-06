"""Configuration settings for LLC Manager.

Settings are loaded from environment variables with the prefix 'LLC_MANAGER_'.
Pydantic-settings handles the parsing and validation.
"""

import os
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import (
    AliasChoices,
    Field,
    PostgresDsn,
    SecretStr,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from llc_manager.core.exceptions import ConfigurationError

# Placeholder value shipped as the package default. Callers are expected to
# override via LLC_MANAGER_SECRET_KEY in any non-development deployment;
# see `Settings._reject_default_secret_key_outside_dev` for enforcement.
_DEFAULT_SECRET_KEY_PLACEHOLDER = "change-me-in-production"  # noqa: S105  # nosec B105 -- permanent false positive (reviewed PR #9); startup sentinel explicitly rejected by _reject_default_secret_key_outside_dev outside development

# Minimum acceptable SECRET_KEY length outside development. 32 bytes (~256 bits
# of entropy when sourced from a CSPRNG) is the OWASP recommendation for HMAC
# and signed-cookie keys. See SECURITY-FINDINGS.md A02-1.
_MIN_SECRET_KEY_LENGTH = 32

# Environment names that count as non-production for the startup checks below.
_DEVELOPMENT_ENVIRONMENTS = frozenset({"development", "local", "test"})


def _is_development_environment() -> bool:
    """Return True when the process runs in a development-class environment.

    Reads ``LLC_MANAGER_ENVIRONMENT``, then ``ENVIRONMENT``. An unset name
    counts as development.

    Returns:
        bool: True for ``development``, ``local``, ``test``, or no name at all.
    """
    # #ASSUME: Security - the environment name comes from the process
    # environment, so a value set only in a ``.env`` file is not seen here and
    # an unset name is treated as development.
    # #VERIFY: production deployments set LLC_MANAGER_ENVIRONMENT in the
    # container environment, not only in a file.
    env = (
        os.getenv("LLC_MANAGER_ENVIRONMENT")
        or os.getenv("ENVIRONMENT")
        or "development"
    ).lower()
    return env in _DEVELOPMENT_ENVIRONMENTS


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
        secret_key (str): Secret key for signing tokens.
        access_token_expire_minutes (int): Token expiration time in minutes.
        authentik_issuer (str | None): Authentik OIDC issuer URL.
        authentik_jwks_url (str | None): Authentik JWKS endpoint URL.
        authentik_audience (str | None): Authentik token audience.
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

    # Security settings
    secret_key: str = _DEFAULT_SECRET_KEY_PLACEHOLDER
    access_token_expire_minutes: int = 30

    # Authentik OIDC integration (placeholder - not yet wired into endpoints).
    # When set, a future per-user check in core/auth.py will validate
    # Authorization: Bearer JWTs against Authentik's JWKS. core/auth.py
    # currently holds only the interim API-key check. See SECURITY-FINDINGS.md
    # A01-1.
    authentik_issuer: str | None = None
    authentik_jwks_url: str | None = None
    authentik_audience: str | None = None

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
        if _is_development_environment():
            return self
        message = (
            f"LLC_MANAGER_API_KEY (or LLC_MANAGER_SERVICE_API_KEY) must be at "
            f"least {_MIN_SECRET_KEY_LENGTH} characters outside development, "
            "local, and test environments."
        )
        raise ConfigurationError(message, details={"config_key": "api_key"})

    @model_validator(mode="after")
    def _reject_default_secret_key_outside_dev(self) -> "Settings":
        """Block startup when the default secret_key is used in non-dev envs.

        A comment saying "change me in production" does not prevent a real
        deployment from accidentally shipping with a public default key. The
        validator reads LLC_MANAGER_ENVIRONMENT / ENVIRONMENT; anything other
        than ``development`` / ``local`` / ``test`` must supply an override.
        """
        if self.secret_key != _DEFAULT_SECRET_KEY_PLACEHOLDER:
            return self

        if _is_development_environment():
            return self

        message = (
            "LLC_MANAGER_SECRET_KEY must be set to a non-default value outside "
            "development, local, and test environments."
        )
        raise ConfigurationError(message, details={"config_key": "secret_key"})

    @model_validator(mode="after")
    def _enforce_secret_key_min_length(self) -> "Settings":
        """Reject short secret keys outside development environments.

        The placeholder check above only catches the literal default. A user-
        supplied but trivially short value (e.g. "secret") would otherwise
        pass. OWASP recommends >= 256 bits of entropy for HMAC/signing keys;
        we enforce 32 characters as a proxy.
        """
        if self.secret_key == _DEFAULT_SECRET_KEY_PLACEHOLDER:
            # Already handled by the placeholder validator above.
            return self

        if len(self.secret_key) >= _MIN_SECRET_KEY_LENGTH:
            return self

        if _is_development_environment():
            return self

        message = (
            f"LLC_MANAGER_SECRET_KEY must be at least {_MIN_SECRET_KEY_LENGTH} "
            "characters outside development, local, and test environments."
        )
        raise ConfigurationError(message, details={"config_key": "secret_key"})

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
