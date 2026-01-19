"""Tests for centralized exception hierarchy.

This module provides comprehensive tests for all exception classes in the
LLC Manager exception hierarchy, covering:
- Exception initialization with various parameters
- Details dictionary population
- Error code assignment
- to_dict() serialization for API responses
- Exception inheritance
"""

import pytest


class TestProjectBaseError:
    """Tests for ProjectBaseError base exception class."""

    @pytest.mark.unit
    def test_basic_initialization(self) -> None:
        """Verify basic initialization with message only."""
        from llc_manager.core.exceptions import ProjectBaseError

        error = ProjectBaseError("Test error message")

        assert str(error) == "Test error message"
        assert error.message == "Test error message"
        assert error.details == {}
        assert error.error_code is None

    @pytest.mark.unit
    def test_initialization_with_details(self) -> None:
        """Verify initialization with details dictionary."""
        from llc_manager.core.exceptions import ProjectBaseError

        details = {"key": "value", "count": 42}
        error = ProjectBaseError("Error with details", details=details)

        assert error.details == details
        assert error.details["key"] == "value"
        assert error.details["count"] == 42

    @pytest.mark.unit
    def test_initialization_with_error_code(self) -> None:
        """Verify initialization with error code."""
        from llc_manager.core.exceptions import ProjectBaseError

        error = ProjectBaseError("Coded error", error_code="ERR001")

        assert error.error_code == "ERR001"

    @pytest.mark.unit
    def test_to_dict_basic(self) -> None:
        """Verify to_dict returns correct structure for basic error."""
        from llc_manager.core.exceptions import ProjectBaseError

        error = ProjectBaseError("Basic error")
        result = error.to_dict()

        assert result == {
            "error": "ProjectBaseError",
            "message": "Basic error",
        }

    @pytest.mark.unit
    def test_to_dict_with_error_code(self) -> None:
        """Verify to_dict includes error code when present."""
        from llc_manager.core.exceptions import ProjectBaseError

        error = ProjectBaseError("Coded error", error_code="ERR001")
        result = error.to_dict()

        assert result["code"] == "ERR001"

    @pytest.mark.unit
    def test_to_dict_with_details(self) -> None:
        """Verify to_dict includes details when present."""
        from llc_manager.core.exceptions import ProjectBaseError

        details = {"field": "email", "reason": "invalid"}
        error = ProjectBaseError("Detailed error", details=details)
        result = error.to_dict()

        assert result["details"] == details

    @pytest.mark.unit
    def test_to_dict_full(self) -> None:
        """Verify to_dict with all parameters."""
        from llc_manager.core.exceptions import ProjectBaseError

        error = ProjectBaseError(
            "Full error",
            details={"extra": "info"},
            error_code="FULL001",
        )
        result = error.to_dict()

        assert result == {
            "error": "ProjectBaseError",
            "message": "Full error",
            "code": "FULL001",
            "details": {"extra": "info"},
        }

    @pytest.mark.unit
    def test_exception_is_catchable(self) -> None:
        """Verify exception can be caught and handled."""
        from llc_manager.core.exceptions import ProjectBaseError

        with pytest.raises(ProjectBaseError) as exc_info:
            raise ProjectBaseError("Catchable error")

        assert str(exc_info.value) == "Catchable error"


class TestConfigurationError:
    """Tests for ConfigurationError exception class."""

    @pytest.mark.unit
    def test_inheritance(self) -> None:
        """Verify ConfigurationError inherits from ProjectBaseError."""
        from llc_manager.core.exceptions import (
            ConfigurationError,
            ProjectBaseError,
        )

        error = ConfigurationError("Config issue")

        assert isinstance(error, ProjectBaseError)
        assert isinstance(error, Exception)

    @pytest.mark.unit
    def test_initialization(self) -> None:
        """Verify ConfigurationError initialization."""
        from llc_manager.core.exceptions import ConfigurationError

        error = ConfigurationError(
            "Missing required configuration",
            details={"missing_keys": ["DATABASE_URL", "SECRET_KEY"]},
        )

        assert error.message == "Missing required configuration"
        assert error.details["missing_keys"] == ["DATABASE_URL", "SECRET_KEY"]

    @pytest.mark.unit
    def test_to_dict_uses_correct_error_name(self) -> None:
        """Verify to_dict uses ConfigurationError as error name."""
        from llc_manager.core.exceptions import ConfigurationError

        error = ConfigurationError("Config issue")
        result = error.to_dict()

        assert result["error"] == "ConfigurationError"


