"""Configuration settings for LLC Manager.

Settings are loaded from environment variables with the prefix 'LLC_MANAGER_'.
Pydantic-settings handles the parsing and validation.
"""

from typing import Literal

from pydantic import PostgresDsn, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for the application, loaded from environment variables.

    Attributes:
        log_level: The logging level for the application.
        json_logs: Flag to enable or disable JSON formatted logs.
        include_timestamp: Flag to include timestamps in logs.
        database_*: Database connection settings.
        api_*: API server settings.
        cors_origins: List of allowed CORS origins.
    """

    model_config = SettingsConfigDict(
        env_prefix="LLC_MANAGER_",
        case_sensitive=False,
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
    api_host: str = "0.0.0.0"  # noqa: S104  # Containerized app requires 0.0.0.0 to accept ingress traffic
    api_port: int = 8000
    api_reload: bool = False
    api_workers: int = 1
    api_title: str = "LLC Manager API"
    api_version: str = "0.1.0"

    # CORS settings
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Security settings
    secret_key: str = "change-me-in-production"  # noqa: S105  # Placeholder default; real value MUST come from LLC_MANAGER_SECRET_KEY env var
    access_token_expire_minutes: int = 30

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
