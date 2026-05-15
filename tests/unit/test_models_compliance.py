"""Tests for compliance-date logic on entity-related models.

Covers:
- TaxFiling.is_overdue: current, past, and far-future dates; leap years; month-end
- Document.is_expired: same date boundary cases
- AuditMixin.is_deleted: soft-delete detection
- RegisteredAgent.full_address: address composition branches
- Document.tag_list: comma-separated tag parsing

These properties are the compliance/reminder primitives the rest of the
application would build "due date overdue / reminder needed" workflows on
top of, so they are exercised directly with a wide range of dates.

The "due-today" / "expires-today" boundary tests pin both the test and the
model to a single fixed datetime via ``_FROZEN_NOW`` so they cannot flip if
the wall clock crosses midnight between the test setup and the property
evaluation.
"""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from llc_manager.models.document import Document, DocumentType
from llc_manager.models.entity import Entity
from llc_manager.models.registered_agent import RegisteredAgent
from llc_manager.models.tax_filing import (
    FilingFrequency,
    FilingStatus,
    TaxFiling,
    TaxFilingType,
)

# A fixed reference moment used by the boundary tests. Both the test fixture
# and the model module's ``datetime.now(...)`` are forced to this value so the
# "due today / expires today" assertions cannot flip if the clock ticks past
# midnight between setup and evaluation.
_FROZEN_NOW = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
_FROZEN_TODAY = _FROZEN_NOW.date()


def _today() -> date:
    """Return the wall-clock date used by the model `is_overdue` properties.

    The model code uses ``datetime.now(UTC).date()`` -- mirror that here so
    tests are anchored to the same notion of "today" for the tests that
    deliberately exercise far-past / far-future dates and therefore don't
    care about midnight rollover.
    """
    return datetime.now(UTC).date()


@pytest.fixture
def frozen_now(monkeypatch: pytest.MonkeyPatch) -> datetime:
    """Freeze ``datetime.now`` in the model modules at ``_FROZEN_NOW``.

    Patches the ``datetime`` symbol imported by ``tax_filing`` and ``document``
    so ``is_overdue`` / ``is_expired`` resolve "today" deterministically.
    """
    frozen_dt = MagicMock(wraps=datetime)
    frozen_dt.now.return_value = _FROZEN_NOW
    monkeypatch.setattr("llc_manager.models.tax_filing.datetime", frozen_dt)
    monkeypatch.setattr("llc_manager.models.document.datetime", frozen_dt)
    return _FROZEN_NOW


