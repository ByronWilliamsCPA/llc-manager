"""Integration tests for the HTMX/Jinja2 entity views."""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from llc_manager.db.session import get_async_session
from llc_manager.main import create_app
from llc_manager.models.entity import EntityType

FIXTURE_ID = UUID("11111111-1111-1111-1111-111111111111")


def _make_entity(
    entity_id: UUID = FIXTURE_ID, legal_name: str = "Acme Holdings LLC"
) -> SimpleNamespace:
    """Build a duck-typed entity object exposing every attribute the templates touch."""
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
    return SimpleNamespace(
        id=entity_id,
        legal_name=legal_name,
        dba_names=None,
        ein="12-3456789",
        entity_type=EntityType.LLC,
        formation_state="DE",
        formation_date=None,
        fiscal_year_end="12-31",
        business_address=None,
        business_city=None,
        business_state=None,
        business_zip=None,
        mailing_address=None,
        mailing_city=None,
        mailing_state=None,
        mailing_zip=None,
        accounting_record_id=None,
        purpose=None,
        notes=None,
        is_active=True,
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )


class _StubResult:
    """Minimal stand-in for SQLAlchemy's Result, supporting the call patterns the
    web routes use: scalar(), scalar_one_or_none(), scalars().all()."""

    def __init__(
        self, *, scalar: object = None, items: list[object] | None = None
    ) -> None:
        self._scalar = scalar
        self._items = items or []

    def scalar(self) -> object:
        return self._scalar

    def scalar_one_or_none(self) -> object:
        return self._scalar

    def scalars(self) -> "_StubResult":
        return self

    def all(self) -> list[object]:
        return self._items


class _StubSession:
    """Async session stub that returns canned results by sniffing the compiled
    SQL: a `count(*)` query yields the row count as `scalar()`; everything
    else yields the entity list (and the first entity as `scalar()` for
    detail-page single-row lookups)."""

    def __init__(self, entities: list[object]) -> None:
        self._entities = entities

    async def execute(self, query: object) -> _StubResult:
        if "count(" in str(query).lower():
            return _StubResult(scalar=len(self._entities), items=self._entities)
        return _StubResult(
            scalar=self._entities[0] if self._entities else None,
            items=self._entities,
        )


@pytest.fixture
def fixture_entity() -> SimpleNamespace:
    return _make_entity()


@pytest.fixture
def client_with_entities(fixture_entity: SimpleNamespace) -> Iterator[TestClient]:
    """TestClient with get_async_session overridden to yield a stubbed session
    that returns the fixture entity for both list and detail queries."""
    app = create_app()

    async def _override() -> AsyncIterator[_StubSession]:
        # Fresh session per request so call counters do not leak across requests.
        yield _StubSession([fixture_entity])

    app.dependency_overrides[get_async_session] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.integration
def test_entities_list_page_returns_200_with_table(
    client_with_entities: TestClient,
) -> None:
    """GET /entities renders the full page and includes the <table> element."""
    response = client_with_entities.get("/entities")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    body = response.text
    assert '<table class="data-table"' in body
    assert "Acme Holdings LLC" in body
    # The search input wired up for HTMX should be present.
    assert 'hx-get="/entities"' in body


@pytest.mark.integration
def test_entity_detail_page_returns_200_with_entity_name(
    client_with_entities: TestClient, fixture_entity: SimpleNamespace
) -> None:
    """GET /entities/{id} renders the detail template and includes the entity name."""
    response = client_with_entities.get(f"/entities/{fixture_entity.id}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert fixture_entity.legal_name in response.text
    # The Edit button should be wired to fetch the inline edit form.
    assert f'hx-get="/entities/{fixture_entity.id}/edit"' in response.text
