"""Compliance summary on entity responses.

Covers the pure computation (``summarize_compliance``), the wiring into the
entity read endpoints, query-count behaviour on the list path, and backward
compatibility of the existing response fields. All names, dates, and agents in
the fixtures are made up. "Today" is always injected, never read from the
wall clock.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.orm import Session

from llc_manager.core.clock import get_today
from llc_manager.db.base import Base
from llc_manager.db.session import get_async_session
from llc_manager.main import create_app
from llc_manager.models.entity import Entity, EntityType
from llc_manager.models.registered_agent import RegisteredAgent
from llc_manager.models.state_registration import (
    RegistrationStatus,
    StateRegistration,
)
from llc_manager.models.tax_filing import (
    FilingFrequency,
    FilingStatus,
    TaxFiling,
    TaxFilingType,
)
from llc_manager.schemas.compliance import ComplianceStatus
from llc_manager.services.compliance import (
    DUE_SOON_DAYS,
    summarize_compliance,
)
from tests.auth_helpers import AUTH_HEADERS
from tests.integration.test_entities_api import (
    _FakeAsyncSession,
    _FakeResult,
    _make_entity,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

pytestmark = pytest.mark.unit

TODAY = date(2026, 6, 15)


def _registration(**overrides: object) -> StateRegistration:
    fields: dict[str, object] = {
        "id": uuid4(),
        "state": "DE",
        "status": RegistrationStatus.ACTIVE,
        "is_good_standing": True,
        "deleted_at": None,
    }
    fields.update(overrides)
    return StateRegistration(**fields)


def _filing(**overrides: object) -> TaxFiling:
    fields: dict[str, object] = {
        "id": uuid4(),
        "filing_type": TaxFilingType.FEDERAL_INCOME,
        "jurisdiction": "Federal",
        "tax_year": 2025,
        "frequency": FilingFrequency.ANNUAL,
        "status": FilingStatus.PENDING,
        "deleted_at": None,
    }
    fields.update(overrides)
    return TaxFiling(**fields)


def _agent(**overrides: object) -> RegisteredAgent:
    fields: dict[str, object] = {
        "id": uuid4(),
        "state": "DE",
        "agent_name": "Pat Example",
        "agent_company": None,
        "is_active": True,
        "deleted_at": None,
    }
    fields.update(overrides)
    return RegisteredAgent(**fields)


def _entity(
    *,
    registrations: list[StateRegistration] | None = None,
    filings: list[TaxFiling] | None = None,
    agents: list[RegisteredAgent] | None = None,
    is_active: bool = True,
) -> Entity:
    entity = _make_entity()
    entity.is_active = is_active
    entity.state_registrations = registrations or []
    entity.tax_filings = filings or []
    entity.registered_agents = agents or []
    return entity


def _in(days: int) -> date:
    return TODAY + timedelta(days=days)


# ---------------------------------------------------------------------------
# No obligations: never fabricate
# ---------------------------------------------------------------------------


class TestNoObligations:
    def test_entity_without_any_records_is_unknown_with_null_date(self) -> None:
        summary = summarize_compliance(_entity(), TODAY)

        assert summary.next_due_date is None
        assert summary.status is ComplianceStatus.UNKNOWN
        assert summary.registered_agent_name is None

    def test_records_without_dates_are_unknown(self) -> None:
        entity = _entity(
            registrations=[_registration()], filings=[_filing(due_date=None)]
        )

        summary = summarize_compliance(entity, TODAY)

        assert summary.next_due_date is None
        assert summary.status is ComplianceStatus.UNKNOWN

    def test_everything_filed_is_unknown_not_current(self) -> None:
        entity = _entity(
            filings=[
                _filing(
                    due_date=_in(-30),
                    filed_date=_in(-40),
                    status=FilingStatus.FILED,
                )
            ]
        )

        summary = summarize_compliance(entity, TODAY)

        assert summary.next_due_date is None
        assert summary.status is ComplianceStatus.UNKNOWN


# ---------------------------------------------------------------------------
# Single and multiple obligations
# ---------------------------------------------------------------------------


class TestObligations:
    def test_single_far_future_filing_is_current(self) -> None:
        entity = _entity(filings=[_filing(due_date=_in(200))])

        summary = summarize_compliance(entity, TODAY)

        assert summary.next_due_date == _in(200)
        assert summary.status is ComplianceStatus.CURRENT

    def test_single_registration_annual_report_counts(self) -> None:
        entity = _entity(registrations=[_registration(annual_report_due=_in(30))])

        summary = summarize_compliance(entity, TODAY)

        assert summary.next_due_date == _in(30)
        assert summary.status is ComplianceStatus.DUE_SOON

    def test_registration_renewal_and_expiration_dates_count(self) -> None:
        entity = _entity(
            registrations=[
                _registration(next_renewal_date=_in(120), expiration_date=_in(90))
            ]
        )

        summary = summarize_compliance(entity, TODAY)

        assert summary.next_due_date == _in(90)
        assert summary.status is ComplianceStatus.CURRENT

    def test_earliest_date_across_registrations_and_filings_wins(self) -> None:
        entity = _entity(
            registrations=[_registration(annual_report_due=_in(100))],
            filings=[_filing(due_date=_in(40)), _filing(due_date=_in(300))],
        )

        summary = summarize_compliance(entity, TODAY)

        assert summary.next_due_date == _in(40)
        assert summary.status is ComplianceStatus.DUE_SOON

    def test_worst_status_wins_overdue_beats_due_soon_beats_current(self) -> None:
        entity = _entity(
            registrations=[_registration(annual_report_due=_in(200))],
            filings=[_filing(due_date=_in(10)), _filing(due_date=_in(-5))],
        )

        summary = summarize_compliance(entity, TODAY)

        assert summary.status is ComplianceStatus.OVERDUE
        assert summary.next_due_date == _in(-5)

    def test_annual_report_filed_on_or_after_due_date_is_completed(self) -> None:
        entity = _entity(
            registrations=[
                _registration(
                    annual_report_due=_in(-10),
                    last_annual_report=_in(-10),
                    next_renewal_date=_in(150),
                )
            ]
        )

        summary = summarize_compliance(entity, TODAY)

        assert summary.next_due_date == _in(150)
        assert summary.status is ComplianceStatus.CURRENT

    def test_annual_report_last_filed_before_due_date_is_outstanding(self) -> None:
        entity = _entity(
            registrations=[
                _registration(annual_report_due=_in(-10), last_annual_report=_in(-375))
            ]
        )

        summary = summarize_compliance(entity, TODAY)

        assert summary.next_due_date == _in(-10)
        assert summary.status is ComplianceStatus.OVERDUE


# ---------------------------------------------------------------------------
# Boundary days
# ---------------------------------------------------------------------------


class TestBoundaries:
    def test_window_constant_is_sixty_days(self) -> None:
        assert DUE_SOON_DAYS == 60

    @pytest.mark.parametrize(
        ("days", "expected"),
        [
            (-1, ComplianceStatus.OVERDUE),
            (0, ComplianceStatus.DUE_SOON),
            (1, ComplianceStatus.DUE_SOON),
            (60, ComplianceStatus.DUE_SOON),
            (61, ComplianceStatus.CURRENT),
        ],
    )
    def test_boundary_days(self, days: int, expected: ComplianceStatus) -> None:
        entity = _entity(filings=[_filing(due_date=_in(days))])

        summary = summarize_compliance(entity, TODAY)

        assert summary.status is expected
        assert summary.next_due_date == _in(days)

    def test_today_is_injected_not_read_from_wall_clock(self) -> None:
        entity = _entity(filings=[_filing(due_date=date(2030, 1, 10))])

        assert (
            summarize_compliance(entity, date(2030, 1, 10)).status
            is ComplianceStatus.DUE_SOON
        )
        assert (
            summarize_compliance(entity, date(2030, 1, 11)).status
            is ComplianceStatus.OVERDUE
        )


# ---------------------------------------------------------------------------
# Filed, not-required, and ineligible records are ignored
# ---------------------------------------------------------------------------


class TestIgnoredRecords:
    def test_filed_by_date_or_status_is_ignored(self) -> None:
        entity = _entity(
            filings=[
                _filing(due_date=_in(-20), filed_date=_in(-25)),
                _filing(due_date=_in(-20), status=FilingStatus.FILED),
                _filing(due_date=_in(-20), status=FilingStatus.NOT_REQUIRED),
                _filing(due_date=_in(45)),
            ]
        )

        summary = summarize_compliance(entity, TODAY)

        assert summary.next_due_date == _in(45)
        assert summary.status is ComplianceStatus.DUE_SOON

    def test_soft_deleted_records_are_ignored(self) -> None:
        deleted = datetime(2026, 1, 1, tzinfo=UTC)
        entity = _entity(
            registrations=[
                _registration(annual_report_due=_in(-30), deleted_at=deleted)
            ],
            filings=[_filing(due_date=_in(-30), deleted_at=deleted)],
            agents=[_agent(agent_name="Deleted Agent", deleted_at=deleted)],
        )

        summary = summarize_compliance(entity, TODAY)

        assert summary.next_due_date is None
        assert summary.status is ComplianceStatus.UNKNOWN
        assert summary.registered_agent_name is None

    @pytest.mark.parametrize(
        "status",
        [
            RegistrationStatus.EXPIRED,
            RegistrationStatus.WITHDRAWN,
            RegistrationStatus.REVOKED,
        ],
    )
    def test_terminal_registrations_are_ignored(
        self, status: RegistrationStatus
    ) -> None:
        entity = _entity(
            registrations=[_registration(status=status, annual_report_due=_in(-30))]
        )

        summary = summarize_compliance(entity, TODAY)

        assert summary.next_due_date is None
        assert summary.status is ComplianceStatus.UNKNOWN

    @pytest.mark.parametrize(
        "status",
        [
            RegistrationStatus.ACTIVE,
            RegistrationStatus.PENDING,
            RegistrationStatus.REINSTATED,
            RegistrationStatus.SUSPENDED,
        ],
    )
    def test_live_registrations_count(self, status: RegistrationStatus) -> None:
        entity = _entity(
            registrations=[_registration(status=status, annual_report_due=_in(5))]
        )

        assert summarize_compliance(entity, TODAY).next_due_date == _in(5)

    def test_inactive_entity_has_no_applicable_obligations(self) -> None:
        entity = _entity(filings=[_filing(due_date=_in(-30))], is_active=False)

        summary = summarize_compliance(entity, TODAY)

        assert summary.next_due_date is None
        assert summary.status is ComplianceStatus.UNKNOWN


# ---------------------------------------------------------------------------
# Tax filing extensions
# ---------------------------------------------------------------------------


class TestExtensions:
    def test_extension_used_when_original_is_past(self) -> None:
        entity = _entity(
            filings=[
                _filing(
                    due_date=_in(-10),
                    extended_due_date=_in(90),
                    status=FilingStatus.EXTENDED,
                )
            ]
        )

        summary = summarize_compliance(entity, TODAY)

        assert summary.next_due_date == _in(90)
        assert summary.status is ComplianceStatus.CURRENT

    def test_past_extension_is_overdue_at_the_extended_date(self) -> None:
        entity = _entity(
            filings=[_filing(due_date=_in(-100), extended_due_date=_in(-3))]
        )

        summary = summarize_compliance(entity, TODAY)

        assert summary.next_due_date == _in(-3)
        assert summary.status is ComplianceStatus.OVERDUE

    def test_original_used_while_it_is_not_yet_past(self) -> None:
        entity = _entity(
            filings=[_filing(due_date=_in(20), extended_due_date=_in(200))]
        )

        summary = summarize_compliance(entity, TODAY)

        assert summary.next_due_date == _in(20)
        assert summary.status is ComplianceStatus.DUE_SOON

    def test_original_due_today_is_not_yet_past(self) -> None:
        entity = _entity(filings=[_filing(due_date=_in(0), extended_due_date=_in(200))])

        summary = summarize_compliance(entity, TODAY)

        assert summary.next_due_date == _in(0)
        assert summary.status is ComplianceStatus.DUE_SOON

    def test_extension_only_filing_uses_the_extended_date(self) -> None:
        entity = _entity(filings=[_filing(due_date=None, extended_due_date=_in(30))])

        assert summarize_compliance(entity, TODAY).next_due_date == _in(30)

    def test_past_original_without_extension_stays_overdue(self) -> None:
        entity = _entity(filings=[_filing(due_date=_in(-1))])

        assert summarize_compliance(entity, TODAY).status is ComplianceStatus.OVERDUE


# ---------------------------------------------------------------------------
# Registered agent display name
# ---------------------------------------------------------------------------


class TestRegisteredAgent:
    def test_company_name_preferred_then_agent_name(self) -> None:
        with_company = _entity(
            agents=[
                _agent(agent_name="Pat Example", agent_company="Example Agents Inc")
            ]
        )
        without_company = _entity(agents=[_agent(agent_name="Pat Example")])

        assert (
            summarize_compliance(with_company, TODAY).registered_agent_name
            == "Example Agents Inc"
        )
        assert (
            summarize_compliance(without_company, TODAY).registered_agent_name
            == "Pat Example"
        )

    def test_inactive_agent_is_ignored(self) -> None:
        entity = _entity(agents=[_agent(is_active=False)])

        assert summarize_compliance(entity, TODAY).registered_agent_name is None

    def test_blank_company_falls_back_to_agent_name(self) -> None:
        entity = _entity(agents=[_agent(agent_company="  ", agent_name="Pat Example")])

        assert (
            summarize_compliance(entity, TODAY).registered_agent_name == "Pat Example"
        )

    def test_formation_state_agent_preferred_when_several_are_active(self) -> None:
        entity = _entity(
            agents=[
                _agent(state="AA", agent_name="Alpha Agent"),
                _agent(state="DE", agent_name="Delaware Agent"),
            ]
        )
        entity.formation_state = "DE"

        assert (
            summarize_compliance(entity, TODAY).registered_agent_name
            == "Delaware Agent"
        )

    def test_choice_is_deterministic_without_a_formation_state_match(self) -> None:
        forward = _entity(
            agents=[
                _agent(state="ZZ", agent_name="Zulu Agent"),
                _agent(state="AA", agent_name="Alpha Agent"),
            ]
        )
        backward = _entity(
            agents=[
                _agent(state="AA", agent_name="Alpha Agent"),
                _agent(state="ZZ", agent_name="Zulu Agent"),
            ]
        )

        assert (
            summarize_compliance(forward, TODAY).registered_agent_name
            == summarize_compliance(backward, TODAY).registered_agent_name
            == "Alpha Agent"
        )


# ---------------------------------------------------------------------------
# Endpoint wiring and backward compatibility
# ---------------------------------------------------------------------------

_LEGACY_KEYS = {
    "id",
    "created_at",
    "updated_at",
    "created_by",
    "updated_by",
    "deleted_at",
    "deleted_by",
    "legal_name",
    "dba_names",
    "ein",
    "entity_type",
    "formation_state",
    "formation_date",
    "fiscal_year_end",
    "business_address",
    "business_city",
    "business_state",
    "business_zip",
    "mailing_address",
    "mailing_city",
    "mailing_state",
    "mailing_zip",
    "accounting_record_id",
    "xero_tenant_id",
    "purpose",
    "notes",
    "is_active",
    "bank_accounts",
}


def _client(session: _FakeAsyncSession, today: date = TODAY) -> TestClient:
    app = create_app()

    async def _session() -> AsyncIterator[_FakeAsyncSession]:
        yield session

    app.dependency_overrides[get_async_session] = _session
    app.dependency_overrides[get_today] = lambda: today
    return TestClient(app, headers=AUTH_HEADERS)


def _compliant_entity() -> Entity:
    entity = _entity(
        filings=[_filing(due_date=_in(30))],
        agents=[_agent(agent_name="Pat Example", agent_company="Example Agents Inc")],
    )
    entity.legal_name = "Sample Holdings LLC"
    return entity


class TestEndpoints:
    def test_list_items_carry_compliance_group(self) -> None:
        session = _FakeAsyncSession(
            [_FakeResult(scalar=1), _FakeResult(all_=[_compliant_entity()])]
        )

        body = _client(session).get("/api/v1/entities").json()

        assert body["items"][0]["compliance"] == {
            "next_due_date": _in(30).isoformat(),
            "status": "due_soon",
            "registered_agent_name": "Example Agents Inc",
        }

    def test_detail_carries_compliance_group(self) -> None:
        session = _FakeAsyncSession([_FakeResult(scalar_one=_compliant_entity())])

        body = _client(session).get(f"/api/v1/entities/{uuid4()}").json()

        assert body["compliance"]["status"] == "due_soon"
        assert body["compliance"]["next_due_date"] == _in(30).isoformat()

    def test_entity_with_no_obligations_returns_null_and_unknown(self) -> None:
        session = _FakeAsyncSession([_FakeResult(scalar_one=_entity())])

        body = _client(session).get(f"/api/v1/entities/{uuid4()}").json()

        assert body["compliance"] == {
            "next_due_date": None,
            "status": "unknown",
            "registered_agent_name": None,
        }

    def test_injected_clock_drives_the_status(self) -> None:
        entity = _entity(filings=[_filing(due_date=_in(30))])
        session = _FakeAsyncSession([_FakeResult(scalar_one=entity)])

        body = _client(session, today=_in(31)).get(f"/api/v1/entities/{uuid4()}").json()

        assert body["compliance"]["status"] == "overdue"

    def test_existing_response_fields_are_unchanged(self) -> None:
        entity = _compliant_entity()
        session = _FakeAsyncSession([_FakeResult(scalar_one=entity)])

        body = _client(session).get(f"/api/v1/entities/{uuid4()}").json()

        assert set(body) == _LEGACY_KEYS | {"compliance"}
        assert body["legal_name"] == "Sample Holdings LLC"
        assert body["entity_type"] == EntityType.LLC.value
        assert body["is_active"] is True
        assert body["bank_accounts"] == []

    def test_list_envelope_is_unchanged(self) -> None:
        session = _FakeAsyncSession([_FakeResult(scalar=0), _FakeResult(all_=[])])

        body = _client(session).get("/api/v1/entities").json()

        assert set(body) == {"items", "total", "page", "size", "pages"}

    def test_openapi_documents_the_group(self) -> None:
        schemas = create_app().openapi()["components"]["schemas"]

        compliance = schemas["EntityCompliance"]
        assert set(compliance["properties"]) == {
            "next_due_date",
            "status",
            "registered_agent_name",
        }
        assert schemas["ComplianceStatus"]["enum"] == [
            "current",
            "due_soon",
            "overdue",
            "unknown",
        ]
        assert "compliance" in schemas["EntityResponse"]["properties"]
        assert "compliance" not in schemas["EntityResponse"].get("required", [])

    def test_default_clock_dependency_returns_a_plain_utc_date(self) -> None:
        before = datetime.now(UTC).date()
        today = get_today()
        after = datetime.now(UTC).date()

        assert type(today) is date
        assert before <= today <= after


# ---------------------------------------------------------------------------
# Query count: summarising adds no queries and does not grow with entities
# ---------------------------------------------------------------------------


@pytest.fixture
def sqlite_engine() -> Iterator[Engine]:
    """Real SQLAlchemy engine (in-memory SQLite) with the production models."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def _seed(engine: Engine, count: int) -> None:
    with Session(engine) as session:
        for index in range(count):
            entity = Entity(
                legal_name=f"Sample {index:03d} LLC",
                entity_type=EntityType.LLC,
                is_active=True,
            )
            entity.state_registrations = [
                _registration(annual_report_due=_in(index), state="DE")
            ]
            entity.tax_filings = [_filing(due_date=_in(index + 5))]
            entity.registered_agents = [_agent(agent_name=f"Agent {index}")]
            session.add(entity)
        session.commit()