class TestTaxFilingIsOverdue:
    """TaxFiling.is_overdue exercises the compliance due-date branch matrix."""

    @pytest.mark.unit
    def test_overdue_when_due_date_in_past(self) -> None:
        filing = TaxFiling(
            filing_type=TaxFilingType.FEDERAL_INCOME,
            jurisdiction="Federal",
            tax_year=2020,
            frequency=FilingFrequency.ANNUAL,
            status=FilingStatus.PENDING,
            due_date=_today() - timedelta(days=1),
        )
        assert filing.is_overdue is True

    @pytest.mark.unit
    def test_not_overdue_when_due_date_in_future(self) -> None:
        filing = TaxFiling(
            filing_type=TaxFilingType.FEDERAL_INCOME,
            jurisdiction="Federal",
            tax_year=2099,
            frequency=FilingFrequency.ANNUAL,
            status=FilingStatus.PENDING,
            due_date=_today() + timedelta(days=365 * 50),
        )
        assert filing.is_overdue is False

    @pytest.mark.unit
    def test_not_overdue_when_due_date_is_today(
        self, frozen_now: datetime
    ) -> None:
        """Due-today is *not* overdue -- model uses strict `>` comparison."""
        filing = TaxFiling(
            filing_type=TaxFilingType.STATE_INCOME,
            jurisdiction="CA",
            tax_year=2024,
            frequency=FilingFrequency.ANNUAL,
            status=FilingStatus.PENDING,
            due_date=frozen_now.date(),
        )
        assert filing.is_overdue is False

    @pytest.mark.unit
    def test_not_overdue_when_status_is_filed(self) -> None:
        """A filed return is never overdue, even with a past due_date."""
        filing = TaxFiling(
            filing_type=TaxFilingType.FRANCHISE_TAX,
            jurisdiction="DE",
            tax_year=2020,
            frequency=FilingFrequency.ANNUAL,
            status=FilingStatus.FILED,
            due_date=_today() - timedelta(days=400),
            filed_date=_today() - timedelta(days=300),
        )
        assert filing.is_overdue is False

    @pytest.mark.unit
    def test_extended_due_date_takes_precedence_over_due_date(self) -> None:
        """An extended date in the future overrides a past original due date."""
        filing = TaxFiling(
            filing_type=TaxFilingType.FEDERAL_INCOME,
            jurisdiction="Federal",
            tax_year=2024,
            frequency=FilingFrequency.ANNUAL,
            status=FilingStatus.EXTENDED,
            due_date=_today() - timedelta(days=10),
            extended_due_date=_today() + timedelta(days=180),
        )
        assert filing.is_overdue is False

    @pytest.mark.unit
    def test_overdue_when_extended_due_date_in_past(self) -> None:
        filing = TaxFiling(
            filing_type=TaxFilingType.FEDERAL_INCOME,
            jurisdiction="Federal",
            tax_year=2023,
            frequency=FilingFrequency.ANNUAL,
            status=FilingStatus.LATE,
            due_date=_today() - timedelta(days=200),
            extended_due_date=_today() - timedelta(days=30),
        )
        assert filing.is_overdue is True

    @pytest.mark.unit
    def test_not_overdue_when_no_due_date_set(self) -> None:
        """Filings without a due date can't be overdue."""
        filing = TaxFiling(
            filing_type=TaxFilingType.OTHER,
            jurisdiction="Federal",
            tax_year=2024,
            frequency=FilingFrequency.ONE_TIME,
            status=FilingStatus.PENDING,
        )
        assert filing.is_overdue is False

    @pytest.mark.unit
    def test_leap_year_feb_29_due_date_compares_correctly(self) -> None:
        """Feb 29 (leap year) in the past is recognized as overdue."""
        filing = TaxFiling(
            filing_type=TaxFilingType.ANNUAL_REPORT,
            jurisdiction="CA",
            tax_year=2020,
            frequency=FilingFrequency.ANNUAL,
            status=FilingStatus.PENDING,
            due_date=date(2020, 2, 29),
        )
        # 2020-02-29 is well in the past from any reasonable test date.
        assert filing.is_overdue is True

    @pytest.mark.unit
    def test_month_end_dec_31_past_is_overdue(self) -> None:
        """December 31 boundary: past year-end is overdue."""
        filing = TaxFiling(
            filing_type=TaxFilingType.ANNUAL_REPORT,
            jurisdiction="TX",
            tax_year=2020,
            frequency=FilingFrequency.ANNUAL,
            status=FilingStatus.PENDING,
            due_date=date(2020, 12, 31),
        )
        assert filing.is_overdue is True

    @pytest.mark.unit
    def test_far_future_due_date_not_overdue(self) -> None:
        """A due date 50 years in the future is not overdue."""
        filing = TaxFiling(
            filing_type=TaxFilingType.K1,
            jurisdiction="Federal",
            tax_year=2090,
            frequency=FilingFrequency.ANNUAL,
            status=FilingStatus.PENDING,
            due_date=date(2099, 12, 31),
        )
        assert filing.is_overdue is False

    @pytest.mark.unit
    def test_repr_includes_identifying_fields(self) -> None:
        filing = TaxFiling(
            filing_type=TaxFilingType.FEDERAL_INCOME,
            jurisdiction="Federal",
            tax_year=2024,
            frequency=FilingFrequency.ANNUAL,
            status=FilingStatus.PENDING,
        )
        text = repr(filing)
        assert "TaxFiling" in text
        assert "Federal" in text
        assert "2024" in text


class TestDocumentIsExpired:
    """Document.is_expired covers the only date-bearing branch on Document."""

    @pytest.mark.unit
    def test_expired_when_expiration_date_in_past(self) -> None:
        doc = Document(
            document_type=DocumentType.INSURANCE_POLICY,
            title="General liability",
            expiration_date=_today() - timedelta(days=1),
        )
        assert doc.is_expired is True

    @pytest.mark.unit
    def test_not_expired_when_expiration_date_in_future(self) -> None:
        doc = Document(
            document_type=DocumentType.INSURANCE_POLICY,
            title="General liability",
            expiration_date=_today() + timedelta(days=365),
        )
        assert doc.is_expired is False

    @pytest.mark.unit
    def test_not_expired_when_expiration_date_is_today(
        self, frozen_now: datetime
    ) -> None:
        doc = Document(
            document_type=DocumentType.LEASE,
            title="Office lease",
            expiration_date=frozen_now.date(),
        )
        assert doc.is_expired is False

    @pytest.mark.unit
    def test_not_expired_when_no_expiration_date(self) -> None:
        doc = Document(
            document_type=DocumentType.OPERATING_AGREEMENT,
            title="Operating agreement",
        )
        assert doc.is_expired is False

    @pytest.mark.unit
    def test_leap_year_expiration_classified_correctly(self) -> None:
        """Feb 29 2020 is firmly in the past from any current test date."""
        doc = Document(
            document_type=DocumentType.CERTIFICATE_OF_GOOD_STANDING,
            title="2020 standing",
            expiration_date=date(2020, 2, 29),
        )
        assert doc.is_expired is True

    @pytest.mark.unit
    def test_month_end_jan_31_far_future_not_expired(self) -> None:
        doc = Document(
            document_type=DocumentType.LEASE,
            title="Long lease",
            expiration_date=date(2099, 1, 31),
        )
        assert doc.is_expired is False


