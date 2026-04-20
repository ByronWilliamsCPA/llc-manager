"""Sentry error tracking and performance monitoring integration.

This module provides production-ready Sentry integration with:
- Error tracking and reporting
- Performance monitoring (APM)
- User context and session tracking
- Custom tags and context
- Integration with FastAPI, Structlog, and SQLAlchemy

Setup:
    1. Install Sentry SDK:
       uv add sentry-sdk[fastapi]

    2. Set environment variables:
       SENTRY_DSN=https://...@....ingest.sentry.io/...
       SENTRY_ENVIRONMENT=production
       SENTRY_TRACES_SAMPLE_RATE=0.1  # 10% of transactions

    3. Initialize in your application:
       from llc_manager.core.sentry import init_sentry
       init_sentry()
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from typing import Any

from llc_manager.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class SentryConfig:
    """Configuration for Sentry initialization.

    Attributes:
        dsn: Sentry DSN (Data Source Name). Defaults to SENTRY_DSN env var.
        environment: Deployment environment (e.g., production, staging).
            Defaults to SENTRY_ENVIRONMENT or ENVIRONMENT env var.
        release: Application release version. Defaults to git SHA or version.
        traces_sample_rate: Percentage of transactions to sample (0.0-1.0).
        profiles_sample_rate: Percentage of profiling data to collect (0.0-1.0).
        enable_tracing: Enable performance monitoring (APM).
        enable_profiling: Enable profiling data collection.
        debug: Enable Sentry SDK debug logging.
    """

    dsn: str | None = None
    environment: str | None = None
    release: str | None = None
    traces_sample_rate: float = 0.1
    profiles_sample_rate: float = 0.1
    enable_tracing: bool = True
    enable_profiling: bool = True
    debug: bool = False

    @classmethod
    def from_env(cls) -> SentryConfig:
        """Create configuration from environment variables."""
        return cls(
            dsn=os.getenv("SENTRY_DSN"),
            environment=os.getenv("SENTRY_ENVIRONMENT")
            or os.getenv("ENVIRONMENT", "development"),
            release=os.getenv("SENTRY_RELEASE"),
        )


def init_sentry(config: SentryConfig | None = None) -> None:
    """Initialize Sentry error tracking and performance monitoring.

    Args:
        config: Sentry configuration. If None, configuration is loaded from
            environment variables.

    Example:
        >>> from llc_manager.core.sentry import init_sentry, SentryConfig
        >>> # Using environment variables (recommended)
        >>> init_sentry()
        >>>
        >>> # Using explicit configuration
        >>> init_sentry(
        ...     SentryConfig(
        ...         environment="production",
        ...         traces_sample_rate=0.2,  # Sample 20% of requests
        ...     )
        ... )
    """
    # #EDGE: External resource - sentry_sdk is an optional install. Missing
    # package must fail soft (log + return) so the app boots without it.
    # #VERIFY: Unit test initialize path with sentry_sdk uninstalled (mock
    # ImportError) asserts no exception propagates.
    if config is None:
        config = SentryConfig.from_env()
    try:
        import sentry_sdk  # noqa: PLC0415  # Import only when Sentry is configured
        from sentry_sdk.integrations.fastapi import FastApiIntegration  # noqa: PLC0415
        from sentry_sdk.integrations.logging import LoggingIntegration  # noqa: PLC0415
        from sentry_sdk.integrations.sqlalchemy import (  # noqa: PLC0415  # Load only when Sentry is configured
            SqlalchemyIntegration,
        )
        from sentry_sdk.integrations.starlette import (  # noqa: PLC0415  # Load only when Sentry is configured
            StarletteIntegration,
        )
    except ImportError:
        logger.warning(
            "Sentry SDK not installed. Install with: uv add sentry-sdk[fastapi]"
        )
        return

    # #ASSUME: Security - SENTRY_DSN absent is interpreted as "telemetry off",
    # not an error state. Silent telemetry-off is safe for local dev but must
    # not mask a misconfigured prod deployment.
    # #VERIFY: Deployment smoke test asserts SENTRY_DSN is set in staging and
    # production environments via env-specific CI checks.
    dsn = config.dsn or os.getenv("SENTRY_DSN")
    if not dsn:
        logger.info("SENTRY_DSN not set. Sentry integration disabled.")
        return

    environment = config.environment or "development"
    release = config.release or _get_release_version()

    # Configure integrations
    integrations: list[Any] = [
        # Logging integration - capture log messages as breadcrumbs
        LoggingIntegration(
            level=logging.INFO,  # Capture INFO and above
            event_level=logging.ERROR,  # Send ERROR and above as events
        ),
    ]

    # FastAPI integration - automatic request tracking
    integrations.extend(
        [
            StarletteIntegration(
                transaction_style="endpoint",  # Use endpoint name as transaction
                failed_request_status_codes=[range(500, 599)],  # Only 5xx errors
            ),
            FastApiIntegration(
                transaction_style="endpoint",
                failed_request_status_codes=[range(500, 599)],
            ),
        ]
    )
    # SQLAlchemy integration - track database queries
    integrations.append(SqlalchemyIntegration())
    # Initialize Sentry
    # pyright: ignore[reportCallIssue, reportArgumentType] justified: sentry_sdk is imported
    # lazily above in a try/except, so pyright cannot resolve the real init() signature.
    sentry_sdk.init(  # pyright: ignore[reportCallIssue, reportArgumentType]
        dsn=dsn,
        environment=environment,
        release=release,
        integrations=integrations,
        # Performance monitoring
        traces_sample_rate=config.traces_sample_rate if config.enable_tracing else 0.0,
        profiles_sample_rate=config.profiles_sample_rate
        if config.enable_profiling
        else 0.0,
        # Error sampling
        sample_rate=1.0,  # Send all errors
        # Additional options
        debug=config.debug,
        attach_stacktrace=True,  # Include stack traces in messages
        send_default_pii=False,  # Don't send PII by default (GDPR compliance)
        # Custom options
        before_send=before_send_hook,  # pyright: ignore[reportArgumentType]  # sentry_sdk EventProcessor uses Any-based kwargs; our typed hook is runtime-compatible
        before_breadcrumb=before_breadcrumb_hook,
    )

    logger.info(
        "sentry_initialized",
        environment=environment,
        release=release,
        traces_sample_rate=config.traces_sample_rate,
    )


def _get_release_version() -> str:
    """Get release version from git SHA or package version.

    Returns:
        Release version string (e.g., "myapp@1.0.0" or "myapp@abc123")
    """
    # Try to get git SHA
    try:
        sha = (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607  # Git is a trusted executable
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
        return f"llc_manager@{sha}"
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Fallback to package version
    try:
        from importlib.metadata import (  # noqa: PLC0415  # Late import keeps stdlib cost out of hot path when version is cached
            version,
        )

        pkg_version = version("llc-manager")
        return f"llc_manager@{pkg_version}"
    except Exception:  # noqa: BLE001  # Broad fallback to static version; logged below for observability
        logger.debug("Version lookup failed; falling back to static version string")

    # Ultimate fallback
    return "llc_manager@0.1.0"


_IGNORED_EXCEPTIONS = frozenset({"KeyboardInterrupt", "SystemExit"})
_SENSITIVE_FIELDS = frozenset({"password", "token", "api_key", "secret"})


def _should_ignore_exception(hint: dict[str, Any]) -> bool:
    """Check if the exception should be ignored (not sent to Sentry)."""
    if "exc_info" not in hint:
        return False
    exc_type, _exc_value, _tb = hint["exc_info"]
    return exc_type.__name__ in _IGNORED_EXCEPTIONS


def _scrub_sensitive_request_data(event: dict[str, Any]) -> None:
    """Redact sensitive fields from request data in-place."""
    request = event.get("request")
    if request is None:
        return

    data = request.get("data")
    if not isinstance(data, dict):
        return

    for field_name in _SENSITIVE_FIELDS:
        if field_name in data:
            data[field_name] = "[REDACTED]"


def before_send_hook(
    event: dict[str, Any], hint: dict[str, Any]
) -> dict[str, Any] | None:
    """Filter and modify events before sending to Sentry.

    This hook allows you to:
    - Filter out specific errors
    - Scrub sensitive data
    - Add custom context
    - Modify error grouping

    Args:
        event: Sentry event dictionary
        hint: Additional information about the event

    Returns:
        Modified event dictionary, or None to drop the event
    """
    if _should_ignore_exception(hint):
        return None

    _scrub_sensitive_request_data(event)
    return event


def before_breadcrumb_hook(
    crumb: dict[str, Any], _hint: dict[str, Any]
) -> dict[str, Any] | None:
    """Filter and modify breadcrumbs before adding to events.

    Breadcrumbs are actions/events leading up to an error.

    Args:
        crumb: Breadcrumb dictionary
        hint: Additional information about the breadcrumb

    Returns:
        Modified breadcrumb dictionary, or None to drop the breadcrumb
    """
    # Example: Don't include query parameters in HTTP breadcrumbs
    if (
        crumb.get("category") == "httplib"
        and "data" in crumb
        and "query" in crumb["data"]
    ):
        crumb["data"]["query"] = "[FILTERED]"

    return crumb


def capture_exception(
    exception: Exception,
    *,
    level: str = "error",
    tags: dict[str, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Manually capture an exception to Sentry with additional context.

    Args:
        exception: The exception to capture
        level: Severity level (debug, info, warning, error, fatal)
        tags: Custom tags for filtering (e.g., {"api": "v1", "user_type": "premium"})
        extra: Additional context data

    Example:
        >>> try:
        ...     risky_operation()
        ... except ValueError as e:
        ...     capture_exception(
        ...         e,
        ...         tags={"operation": "data_import"},
        ...         extra={"file_size": 1024, "row_count": 100},
        ...     )
    """
    try:
        import sentry_sdk  # noqa: PLC0415  # Optional dep; imported lazily to avoid hard dependency
    except ImportError:
        logger.warning("Sentry SDK not installed")
        return

    with sentry_sdk.push_scope() as scope:
        scope.level = level

        if tags:
            for key, value in tags.items():
                scope.set_tag(key, value)

        if extra:
            for key, value in extra.items():
                scope.set_extra(key, value)

        sentry_sdk.capture_exception(exception)


