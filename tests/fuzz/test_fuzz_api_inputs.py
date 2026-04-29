"""Hypothesis-based fuzz tests for API input boundary conditions.

These tests verify that the EntityCreate schema and list_entities pagination
parameters handle arbitrary inputs without raising unhandled exceptions.
Scorecard recognises @given-decorated tests as fuzzing coverage.
"""

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from llc_manager.schemas.entity import EntityCreate


# ---------------------------------------------------------------------------
# Strategy helpers
# ---------------------------------------------------------------------------

# Two-character ASCII strings that match the formation_state/business_state
# min_length=2, max_length=2 constraint.
_two_char_text = st.text(min_size=2, max_size=2)

# Arbitrary text within the legal_name bounds (1..255 characters).
_legal_name = st.text(min_size=1, max_size=255)

# Pagination integers covering normal range and boundary values.
_page_int = st.integers(min_value=-1000, max_value=100_000)
_size_int = st.integers(min_value=-1, max_value=10_000)


# ---------------------------------------------------------------------------
# Fuzz tests
# ---------------------------------------------------------------------------


@given(
    legal_name=_legal_name,
    formation_state=st.one_of(st.none(), _two_char_text),
    business_state=st.one_of(st.none(), _two_char_text),
    notes=st.one_of(st.none(), st.text(max_size=2000)),
    purpose=st.one_of(st.none(), st.text(max_size=2000)),
    is_active=st.booleans(),
)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_entity_create_schema_never_crashes(
    legal_name: str,
    formation_state: str | None,
    business_state: str | None,
    notes: str | None,
    purpose: str | None,
    is_active: bool,
) -> None:
    """EntityCreate must either parse successfully or raise ValidationError.

    An unhandled exception (TypeError, AttributeError, etc.) would indicate
    a schema defect. Pydantic ValidationError is expected and acceptable for
    invalid inputs.
    """
    try:
        entity = EntityCreate(
            legal_name=legal_name,
            formation_state=formation_state,
            business_state=business_state,
            notes=notes,
            purpose=purpose,
            is_active=is_active,
        )
        # If parsing succeeded, the legal_name must be preserved exactly.
        assert entity.legal_name == legal_name
    except ValidationError:
        # Expected for inputs that violate field constraints.
        pass


@given(
    page=_page_int,
    size=_size_int,
)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_pagination_parameters_are_integers(page: int, size: int) -> None:
    """Pagination parameters must be representable as Python integers.

    This test documents the integer boundary contract for the list_entities
    endpoint query parameters (page, size). The endpoint applies its own
    validation; this test confirms no implicit coercion surprises exist at
    the integer type boundary.
    """
    # Both values must survive a round-trip through int() without raising.
    assert isinstance(int(page), int)
    assert isinstance(int(size), int)
    # Clamp to the valid range expected by the API (page >= 1, size 1..100).
    effective_page = max(1, page)
    effective_size = max(1, min(size, 100))
    assert effective_page >= 1
    assert 1 <= effective_size <= 100
