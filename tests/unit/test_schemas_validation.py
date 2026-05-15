"""Tests for Pydantic schema input validation.

These tests verify that the API contract layer rejects malformed input *before*
it reaches the database -- this is the application's primary defense against
bad EIN formats, invalid state codes, out-of-range percentages, and so on.

Each test makes a single assertion about one rule so a regression points at
the exact validator that broke.
"""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError as PydanticValidationError

from llc_manager.models.entity import EntityType
from llc_manager.models.owner import OwnershipType
from llc_manager.schemas.entity import (
    EntityCreate,
    EntityListResponse,
    EntityUpdate,
)
from llc_manager.schemas.owner import OwnerCreate, OwnerUpdate


class TestEntityCreateValidation:
    """EntityCreate enforces the LLC-input contract at the API boundary."""

    @pytest.mark.unit
    def test_minimal_valid_entity(self) -> None:
        ent = EntityCreate(legal_name="Acme LLC")
        assert ent.legal_name == "Acme LLC"
        assert ent.entity_type == EntityType.LLC
        assert ent.is_active is True

    @pytest.mark.unit
    def test_empty_legal_name_rejected(self) -> None:
        with pytest.raises(PydanticValidationError) as exc:
            EntityCreate(legal_name="")
        assert "legal_name" in str(exc.value)

    @pytest.mark.unit
    def test_legal_name_too_long_rejected(self) -> None:
        with pytest.raises(PydanticValidationError):
            EntityCreate(legal_name="x" * 256)

    @pytest.mark.unit
    def test_legal_name_whitespace_stripped(self) -> None:
        """BaseSchema sets str_strip_whitespace=True."""
        ent = EntityCreate(legal_name="  Acme LLC  ")
        assert ent.legal_name == "Acme LLC"

    @pytest.mark.unit
    def test_valid_ein_accepted(self) -> None:
        ent = EntityCreate(legal_name="Acme LLC", ein="12-3456789")
        assert ent.ein == "12-3456789"

    @pytest.mark.unit
    def test_empty_ein_accepted(self) -> None:
        """Empty string matches the trailing `|^$` branch of the EIN regex."""
        ent = EntityCreate(legal_name="Acme LLC", ein="")
        assert ent.ein == ""

    @pytest.mark.unit
    def test_invalid_ein_format_rejected(self) -> None:
        with pytest.raises(PydanticValidationError):
            EntityCreate(legal_name="Acme LLC", ein="123456789")

    @pytest.mark.unit
    def test_ein_with_letters_rejected(self) -> None:
        with pytest.raises(PydanticValidationError):
            EntityCreate(legal_name="Acme LLC", ein="AB-1234567")

    @pytest.mark.unit
    def test_invalid_state_too_short_rejected(self) -> None:
        with pytest.raises(PydanticValidationError):
            EntityCreate(legal_name="Acme LLC", formation_state="C")

    @pytest.mark.unit
    def test_invalid_state_too_long_rejected(self) -> None:
        with pytest.raises(PydanticValidationError):
            EntityCreate(legal_name="Acme LLC", formation_state="CAL")

    @pytest.mark.unit
    def test_valid_fiscal_year_end(self) -> None:
        ent = EntityCreate(legal_name="Acme LLC", fiscal_year_end="12-31")
        assert ent.fiscal_year_end == "12-31"

    @pytest.mark.unit
    def test_invalid_fiscal_year_end_month_rejected(self) -> None:
        with pytest.raises(PydanticValidationError):
            EntityCreate(legal_name="Acme LLC", fiscal_year_end="13-01")

    @pytest.mark.unit
    def test_invalid_fiscal_year_end_day_rejected(self) -> None:
        with pytest.raises(PydanticValidationError):
            EntityCreate(legal_name="Acme LLC", fiscal_year_end="02-32")

    @pytest.mark.unit
    def test_fiscal_year_end_wrong_format_rejected(self) -> None:
        with pytest.raises(PydanticValidationError):
            EntityCreate(legal_name="Acme LLC", fiscal_year_end="1231")

    @pytest.mark.unit
    def test_invalid_entity_type_rejected(self) -> None:
        with pytest.raises(PydanticValidationError):
            EntityCreate(legal_name="Acme LLC", entity_type="ufo")  # type: ignore[arg-type]

    @pytest.mark.unit
    def test_all_entity_types_accepted(self) -> None:
        for entity_type in EntityType:
            ent = EntityCreate(legal_name="x", entity_type=entity_type)
            assert ent.entity_type == entity_type

    @pytest.mark.unit
    def test_formation_date_accepts_date(self) -> None:
        ent = EntityCreate(legal_name="Acme LLC", formation_date=date(2020, 2, 29))
        assert ent.formation_date == date(2020, 2, 29)


