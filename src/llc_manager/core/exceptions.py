"""Centralized exception hierarchy for LLC Manager.

This module provides a structured exception hierarchy for consistent error handling
across the application. All project-specific exceptions inherit from ProjectBaseError.

Exception Hierarchy:
    ProjectBaseError (base for all project exceptions)
    ├── ConfigurationError (configuration/settings issues)
    ├── ValidationError (input/data validation failures)
    ├── ResourceNotFoundError (missing resources/entities)
    ├── AuthenticationError (authentication failures)
    ├── AuthorizationError (permission/access denied)
    ├── ExternalServiceError (third-party service failures)
    │   ├── APIError (external API errors)
    │   └── DatabaseError (database operation errors)
    └── BusinessLogicError (domain/business rule violations)

Usage:
    from llc_manager.core.exceptions import (
        ValidationError,
        ResourceNotFoundError,
        ConfigurationError,
    )

    # Raise with context
    raise ValidationError("Invalid email format", field="email", value=user_input)

    # Handle in API endpoints
    try:
        process_data(input_data)
    except ValidationError as e:
        return {"error": str(e), "details": e.details}
"""

from __future__ import annotations

from typing import Any


class ProjectBaseError(Exception):
    """Base exception for all LLC Manager errors.

    All custom exceptions in the project should inherit from this class
    to enable unified error handling and logging.

    Attributes:
        message: Human-readable error message.
        details: Additional context about the error (optional).
        error_code: Machine-readable error code for API responses (optional).

    Example:
        >>> raise ProjectBaseError("Something went wrong", error_code="ERR001")
    """

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        error_code: str | None = None,
    ) -> None:
        """Initialize the exception.

        Args:
            message: Human-readable error description.
            details: Additional context as key-value pairs.
            error_code: Machine-readable error code.
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.error_code = error_code

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for API responses.

        Returns:
            Dictionary with error details suitable for JSON serialization.
        """
        result: dict[str, Any] = {
            "error": self.__class__.__name__,
            "message": self.message,
        }
        if self.error_code:
            result["code"] = self.error_code
        if self.details:
            result["details"] = self.details
        return result


class ConfigurationError(ProjectBaseError):
    """Configuration-related errors.

    Raised when there are issues with application configuration,
    environment variables, or settings validation.

    Example:
        >>> raise ConfigurationError(
        ...     "Missing required configuration",
        ...     details={"missing_keys": ["DATABASE_URL", "SECRET_KEY"]},
        ... )
    """


class ValidationError(ProjectBaseError):
    """Input validation errors.

    Raised when user input or data fails validation rules.
    Includes field-level error details for form validation.

    Example:
        >>> raise ValidationError(
        ...     "Invalid email format",
        ...     field="email",
        ...     value="not-an-email",
        ... )
    """

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        value: Any = None,
        details: dict[str, Any] | None = None,
        error_code: str | None = None,
    ) -> None:
        """Initialize validation error with field context.

        Args:
            message: Description of the validation failure.
            field: Name of the field that failed validation.
            value: The invalid value (will be sanitized in logs).
            details: Additional validation context.
            error_code: Machine-readable error code.
        """
        details = details or {}
        if field:
            details["field"] = field
        if value is not None:
            # Truncate long values to avoid log bloat
            str_value = str(value)
            details["value"] = (
                str_value[:100] + "..." if len(str_value) > 100 else str_value
            )
        super().__init__(
            message, details=details, error_code=error_code or "VALIDATION_ERROR"
        )


class ResourceNotFoundError(ProjectBaseError):
    """Resource not found errors.

    Raised when a requested resource (entity, file, record) cannot be found.

    Example:
        >>> raise ResourceNotFoundError(
        ...     "User not found",
        ...     resource_type="User",
        ...     resource_id="user_123",
        ... )
    """

    def __init__(
        self,
        message: str,
        *,
        resource_type: str | None = None,
        resource_id: str | None = None,
        details: dict[str, Any] | None = None,
        error_code: str | None = None,
    ) -> None:
        """Initialize resource not found error.

        Args:
            message: Description of what was not found.
            resource_type: Type of resource (e.g., "User", "Document").
            resource_id: Identifier of the missing resource.
            details: Additional context.
            error_code: Machine-readable error code.
        """
        details = details or {}
        if resource_type:
            details["resource_type"] = resource_type
        if resource_id:
            details["resource_id"] = resource_id
        super().__init__(message, details=details, error_code=error_code or "NOT_FOUND")


class AuthenticationError(ProjectBaseError):
    """Authentication failures.

    Raised when authentication fails (invalid credentials, expired tokens, etc.).

    Example:
        >>> raise AuthenticationError("Invalid or expired token")
    """

    def __init__(
        self,
        message: str = "Authentication failed",
        *,
        details: dict[str, Any] | None = None,
        error_code: str | None = None,
    ) -> None:
        """Initialize authentication error.

        Args:
            message: Description of authentication failure.
            details: Additional context (avoid including sensitive data).
            error_code: Machine-readable error code.
        """
        super().__init__(
            message, details=details, error_code=error_code or "AUTH_FAILED"
        )


