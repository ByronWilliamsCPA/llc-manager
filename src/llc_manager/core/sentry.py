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
from typing import Any

logger = logging.getLogger(__name__)


def init_sentry(
    dsn: str | None = None,
    environment: str | None = None,
    release: str | None = None,
    traces_sample_rate: float = 0.1,
    profiles_sample_rate: float = 0.1,
    enable_tracing: bool = True,
    enable_profiling: bool = True,
    debug: bool = False,
) -> None:
    """Initialize Sentry error tracking and performance monitoring.

    Args:
        dsn: Sentry DSN (Data Source Name). Defaults to SENTRY_DSN env var.
        environment: Deployment environment (e.g., production, staging).
            Defaults to SENTRY_ENVIRONMENT or ENVIRONMENT env var.
        release: Application release version. Defaults to git SHA or version.
        traces_sample_rate: Percentage of transactions to sample (0.0-1.0).
            Default 0.1 = 10% of requests.
        profiles_sample_rate: Percentage of profiling data to collect (0.0-1.0).
            Default 0.1 = 10% of traces.
        enable_tracing: Enable performance monitoring (APM).
        enable_profiling: Enable profiling data collection.
        debug: Enable Sentry SDK debug logging.

    Example:
        >>> from llc_manager.core.sentry import init_sentry
        >>> init_sentry(
        ...     environment="production",
        ...     traces_sample_rate=0.2,  # Sample 20% of requests
        ... )
    """
    try:
        import sentry_sdk  # noqa: PLC0415  # Import only when Sentry is configured
        from sentry_sdk.integrations.fastapi import FastApiIntegration  # noqa: PLC0415
        from sentry_sdk.integrations.logging import LoggingIntegration  # noqa: PLC0415
        from sentry_sdk.integrations.sqlalchemy import (
            SqlalchemyIntegration,
        )
        from sentry_sdk.integrations.starlette import (
            StarletteIntegration,
        )
    except ImportError:
        logger.warning(
            "Sentry SDK not installed. Install with: uv add sentry-sdk[fastapi]"
        )
        return

    # Get configuration from environment or arguments
    dsn = dsn or os.getenv("SENTRY_DSN")
    if not dsn:
        logger.info("SENTRY_DSN not set. Sentry integration disabled.")
        return

    environment = (
        environment
        or os.getenv("SENTRY_ENVIRONMENT")
        or os.getenv("ENVIRONMENT", "development")
    )
    release = release or os.getenv("SENTRY_RELEASE") or _get_release_version()

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
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release,
        integrations=integrations,
        # Performance monitoring
        traces_sample_rate=traces_sample_rate if enable_tracing else 0.0,
        profiles_sample_rate=profiles_sample_rate if enable_profiling else 0.0,
        # Error sampling
        sample_rate=1.0,  # Send all errors
        # Additional options
        debug=debug,
        attach_stacktrace=True,  # Include stack traces in messages
        send_default_pii=False,  # Don't send PII by default (GDPR compliance)
        # Custom options
        before_send=before_send_hook,
        before_breadcrumb=before_breadcrumb_hook,
    )

    logger.info(
        "sentry_initialized",
        environment=environment,
        release=release,
        traces_sample_rate=traces_sample_rate,
    )


def _get_release_version() -> str:
    """Get release version from git SHA or package version.

    Returns:
        Release version string (e.g., "myapp@1.0.0" or "myapp@abc123")
    """
    # Try to get git SHA
    try:
        import subprocess  # noqa: PLC0415  # Import only when needed (optional dependency)

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
        from importlib.metadata import (
            version,  # Import only when needed
        )

        pkg_version = version("llc-manager")
        return f"llc_manager@{pkg_version}"
    except Exception:  # noqa: BLE001  # Intentionally broad - fallback to static version
        pass

    # Ultimate fallback
    return "llc_manager@0.1.0"


def before_send_hook(
    event: dict[str, Any], _hint: dict[str, Any]
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
    # Example: Filter out specific exceptions
    if "exc_info" in _hint:
        exc_type, _exc_value, _tb = _hint["exc_info"]

        # Don't send certain exception types
        if exc_type.__name__ in ("KeyboardInterrupt", "SystemExit"):
            return None

    # Example: Scrub sensitive data from request bodies
    if "request" in event:
        request = event["request"]
        if "data" in request:
            # Remove sensitive fields
            sensitive_fields = {"password", "token", "api_key", "secret"}
            if isinstance(request["data"], dict):
                for field in sensitive_fields:
                    if field in request["data"]:
                        request["data"][field] = "[REDACTED]"

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
    if crumb.get("category") == "httplib":
        if "data" in crumb and "query" in crumb["data"]:
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
        import sentry_sdk
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
        import sentry_sdk
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
        import sentry_sdk
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
        import sentry_sdk
    except ImportError:
        return

    sentry_sdk.add_breadcrumb(
        message=message,
        category=category,
        level=level,
        data=data or {},
    )