class TestValidationError:
    """Tests for ValidationError exception class."""

    @pytest.mark.unit
    def test_inheritance(self) -> None:
        """Verify ValidationError inherits from ProjectBaseError."""
        from llc_manager.core.exceptions import (
            ProjectBaseError,
            ValidationError,
        )

        error = ValidationError("Validation failed")

        assert isinstance(error, ProjectBaseError)

    @pytest.mark.unit
    def test_basic_initialization(self) -> None:
        """Verify basic initialization with message only."""
        from llc_manager.core.exceptions import ValidationError

        error = ValidationError("Invalid input")

        assert error.message == "Invalid input"
        assert error.error_code == "VALIDATION_ERROR"

    @pytest.mark.unit
    def test_initialization_with_field(self) -> None:
        """Verify initialization with field parameter."""
        from llc_manager.core.exceptions import ValidationError

        error = ValidationError("Invalid email format", field="email")

        assert error.details["field"] == "email"

    @pytest.mark.unit
    def test_initialization_with_value(self) -> None:
        """Verify initialization with value parameter."""
        from llc_manager.core.exceptions import ValidationError

        error = ValidationError("Invalid input", value="bad_value")

        assert error.details["value"] == "bad_value"

    @pytest.mark.unit
    def test_value_truncation_for_long_values(self) -> None:
        """Verify long values are truncated to prevent log bloat."""
        from llc_manager.core.exceptions import ValidationError

        long_value = "x" * 200
        error = ValidationError("Value too long", value=long_value)

        assert len(error.details["value"]) == 103  # 100 chars + "..."
        assert error.details["value"].endswith("...")

    @pytest.mark.unit
    def test_short_value_not_truncated(self) -> None:
        """Verify short values are not truncated."""
        from llc_manager.core.exceptions import ValidationError

        short_value = "short"
        error = ValidationError("Short value", value=short_value)

        assert error.details["value"] == "short"

    @pytest.mark.unit
    def test_none_value_not_included(self) -> None:
        """Verify None value is not included in details."""
        from llc_manager.core.exceptions import ValidationError

        error = ValidationError("No value")

        assert "value" not in error.details

    @pytest.mark.unit
    def test_full_initialization(self) -> None:
        """Verify initialization with all parameters."""
        from llc_manager.core.exceptions import ValidationError

        error = ValidationError(
            "Invalid email format",
            field="email",
            value="not-an-email",
            details={"constraint": "email_format"},
            error_code="CUSTOM_VALIDATION",
        )

        assert error.message == "Invalid email format"
        assert error.details["field"] == "email"
        assert error.details["value"] == "not-an-email"
        assert error.details["constraint"] == "email_format"
        assert error.error_code == "CUSTOM_VALIDATION"


class TestResourceNotFoundError:
    """Tests for ResourceNotFoundError exception class."""

    @pytest.mark.unit
    def test_inheritance(self) -> None:
        """Verify ResourceNotFoundError inherits from ProjectBaseError."""
        from llc_manager.core.exceptions import (
            ProjectBaseError,
            ResourceNotFoundError,
        )

        error = ResourceNotFoundError("Not found")

        assert isinstance(error, ProjectBaseError)

    @pytest.mark.unit
    def test_basic_initialization(self) -> None:
        """Verify basic initialization sets default error code."""
        from llc_manager.core.exceptions import ResourceNotFoundError

        error = ResourceNotFoundError("Resource not found")

        assert error.error_code == "NOT_FOUND"

    @pytest.mark.unit
    def test_initialization_with_resource_type(self) -> None:
        """Verify initialization with resource_type parameter."""
        from llc_manager.core.exceptions import ResourceNotFoundError

        error = ResourceNotFoundError("Not found", resource_type="User")

        assert error.details["resource_type"] == "User"

    @pytest.mark.unit
    def test_initialization_with_resource_id(self) -> None:
        """Verify initialization with resource_id parameter."""
        from llc_manager.core.exceptions import ResourceNotFoundError

        error = ResourceNotFoundError("Not found", resource_id="user_123")

        assert error.details["resource_id"] == "user_123"

    @pytest.mark.unit
    def test_full_initialization(self) -> None:
        """Verify initialization with all parameters."""
        from llc_manager.core.exceptions import ResourceNotFoundError

        error = ResourceNotFoundError(
            "User not found",
            resource_type="User",
            resource_id="user_123",
        )

        assert error.details["resource_type"] == "User"
        assert error.details["resource_id"] == "user_123"