def _statements_for_list(engine: Engine) -> tuple[int, int]:
    """Return (statements to load a page, extra statements to summarise it)."""
    statements: list[str] = []

    def _record(*args: object) -> None:
        statements.append(str(args[2]))

    event.listen(engine, "before_cursor_execute", _record)
    try:
        with Session(engine) as session:
            entities = (
                session.execute(
                    select(Entity)
                    .where(Entity.deleted_at.is_(None))
                    .order_by(Entity.legal_name)
                    .limit(100)
                )
                .scalars()
                .all()
            )
            loaded = len(statements)
            summaries = [summarize_compliance(e, TODAY) for e in entities]
            assert len(summaries) == len(entities)
            assert all(s.next_due_date is not None for s in summaries)
            return loaded, len(statements) - loaded
    finally:
        event.remove(engine, "before_cursor_execute", _record)


class TestQueryCount:
    def test_summarising_issues_no_extra_queries(self, sqlite_engine: Engine) -> None:
        _seed(sqlite_engine, 5)

        _, extra = _statements_for_list(sqlite_engine)

        assert extra == 0

    def test_page_load_query_count_does_not_grow_with_entities(
        self, sqlite_engine: Engine
    ) -> None:
        _seed(sqlite_engine, 2)
        small, _ = _statements_for_list(sqlite_engine)

        _seed(sqlite_engine, 40)
        large, extra = _statements_for_list(sqlite_engine)

        assert large == small
        assert extra == 0