def capture_message(
    message: str,
    *,
    level: str = "info",
    tags: dict[str, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Capture a message (not an exception) to Sentry.

    Use for non-error events that you want to track.

    Args:
        message: The message to capture
        level: Severity level (debug, info, warning, error, fatal)
        tags: Custom tags for filtering
        extra: Additional context data

    Example:
        >>> capture_message(
        ...     "User completed onboarding",
        ...     level="info",
        ...     tags={"user_type": "trial"},
        ...     extra={"steps_completed": 5},
        ... )
    """
    try:
        import sentry_sdk  # noqa: PLC0415  # Optional dep; imported lazily to avoid hard dependency
    except ImportError:
        logger.warning("Sentry SDK not installed")
        return

    with sentry_sdk.push_scope() as scope:
        scope.level = level

        if tags:
            for key, value in tags.items():
                scope.set_tag(key, value)

        if extra:
            for key, value in extra.items():
                scope.set_extra(key, value)

        sentry_sdk.capture_message(message)


def set_user_context(
    user_id: str | None = None,
    email: str | None = None,
    username: str | None = None,
    **kwargs: Any,
) -> None:
    """Set user context for error tracking.

    This associates errors with specific users for better debugging.

    Args:
        user_id: Unique user identifier
        email: User email (will be scrubbed if PII filtering is enabled)
        username: User username
        **kwargs: Additional user attributes

    Example:
        >>> set_user_context(
        ...     user_id="user_123",
        ...     username="john_doe",
        ...     subscription="premium",
        ... )
    """
    try:
        import sentry_sdk  # noqa: PLC0415  # Optional dep; imported lazily to avoid hard dependency
    except ImportError:
        return

    user_data = {}
    if user_id:
        user_data["id"] = user_id
    if email:
        user_data["email"] = email
    if username:
        user_data["username"] = username
    user_data.update(kwargs)

    sentry_sdk.set_user(user_data)


def add_breadcrumb(
    message: str,
    category: str = "custom",
    level: str = "info",
    data: dict[str, Any] | None = None,
) -> None:
    """Add a breadcrumb (event leading up to an error).

    Breadcrumbs help you understand the sequence of events before an error.

    Args:
        message: Breadcrumb message
        category: Category (e.g., "auth", "query", "http")
        level: Severity level
        data: Additional data

    Example:
        >>> add_breadcrumb(
        ...     message="User clicked export button",
        ...     category="ui",
        ...     data={"format": "csv", "row_count": 1000},
        ... )
    """
    try:
        import sentry_sdk  # noqa: PLC0415  # Optional dep; imported lazily to avoid hard dependency
    except ImportError:
        return

    sentry_sdk.add_breadcrumb(
        message=message,
        category=category,
        level=level,
        data=data or {},
    )
