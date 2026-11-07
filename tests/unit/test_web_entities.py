"""Integration tests for the HTMX/Jinja2 entity views."""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from html.parser import HTMLParser
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from llc_manager.auth.session import SESSION_COOKIE
from llc_manager.core.config import settings
from llc_manager.db.session import get_async_session
from llc_manager.main import create_app
from llc_manager.models.entity import EntityType
from tests.auth_helpers import (
    TEST_CSRF_TOKEN,
    session_cookie_value,
    user_session,
)

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
    SQL: a `count(*)` query yields the row count as `scalar()`; an EIN-uniqueness
    lookup (``ein =`` predicate) yields no row so the save path treats the EIN as
    free; everything else yields the entity list (and the first entity as
    `scalar()` for detail-page single-row lookups)."""

    def __init__(self, entities: list[object]) -> None:
        self._entities = entities

    async def execute(self, query: object) -> _StubResult:
        compiled = str(query).lower()
        if "count(" in compiled:
            return _StubResult(scalar=len(self._entities), items=self._entities)
        # The save path's EIN-uniqueness probe must not match the entity being
        # edited, otherwise every save would look like a duplicate-EIN conflict.
        if "ein =" in compiled and "id !=" in compiled:
            return _StubResult(scalar=None, items=[])
        return _StubResult(
            scalar=self._entities[0] if self._entities else None,
            items=self._entities,
        )

    async def flush(self) -> None:
        """No-op: the stub holds entities in memory; nothing to persist."""

    async def refresh(self, _instance: object) -> None:
        """No-op: in-memory entities need no reload after flush."""


@pytest.fixture
def fixture_entity() -> SimpleNamespace:
    return _make_entity()


@pytest.fixture
def client_with_entities(fixture_entity: SimpleNamespace) -> Iterator[TestClient]:
    """Signed-in admin TestClient with the database stubbed out.

    ``get_async_session`` is overridden to yield a stubbed session that returns
    the fixture entity for both list and detail queries. The client carries an
    admin session cookie and the matching ``X-CSRF-Token`` header, as a browser
    would after signing in (the web routes are gated).
    """
    app = create_app()

    async def _override() -> AsyncIterator[_StubSession]:
        # Fresh session per request so call counters do not leak across requests.
        yield _StubSession([fixture_entity])

    app.dependency_overrides[get_async_session] = _override
    with TestClient(app) as c:
        c.cookies.set(
            SESSION_COOKIE,
            session_cookie_value(settings.secret_key, user_session("admin")),
        )
        c.headers["X-CSRF-Token"] = TEST_CSRF_TOKEN
        yield c
    app.dependency_overrides.clear()


@pytest.mark.unit
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


class _FormControlCollector(HTMLParser):
    """Collect <input> attributes and <label for> targets/classes from HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.inputs: list[dict[str, str | None]] = []
        self.labels: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "input":
            self.inputs.append(dict(attrs))
        elif tag == "label":
            self.labels.append(dict(attrs))


@pytest.mark.unit
def test_entities_list_search_input_has_associated_label(
    client_with_entities: TestClient,
) -> None:
    """The search input has an id and a visually hidden <label for> naming it.

    Guards SonarCloud rule Web:InputWithoutLabelCheck (WCAG 1.3.1 / 4.1.2).
    """
    response = client_with_entities.get("/entities")

    assert response.status_code == 200
    collector = _FormControlCollector()
    collector.feed(response.text)
    search_inputs = [i for i in collector.inputs if i.get("name") == "q"]
    assert len(search_inputs) == 1
    search_input = search_inputs[0]
    input_id = search_input.get("id")
    assert input_id, "search input must have an id"
    labels = [lb for lb in collector.labels if lb.get("for") == input_id]
    assert len(labels) == 1, f'expected one <label for="{input_id}">'
    # The label is visually hidden so the layout is unchanged.
    assert "sr-only" in (labels[0].get("class") or "").split()
    # HTMX wiring is preserved.
    assert search_input.get("hx-get") == "/entities"
    assert search_input.get("placeholder")


@pytest.mark.unit
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


@pytest.mark.unit
def test_entity_edit_form_posts_to_web_route_not_json_api(
    client_with_entities: TestClient, fixture_entity: SimpleNamespace
) -> None:
    """The edit form submits to the HTML web route, never the typed JSON API.

    Posting form fields (with empty strings for blanks) to ``/api/v1/entities/{id}``
    via ``json-enc`` is what produced the 422-on-every-save bug, so the form must
    target the web layer and must not carry the ``json-enc`` extension.
    """
    response = client_with_entities.get(f"/entities/{fixture_entity.id}/edit")

    assert response.status_code == 200
    assert f'hx-patch="/entities/{fixture_entity.id}/edit"' in response.text
    assert "json-enc" not in response.text
    assert "/api/v1/entities" not in response.text


@pytest.mark.unit
def test_entity_edit_save_with_blank_optionals_returns_card_not_422(
    client_with_entities: TestClient, fixture_entity: SimpleNamespace
) -> None:
    """Saving the edit form with blank optional fields returns the detail card.

    Regression: ``json-enc`` serialized blank inputs as empty strings, which the
    typed ``EntityUpdate`` schema rejected (``formation_state`` min_length=2,
    ``formation_date`` as a ``date``), producing HTTP 422 on every save. The web
    save route must coerce blanks to "unset" and return the read-only HTML card so
    HTMX can swap ``#entity-card``.
    """
    response = client_with_entities.patch(
        f"/entities/{fixture_entity.id}/edit",
        data={
            "legal_name": "Acme Renamed LLC",
            "dba_names": "",
            "ein": "12-3456789",  # unchanged, so the uniqueness probe is skipped
            "entity_type": EntityType.LLC.value,  # template emits the lowercase value
            "formation_state": "",  # blank -> previously failed min_length=2
            "formation_date": "",  # blank -> previously failed date parsing
            "business_address": "",
            "purpose": "",
            "notes": "",
            # is_active checkbox unchecked -> omitted entirely by the browser
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    # The read-only detail card (its <dl> wrapper) is returned, not JSON.
    assert 'class="entity-fields"' in response.text
    # The updated legal name is reflected in the returned card.
    assert "Acme Renamed LLC" in response.text