class AuthorizationError(ProjectBaseError):
    """Authorization/permission errors.

    Raised when a user lacks permission to perform an action.

    Example:
        >>> raise AuthorizationError(
        ...     "Insufficient permissions",
        ...     required_permission="admin:write",
        ...     resource="settings",
        ... )
    """

    def __init__(
        self,
        message: str = "Permission denied",
        *,
        required_permission: str | None = None,
        resource: str | None = None,
        details: dict[str, Any] | None = None,
        error_code: str | None = None,
    ) -> None:
        """Initialize authorization error.

        Args:
            message: Description of permission failure.
            required_permission: The permission that was required.
            resource: The resource access was denied to.
            details: Additional context.
            error_code: Machine-readable error code.
        """
        details = details or {}
        if required_permission:
            details["required_permission"] = required_permission
        if resource:
            details["resource"] = resource
        super().__init__(message, details=details, error_code=error_code or "FORBIDDEN")


class ExternalServiceError(ProjectBaseError):
    """External service/dependency errors.

    Base class for errors from external services (APIs, databases, etc.).

    Example:
        >>> raise ExternalServiceError(
        ...     "Payment gateway unavailable",
        ...     service_name="Stripe",
        ...     status_code=503,
        ... )
    """

    def __init__(
        self,
        message: str,
        *,
        service_name: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
        error_code: str | None = None,
    ) -> None:
        """Initialize external service error.

        Args:
            message: Description of the service error.
            service_name: Name of the external service.
            status_code: HTTP status code if applicable.
            details: Additional context.
            error_code: Machine-readable error code.
        """
        details = details or {}
        if service_name:
            details["service_name"] = service_name
        if status_code:
            details["status_code"] = status_code
        super().__init__(
            message, details=details, error_code=error_code or "EXTERNAL_SERVICE_ERROR"
        )


class APIError(ExternalServiceError):
    """External API errors.

    Raised when calls to external APIs fail.

    Example:
        >>> raise APIError(
        ...     "GitHub API rate limit exceeded",
        ...     service_name="GitHub",
        ...     status_code=429,
        ...     retry_after=60,
        ... )
    """

    def __init__(
        self,
        message: str,
        *,
        service_name: str | None = None,
        status_code: int | None = None,
        retry_after: int | None = None,
        details: dict[str, Any] | None = None,
        error_code: str | None = None,
    ) -> None:
        """Initialize API error.

        Args:
            message: Description of the API error.
            service_name: Name of the external API.
            status_code: HTTP status code from the API.
            retry_after: Seconds to wait before retrying (for rate limits).
            details: Additional context.
            error_code: Machine-readable error code.
        """
        details = details or {}
        if retry_after:
            details["retry_after"] = retry_after
        super().__init__(
            message,
            service_name=service_name,
            status_code=status_code,
            details=details,
            error_code=error_code or "API_ERROR",
        )


class DatabaseError(ExternalServiceError):
    """Database operation errors.

    Raised when database operations fail (connection issues, constraint violations, etc.).

    Example:
        >>> raise DatabaseError(
        ...     "Unique constraint violation",
        ...     operation="insert",
        ...     table="users",
        ... )
    """

    def __init__(
        self,
        message: str,
        *,
        operation: str | None = None,
        table: str | None = None,
        details: dict[str, Any] | None = None,
        error_code: str | None = None,
    ) -> None:
        """Initialize database error.

        Args:
            message: Description of the database error.
            operation: The database operation that failed.
            table: The table/collection involved.
            details: Additional context.
            error_code: Machine-readable error code.
        """
        details = details or {}
        if operation:
            details["operation"] = operation
        if table:
            details["table"] = table
        super().__init__(
            message,
            service_name="database",
            details=details,
            error_code=error_code or "DATABASE_ERROR",
        )


class BusinessLogicError(ProjectBaseError):
    """Business logic/domain rule violations.

    Raised when operations violate business rules or domain constraints.

    Example:
        >>> raise BusinessLogicError(
        ...     "Insufficient funds for transfer",
        ...     rule="minimum_balance",
        ...     context={"available": 100, "requested": 150},
        ... )
    """

    def __init__(
        self,
        message: str,
        *,
        rule: str | None = None,
        context: dict[str, Any] | None = None,
        details: dict[str, Any] | None = None,
        error_code: str | None = None,
    ) -> None:
        """Initialize business logic error.

        Args:
            message: Description of the rule violation.
            rule: Name of the business rule violated.
            context: Business context for the violation.
            details: Additional context.
            error_code: Machine-readable error code.
        """
        details = details or {}
        if rule:
            details["rule"] = rule
        if context:
            details["context"] = context
        super().__init__(
            message, details=details, error_code=error_code or "BUSINESS_RULE_VIOLATION"
        )


# Export all exceptions
__all__ = [
    "APIError",
    "AuthenticationError",
    "AuthorizationError",
    "BusinessLogicError",
    "ConfigurationError",
    "DatabaseError",
    "ExternalServiceError",
    "ProjectBaseError",
    "ResourceNotFoundError",
    "ValidationError",
]