class TestDocumentTagList:
    """Document.tag_list parses comma-separated tags into a clean list."""

    @pytest.mark.unit
    def test_empty_tag_list_when_no_tags(self) -> None:
        doc = Document(document_type=DocumentType.OTHER, title="Untagged")
        assert doc.tag_list == []

    @pytest.mark.unit
    def test_single_tag(self) -> None:
        doc = Document(
            document_type=DocumentType.OTHER, title="Tagged", tags="formation"
        )
        assert doc.tag_list == ["formation"]

    @pytest.mark.unit
    def test_multiple_tags_with_whitespace_are_stripped(self) -> None:
        doc = Document(
            document_type=DocumentType.OTHER,
            title="Tagged",
            tags="formation,  tax  , compliance",
        )
        assert doc.tag_list == ["formation", "tax", "compliance"]

    @pytest.mark.unit
    def test_repr_includes_type_and_title(self) -> None:
        doc = Document(
            document_type=DocumentType.OPERATING_AGREEMENT,
            title="Operating Agreement",
        )
        text = repr(doc)
        assert "Document" in text
        assert "Operating Agreement" in text


class TestRegisteredAgentFullAddress:
    """RegisteredAgent.full_address composes parts and skips missing pieces."""

    @pytest.mark.unit
    def test_full_address_with_all_fields(self) -> None:
        agent = RegisteredAgent(
            state="DE",
            agent_name="Acme Agent",
            address="123 Main St",
            city="Wilmington",
            state_address="DE",
            zip_code="19801",
        )
        assert agent.full_address == "123 Main St\nWilmington, DE\n19801"

    @pytest.mark.unit
    def test_full_address_without_zip(self) -> None:
        agent = RegisteredAgent(
            state="DE",
            agent_name="Acme Agent",
            address="123 Main St",
            city="Wilmington",
            state_address="DE",
        )
        assert agent.full_address == "123 Main St\nWilmington, DE"

    @pytest.mark.unit
    def test_full_address_without_city_state(self) -> None:
        """Missing city/state suppresses the second line but keeps street + zip."""
        agent = RegisteredAgent(
            state="DE",
            agent_name="Acme Agent",
            address="123 Main St",
            zip_code="19801",
        )
        assert agent.full_address == "123 Main St\n19801"

    @pytest.mark.unit
    def test_full_address_empty_when_no_components(self) -> None:
        """No address components -> empty string (all parts filtered)."""
        agent = RegisteredAgent(state="DE", agent_name="Acme Agent")
        assert agent.full_address == ""

    @pytest.mark.unit
    def test_repr_includes_state_and_agent(self) -> None:
        agent = RegisteredAgent(state="DE", agent_name="Acme Agent")
        text = repr(agent)
        assert "DE" in text
        assert "Acme Agent" in text


class TestAuditMixinIsDeleted:
    """AuditMixin.is_deleted underpins soft-delete filtering in the API."""

    @pytest.mark.unit
    def test_is_deleted_false_when_deleted_at_none(self) -> None:
        entity = Entity(legal_name="ACME LLC")
        assert entity.is_deleted is False

    @pytest.mark.unit
    def test_is_deleted_true_when_deleted_at_set(self) -> None:
        entity = Entity(legal_name="ACME LLC")
        entity.deleted_at = datetime.now(UTC)
        assert entity.is_deleted is True


class TestEntityRelationshipProperties:
    """Entity.parent_entities / child_entities materialize the graph edges."""

    @pytest.mark.unit
    def test_parent_entities_empty_by_default(self) -> None:
        entity = Entity(legal_name="Standalone LLC")
        assert entity.parent_entities == []

    @pytest.mark.unit
    def test_child_entities_empty_by_default(self) -> None:
        entity = Entity(legal_name="Standalone LLC")
        assert entity.child_entities == []

    @pytest.mark.unit
    def test_repr_includes_legal_name(self) -> None:
        entity = Entity(legal_name="ACME LLC")
        text = repr(entity)
        assert "Entity" in text
        assert "ACME LLC" in text