class TestAuthenticationError:
    """Tests for AuthenticationError exception class."""

    @pytest.mark.unit
    def test_inheritance(self) -> None:
        """Verify AuthenticationError inherits from ProjectBaseError."""
        from llc_manager.core.exceptions import (
            AuthenticationError,
            ProjectBaseError,
        )

        error = AuthenticationError()

        assert isinstance(error, ProjectBaseError)

    @pytest.mark.unit
    def test_default_message(self) -> None:
        """Verify default message is used when not provided."""
        from llc_manager.core.exceptions import AuthenticationError

        error = AuthenticationError()

        assert error.message == "Authentication failed"

    @pytest.mark.unit
    def test_default_error_code(self) -> None:
        """Verify default error code is set."""
        from llc_manager.core.exceptions import AuthenticationError

        error = AuthenticationError()

        assert error.error_code == "AUTH_FAILED"

    @pytest.mark.unit
    def test_custom_message(self) -> None:
        """Verify custom message can be provided."""
        from llc_manager.core.exceptions import AuthenticationError

        error = AuthenticationError("Invalid or expired token")

        assert error.message == "Invalid or expired token"


class TestAuthorizationError:
    """Tests for AuthorizationError exception class."""

    @pytest.mark.unit
    def test_inheritance(self) -> None:
        """Verify AuthorizationError inherits from ProjectBaseError."""
        from llc_manager.core.exceptions import (
            AuthorizationError,
            ProjectBaseError,
        )

        error = AuthorizationError()

        assert isinstance(error, ProjectBaseError)

    @pytest.mark.unit
    def test_default_message(self) -> None:
        """Verify default message is used when not provided."""
        from llc_manager.core.exceptions import AuthorizationError

        error = AuthorizationError()

        assert error.message == "Permission denied"

    @pytest.mark.unit
    def test_default_error_code(self) -> None:
        """Verify default error code is set."""
        from llc_manager.core.exceptions import AuthorizationError

        error = AuthorizationError()

        assert error.error_code == "FORBIDDEN"

    @pytest.mark.unit
    def test_initialization_with_required_permission(self) -> None:
        """Verify initialization with required_permission parameter."""
        from llc_manager.core.exceptions import AuthorizationError

        error = AuthorizationError(required_permission="admin:write")

        assert error.details["required_permission"] == "admin:write"

    @pytest.mark.unit
    def test_initialization_with_resource(self) -> None:
        """Verify initialization with resource parameter."""
        from llc_manager.core.exceptions import AuthorizationError

        error = AuthorizationError(resource="settings")

        assert error.details["resource"] == "settings"

    @pytest.mark.unit
    def test_full_initialization(self) -> None:
        """Verify initialization with all parameters."""
        from llc_manager.core.exceptions import AuthorizationError

        error = AuthorizationError(
            "Insufficient permissions",
            required_permission="admin:write",
            resource="settings",
        )

        assert error.details["required_permission"] == "admin:write"
        assert error.details["resource"] == "settings"