class TestEntityUpdateValidation:
    """EntityUpdate is a partial schema -- all fields optional."""

    @pytest.mark.unit
    def test_empty_update_allowed(self) -> None:
        upd = EntityUpdate()
        assert upd.legal_name is None
        assert upd.is_active is None

    @pytest.mark.unit
    def test_partial_update_only_sets_provided_fields(self) -> None:
        upd = EntityUpdate(legal_name="New Name")
        dumped = upd.model_dump(exclude_unset=True)
        assert dumped == {"legal_name": "New Name"}

    @pytest.mark.unit
    def test_update_invalid_ein_rejected(self) -> None:
        with pytest.raises(PydanticValidationError):
            EntityUpdate(ein="not-an-ein")

    @pytest.mark.unit
    def test_update_invalid_state_rejected(self) -> None:
        with pytest.raises(PydanticValidationError):
            EntityUpdate(business_state="California")

    @pytest.mark.unit
    def test_update_empty_legal_name_rejected(self) -> None:
        with pytest.raises(PydanticValidationError):
            EntityUpdate(legal_name="")


class TestEntityListResponseShape:
    """EntityListResponse is the paginated wrapper used by `list_entities`."""

    @pytest.mark.unit
    def test_empty_list_response(self) -> None:
        resp = EntityListResponse(items=[], total=0, page=1, size=20, pages=1)
        assert resp.items == []
        assert resp.total == 0
        assert resp.pages == 1


class TestOwnerCreateValidation:
    """Ownership-percentage validators are financially load-bearing."""

    @pytest.mark.unit
    def test_minimal_valid_owner(self) -> None:
        from uuid import uuid4

        owner = OwnerCreate(owner_name="Alice", entity_id=uuid4())
        assert owner.owner_name == "Alice"
        assert owner.ownership_type == OwnershipType.MEMBER
        assert owner.ownership_percentage == Decimal("0.00")

    @pytest.mark.unit
    def test_ownership_percentage_negative_rejected(self) -> None:
        from uuid import uuid4

        with pytest.raises(PydanticValidationError):
            OwnerCreate(
                owner_name="Alice",
                entity_id=uuid4(),
                ownership_percentage=Decimal(-1),
            )

    @pytest.mark.unit
    def test_ownership_percentage_over_100_rejected(self) -> None:
        from uuid import uuid4

        with pytest.raises(PydanticValidationError):
            OwnerCreate(
                owner_name="Alice",
                entity_id=uuid4(),
                ownership_percentage=Decimal("100.01"),
            )

    @pytest.mark.unit
    def test_ownership_percentage_float_coerced_to_decimal(self) -> None:
        from uuid import uuid4

        owner = OwnerCreate(
            owner_name="Alice",
            entity_id=uuid4(),
            ownership_percentage=33.33,  # type: ignore[arg-type]
        )
        assert isinstance(owner.ownership_percentage, Decimal)
        assert owner.ownership_percentage == Decimal("33.33")

    @pytest.mark.unit
    def test_capital_contribution_negative_rejected(self) -> None:
        from uuid import uuid4

        with pytest.raises(PydanticValidationError):
            OwnerCreate(
                owner_name="Alice",
                entity_id=uuid4(),
                capital_contribution=Decimal(-100),
            )

    @pytest.mark.unit
    def test_ownership_percentage_none_converted_to_none(self) -> None:
        """The shared decimal-conversion validator passes None through."""
        from uuid import uuid4

        owner = OwnerCreate(
            owner_name="Alice",
            entity_id=uuid4(),
            profit_share_percentage=None,
        )
        assert owner.profit_share_percentage is None

    @pytest.mark.unit
    def test_owner_name_empty_rejected(self) -> None:
        from uuid import uuid4

        with pytest.raises(PydanticValidationError):
            OwnerCreate(owner_name="", entity_id=uuid4())

    @pytest.mark.unit
    def test_owner_missing_entity_id_rejected(self) -> None:
        with pytest.raises(PydanticValidationError):
            OwnerCreate(owner_name="Alice")  # type: ignore[call-arg]


class TestOwnerUpdateValidation:
    """OwnerUpdate exercises the partial-update validators on percentages."""

    @pytest.mark.unit
    def test_update_partial_ok(self) -> None:
        upd = OwnerUpdate(ownership_percentage=Decimal(50))
        assert upd.ownership_percentage == Decimal(50)

    @pytest.mark.unit
    def test_update_voting_percentage_over_100_rejected(self) -> None:
        with pytest.raises(PydanticValidationError):
            OwnerUpdate(voting_percentage=Decimal(101))

    @pytest.mark.unit
    def test_update_int_coerced_to_decimal(self) -> None:
        upd = OwnerUpdate(loss_share_percentage=25)  # type: ignore[arg-type]
        assert isinstance(upd.loss_share_percentage, Decimal)
        assert upd.loss_share_percentage == Decimal(25)

    @pytest.mark.unit
    def test_update_percentage_none_passes_through(self) -> None:
        upd = OwnerUpdate(ownership_percentage=None)
        assert upd.ownership_percentage is None