class TestExternalServiceError:
    """Tests for ExternalServiceError exception class."""

    @pytest.mark.unit
    def test_inheritance(self) -> None:
        """Verify ExternalServiceError inherits from ProjectBaseError."""
        from llc_manager.core.exceptions import (
            ExternalServiceError,
            ProjectBaseError,
        )

        error = ExternalServiceError("Service error")

        assert isinstance(error, ProjectBaseError)

    @pytest.mark.unit
    def test_default_error_code(self) -> None:
        """Verify default error code is set."""
        from llc_manager.core.exceptions import ExternalServiceError

        error = ExternalServiceError("Service unavailable")

        assert error.error_code == "EXTERNAL_SERVICE_ERROR"

    @pytest.mark.unit
    def test_initialization_with_service_name(self) -> None:
        """Verify initialization with service_name parameter."""
        from llc_manager.core.exceptions import ExternalServiceError

        error = ExternalServiceError("Service error", service_name="Stripe")

        assert error.details["service_name"] == "Stripe"

    @pytest.mark.unit
    def test_initialization_with_status_code(self) -> None:
        """Verify initialization with status_code parameter."""
        from llc_manager.core.exceptions import ExternalServiceError

        error = ExternalServiceError("Service error", status_code=503)

        assert error.details["status_code"] == 503

    @pytest.mark.unit
    def test_full_initialization(self) -> None:
        """Verify initialization with all parameters."""
        from llc_manager.core.exceptions import ExternalServiceError

        error = ExternalServiceError(
            "Payment gateway unavailable",
            service_name="Stripe",
            status_code=503,
        )

        assert error.details["service_name"] == "Stripe"
        assert error.details["status_code"] == 503


class TestAPIError:
    """Tests for APIError exception class."""

    @pytest.mark.unit
    def test_inheritance(self) -> None:
        """Verify APIError inherits from ExternalServiceError."""
        from llc_manager.core.exceptions import (
            APIError,
            ExternalServiceError,
        )

        error = APIError("API error")

        assert isinstance(error, ExternalServiceError)

    @pytest.mark.unit
    def test_default_error_code(self) -> None:
        """Verify default error code is set."""
        from llc_manager.core.exceptions import APIError

        error = APIError("API failure")

        assert error.error_code == "API_ERROR"

    @pytest.mark.unit
    def test_initialization_with_details(self) -> None:
        """Verify initialization with details parameter including retry_after."""
        from llc_manager.core.exceptions import APIError

        error = APIError("Rate limited", details={"retry_after": 60})

        assert error.details is not None
        assert error.details["retry_after"] == 60

    @pytest.mark.unit
    def test_full_initialization(self) -> None:
        """Verify initialization with all parameters."""
        from llc_manager.core.exceptions import APIError

        error = APIError(
            "GitHub API rate limit exceeded",
            service_name="GitHub",
            status_code=429,
            details={"retry_after": 60},
        )

        # service_name and status_code are stored in details dict
        assert error.details is not None
        assert error.details["service_name"] == "GitHub"
        assert error.details["status_code"] == 429
        assert error.details["retry_after"] == 60


class TestDatabaseError:
    """Tests for DatabaseError exception class."""

    @pytest.mark.unit
    def test_inheritance(self) -> None:
        """Verify DatabaseError inherits from ExternalServiceError."""
        from llc_manager.core.exceptions import (
            DatabaseError,
            ExternalServiceError,
        )

        error = DatabaseError("Database error")

        assert isinstance(error, ExternalServiceError)

    @pytest.mark.unit
    def test_default_error_code(self) -> None:
        """Verify default error code is set."""
        from llc_manager.core.exceptions import DatabaseError

        error = DatabaseError("Database failure")

        assert error.error_code == "DATABASE_ERROR"

    @pytest.mark.unit
    def test_default_service_name(self) -> None:
        """Verify default service_name is 'database'."""
        from llc_manager.core.exceptions import DatabaseError

        error = DatabaseError("Database failure")

        assert error.details["service_name"] == "database"

    @pytest.mark.unit
    def test_initialization_with_operation(self) -> None:
        """Verify initialization with operation parameter."""
        from llc_manager.core.exceptions import DatabaseError

        error = DatabaseError("Constraint violation", operation="insert")

        assert error.details["operation"] == "insert"

    @pytest.mark.unit
    def test_initialization_with_table(self) -> None:
        """Verify initialization with table parameter."""
        from llc_manager.core.exceptions import DatabaseError

        error = DatabaseError("Query failed", table="users")

        assert error.details["table"] == "users"

    @pytest.mark.unit
    def test_full_initialization(self) -> None:
        """Verify initialization with all parameters."""
        from llc_manager.core.exceptions import DatabaseError

        error = DatabaseError(
            "Unique constraint violation",
            operation="insert",
            table="users",
        )

        assert error.details["operation"] == "insert"
        assert error.details["table"] == "users"
        assert error.details["service_name"] == "database"


class TestBusinessLogicError:
    """Tests for BusinessLogicError exception class."""

    @pytest.mark.unit
    def test_inheritance(self) -> None:
        """Verify BusinessLogicError inherits from ProjectBaseError."""
        from llc_manager.core.exceptions import (
            BusinessLogicError,
            ProjectBaseError,
        )

        error = BusinessLogicError("Business rule violated")

        assert isinstance(error, ProjectBaseError)

    @pytest.mark.unit
    def test_default_error_code(self) -> None:
        """Verify default error code is set."""
        from llc_manager.core.exceptions import BusinessLogicError

        error = BusinessLogicError("Rule violation")

        assert error.error_code == "BUSINESS_RULE_VIOLATION"

    @pytest.mark.unit
    def test_initialization_with_rule(self) -> None:
        """Verify initialization with rule parameter."""
        from llc_manager.core.exceptions import BusinessLogicError

        error = BusinessLogicError("Insufficient funds", rule="minimum_balance")

        assert error.details["rule"] == "minimum_balance"

    @pytest.mark.unit
    def test_initialization_with_context(self) -> None:
        """Verify initialization with context parameter."""
        from llc_manager.core.exceptions import BusinessLogicError

        context = {"available": 100, "requested": 150}
        error = BusinessLogicError("Insufficient funds", context=context)

        assert error.details["context"] == context

    @pytest.mark.unit
    def test_full_initialization(self) -> None:
        """Verify initialization with all parameters."""
        from llc_manager.core.exceptions import BusinessLogicError

        error = BusinessLogicError(
            "Insufficient funds for transfer",
            rule="minimum_balance",
            context={"available": 100, "requested": 150},
        )

        assert error.details["rule"] == "minimum_balance"
        assert error.details["context"]["available"] == 100
        assert error.details["context"]["requested"] == 150


class TestExceptionHierarchy:
    """Tests for exception hierarchy and catchability."""

    @pytest.mark.unit
    def test_all_exceptions_catchable_as_project_base(self) -> None:
        """Verify all exceptions can be caught as ProjectBaseError."""
        from llc_manager.core.exceptions import (
            APIError,
            AuthenticationError,
            AuthorizationError,
            BusinessLogicError,
            ConfigurationError,
            DatabaseError,
            ExternalServiceError,
            ProjectBaseError,
            ResourceNotFoundError,
            ValidationError,
        )

        exceptions = [
            ConfigurationError("test"),
            ValidationError("test"),
            ResourceNotFoundError("test"),
            AuthenticationError("test"),
            AuthorizationError("test"),
            ExternalServiceError("test"),
            APIError("test"),
            DatabaseError("test"),
            BusinessLogicError("test"),
        ]

        for exc in exceptions:
            assert isinstance(exc, ProjectBaseError)

    @pytest.mark.unit
    def test_external_service_hierarchy(self) -> None:
        """Verify APIError and DatabaseError are ExternalServiceErrors."""
        from llc_manager.core.exceptions import (
            APIError,
            DatabaseError,
            ExternalServiceError,
        )

        api_error = APIError("API failed")
        db_error = DatabaseError("DB failed")

        assert isinstance(api_error, ExternalServiceError)
        assert isinstance(db_error, ExternalServiceError)

    @pytest.mark.unit
    def test_catching_by_parent_type(self) -> None:
        """Verify exceptions can be caught by parent type."""
        from llc_manager.core.exceptions import (
            APIError,
            ExternalServiceError,
            ProjectBaseError,
        )

        # Catch APIError as ExternalServiceError
        with pytest.raises(ExternalServiceError):
            raise APIError("API failed")

        # Catch APIError as ProjectBaseError
        with pytest.raises(ProjectBaseError):
            raise APIError("API failed")


class TestModuleExports:
    """Tests for module exports in __all__."""

    @pytest.mark.unit
    def test_all_exceptions_exported(self) -> None:
        """Verify all exception classes are exported."""
        from llc_manager.core import exceptions

        expected_exports = [
            "ProjectBaseError",
            "ConfigurationError",
            "ValidationError",
            "ResourceNotFoundError",
            "AuthenticationError",
            "AuthorizationError",
            "ExternalServiceError",
            "APIError",
            "DatabaseError",
            "BusinessLogicError",
        ]

        for export in expected_exports:
            assert hasattr(exceptions, export), f"{export} not exported from module"
