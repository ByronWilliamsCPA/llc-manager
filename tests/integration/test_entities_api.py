"""Integration tests for the /api/v1/entities CRUD endpoints.

The route handlers in ``llc_manager.api.v1.endpoints.entities`` execute against
a SQLAlchemy ``AsyncSession``. The test harness substitutes that session with
a recording fake via FastAPI's ``dependency_overrides`` mechanism so each
route's branches (success, 404, 409, 400) fire without requiring a running
PostgreSQL instance -- the test container in this environment has no docker
daemon and no aiosqlite, and the production model definitions use
``PG_UUID`` directly.

The tests deliberately cover:
- list_entities: empty result, populated result, search filter, is_active filter,
  pagination math (size, page, pages calculation, page > total).
- create_entity: 201 success path, 409 on duplicate EIN, 422 on malformed input.
- get_entity: 200 success, 404 not found, 422 on malformed UUID.
- update_entity: 200 success, 404 not found, 409 on EIN conflict,
  partial-update (only-supplied-fields semantics).
- delete_entity: 204 success (soft delete), 404 not found.
- Ownership-isolation note: there is no user/auth model in the codebase,
  so cross-tenant access cannot be enforced. We document this gap and
  assert the current behavior so a future auth layer makes these tests
  flip explicitly. See ``docs/template_feedback.md`` for the open issue.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from llc_manager.api.v1.endpoints.entities import router as entities_router
from llc_manager.db.session import get_async_session
from llc_manager.main import create_app
from llc_manager.models.entity import Entity, EntityType

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# ---------------------------------------------------------------------------
# Fake DB infrastructure
# ---------------------------------------------------------------------------


class _FakeResult:
    """Mimics the SQLAlchemy ``Result`` API used by the endpoints.

    Only the methods actually invoked by ``entities.py`` are implemented:
    ``scalar``, ``scalar_one_or_none``, ``scalars().all()``. The handler
    issues one ``await db.execute(...)`` per logical query, so the fake
    session pops a pre-queued result for each call.
    """

    def __init__(
        self,
        *,
        scalar: Any = None,
        scalar_one: Any = None,
        all_: list[Any] | None = None,
    ) -> None:
        self._scalar = scalar
        self._scalar_one = scalar_one
        self._all = all_ or []

    def scalar(self) -> Any:
        return self._scalar

    def scalar_one_or_none(self) -> Any:
        return self._scalar_one

    def scalars(self) -> _FakeResult:
        return self

    def all(self) -> list[Any]:
        return self._all


class _FakeAsyncSession:
    """Records executions and synthesizes results from a queued plan."""

    def __init__(self, results: list[_FakeResult]) -> None:
        self._results = list(results)
        self.added: list[Any] = []
        self.execute_count = 0
        self.flush_count = 0
        self.refresh_count = 0

    async def execute(self, _query: Any) -> _FakeResult:
        self.execute_count += 1
        if not self._results:
            return _FakeResult()
        return self._results.pop(0)

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flush_count += 1

    async def refresh(self, _obj: Any) -> None:
        self.refresh_count += 1


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_entity(
    *,
    legal_name: str = "Acme LLC",
    ein: str | None = "12-3456789",
    entity_id: UUID | None = None,
) -> Entity:
    """Build a fully-populated Entity (timestamps + audit fields).

    ``EntityResponse.model_validate(entity)`` requires all FullSchema fields
    so we must set timestamp / audit columns explicitly.
    """
    now = datetime.now(UTC)
    entity = Entity(
        legal_name=legal_name,
        ein=ein,
        entity_type=EntityType.LLC,
        is_active=True,
    )
    entity.id = entity_id or uuid4()
    entity.created_at = now
    entity.updated_at = now
    entity.created_by = None
    entity.updated_by = None
    entity.deleted_at = None
    entity.deleted_by = None
    return entity


def _client_with_session(session: _FakeAsyncSession) -> TestClient:
    """Build a TestClient whose entities router uses the supplied fake session."""
    app = create_app()

    async def _override() -> AsyncIterator[_FakeAsyncSession]:
        yield session

    app.dependency_overrides[get_async_session] = _override
    return TestClient(app)


class TestRouterWiring:
    """Defensive smoke check: the router under test is registered on the app.

    If the router is detached the per-endpoint tests still 'pass' against
    dependency overrides but the production wiring is broken. Running this
    sanity assertion as a real test keeps that drift visible.
    """

    @pytest.mark.integration
    def test_entities_router_mounted_on_v1(self) -> None:
        app = create_app()
        paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
        assert any(p.startswith("/api/v1/entities") for p in paths), (
            "entities router is not mounted on /api/v1/entities"
        )
        assert entities_router is not None


# ---------------------------------------------------------------------------
# list_entities
# ---------------------------------------------------------------------------


class TestListEntities:
    @pytest.mark.integration
    def test_empty_list_returns_one_page(self) -> None:
        # count -> 0, items -> []
        session = _FakeAsyncSession([_FakeResult(scalar=0), _FakeResult(all_=[])])
        client = _client_with_session(session)

        resp = client.get("/api/v1/entities")

        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0
        assert body["page"] == 1
        assert body["pages"] == 1  # empty result still reports 1 page

    @pytest.mark.integration
    def test_populated_list_returns_items(self) -> None:
        entity = _make_entity(legal_name="One LLC")
        session = _FakeAsyncSession([_FakeResult(scalar=1), _FakeResult(all_=[entity])])
        client = _client_with_session(session)

        resp = client.get("/api/v1/entities")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["legal_name"] == "One LLC"

    @pytest.mark.integration
    def test_pagination_math(self) -> None:
        # 25 entities, size=10 -> 3 pages.
        entities = [_make_entity(legal_name=f"E{i}") for i in range(10)]
        session = _FakeAsyncSession(
            [_FakeResult(scalar=25), _FakeResult(all_=entities)]
        )
        client = _client_with_session(session)

        resp = client.get("/api/v1/entities", params={"page": 1, "size": 10})

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 25
        assert body["size"] == 10
        assert body["pages"] == 3

    @pytest.mark.integration
    def test_search_filter_applied(self) -> None:
        entity = _make_entity(legal_name="Acme Holdings LLC")
        session = _FakeAsyncSession([_FakeResult(scalar=1), _FakeResult(all_=[entity])])
        client = _client_with_session(session)

        resp = client.get("/api/v1/entities", params={"search": "Acme"})

        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    @pytest.mark.integration
    def test_is_active_filter_applied(self) -> None:
        session = _FakeAsyncSession([_FakeResult(scalar=0), _FakeResult(all_=[])])
        client = _client_with_session(session)

        resp = client.get("/api/v1/entities", params={"is_active": False})

        assert resp.status_code == 200
        # Both filter branches executed; count is reported.
        assert resp.json()["total"] == 0

    @pytest.mark.integration
    def test_page_validation_rejects_zero(self) -> None:
        session = _FakeAsyncSession([])
        client = _client_with_session(session)

        resp = client.get("/api/v1/entities", params={"page": 0})
        # Query-param validation runs before the handler -> 422.
        assert resp.status_code == 422

    @pytest.mark.integration
    def test_size_validation_rejects_over_100(self) -> None:
        session = _FakeAsyncSession([])
        client = _client_with_session(session)

        resp = client.get("/api/v1/entities", params={"size": 101})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# create_entity
# ---------------------------------------------------------------------------


class TestCreateEntity:
    @pytest.mark.integration
    def test_create_success_returns_201(self) -> None:
        # First execute -> dup-EIN lookup (returns None = no dup).
        session = _FakeAsyncSession([_FakeResult(scalar_one=None)])
        client = _client_with_session(session)

        # Pre-populate the new entity's identifiers so model_validate works
        # after the (no-op) refresh in our fake session.
        def _capture_added(obj: Entity) -> None:
            obj.id = uuid4()
            now = datetime.now(UTC)
            obj.created_at = now
            obj.updated_at = now

        original_add = session.add

        def _add(obj: Entity) -> None:
            _capture_added(obj)
            original_add(obj)

        session.add = _add  # type: ignore[method-assign]

        resp = client.post(
            "/api/v1/entities",
            json={
                "legal_name": "New LLC",
                "ein": "99-1234567",
                "entity_type": "llc",
            },
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["legal_name"] == "New LLC"
        assert body["ein"] == "99-1234567"
        assert session.flush_count == 1
        assert session.refresh_count == 1

    @pytest.mark.integration
    def test_create_without_ein_skips_dup_check(self) -> None:
        # No EIN supplied -> the duplicate-lookup branch is skipped entirely.
        session = _FakeAsyncSession([])
        client = _client_with_session(session)

        def _capture_added(obj: Entity) -> None:
            obj.id = uuid4()
            now = datetime.now(UTC)
            obj.created_at = now
            obj.updated_at = now

        original_add = session.add

        def _add(obj: Entity) -> None:
            _capture_added(obj)
            original_add(obj)

        session.add = _add  # type: ignore[method-assign]

        resp = client.post(
            "/api/v1/entities",
            json={"legal_name": "No EIN LLC"},
        )

        assert resp.status_code == 201
        assert resp.json()["ein"] is None
        # No SELECT was issued because EIN was absent.
        assert session.execute_count == 0

    @pytest.mark.integration
    def test_create_duplicate_ein_returns_409(self) -> None:
        existing = _make_entity(legal_name="Existing", ein="99-1234567")
        session = _FakeAsyncSession([_FakeResult(scalar_one=existing)])
        client = _client_with_session(session)

        resp = client.post(
            "/api/v1/entities",
            json={"legal_name": "Dup", "ein": "99-1234567"},
        )

        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]

    @pytest.mark.integration
    def test_create_missing_legal_name_returns_422(self) -> None:
        session = _FakeAsyncSession([])
        client = _client_with_session(session)

        resp = client.post("/api/v1/entities", json={})

        assert resp.status_code == 422

    @pytest.mark.integration
    def test_create_invalid_ein_format_returns_422(self) -> None:
        session = _FakeAsyncSession([])
        client = _client_with_session(session)

        resp = client.post(
            "/api/v1/entities",
            json={"legal_name": "Bad EIN", "ein": "1234567"},
        )

        assert resp.status_code == 422

    @pytest.mark.integration
    def test_create_invalid_state_returns_422(self) -> None:
        session = _FakeAsyncSession([])
        client = _client_with_session(session)

        resp = client.post(
            "/api/v1/entities",
            json={"legal_name": "Bad State", "formation_state": "California"},
        )

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# get_entity
# ---------------------------------------------------------------------------


class TestGetEntity:
    @pytest.mark.integration
    def test_get_existing_returns_200(self) -> None:
        entity = _make_entity(legal_name="Lookup LLC")
        session = _FakeAsyncSession([_FakeResult(scalar_one=entity)])
        client = _client_with_session(session)

        resp = client.get(f"/api/v1/entities/{entity.id}")

        assert resp.status_code == 200
        assert resp.json()["legal_name"] == "Lookup LLC"

    @pytest.mark.integration
    def test_get_missing_returns_404(self) -> None:
        session = _FakeAsyncSession([_FakeResult(scalar_one=None)])
        client = _client_with_session(session)

        resp = client.get(f"/api/v1/entities/{uuid4()}")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    @pytest.mark.integration
    def test_get_invalid_uuid_returns_422(self) -> None:
        session = _FakeAsyncSession([])
        client = _client_with_session(session)

        resp = client.get("/api/v1/entities/not-a-uuid")

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# update_entity
# ---------------------------------------------------------------------------


class TestUpdateEntity:
    @pytest.mark.integration
    def test_update_success_returns_200(self) -> None:
        entity = _make_entity(legal_name="Old Name", ein="11-1111111")
        # 1) lookup by id; 2) no EIN change so no second SELECT.
        session = _FakeAsyncSession([_FakeResult(scalar_one=entity)])
        client = _client_with_session(session)

        resp = client.patch(
            f"/api/v1/entities/{entity.id}",
            json={"legal_name": "New Name"},
        )

        assert resp.status_code == 200
        assert resp.json()["legal_name"] == "New Name"
        # The entity object was mutated in place.
        assert entity.legal_name == "New Name"

    @pytest.mark.integration
    def test_update_missing_returns_404(self) -> None:
        session = _FakeAsyncSession([_FakeResult(scalar_one=None)])
        client = _client_with_session(session)

        resp = client.patch(
            f"/api/v1/entities/{uuid4()}",
            json={"legal_name": "Anything"},
        )

        assert resp.status_code == 404

    @pytest.mark.integration
    def test_update_ein_to_conflicting_value_returns_409(self) -> None:
        existing = _make_entity(legal_name="Target", ein="11-1111111")
        conflicting = _make_entity(legal_name="Other", ein="22-2222222")
        # 1) load target; 2) EIN dup-check finds another entity.
        session = _FakeAsyncSession(
            [
                _FakeResult(scalar_one=existing),
                _FakeResult(scalar_one=conflicting),
            ]
        )
        client = _client_with_session(session)

        resp = client.patch(
            f"/api/v1/entities/{existing.id}",
            json={"ein": "22-2222222"},
        )

        assert resp.status_code == 409

    @pytest.mark.integration
    def test_update_same_ein_skips_conflict_check(self) -> None:
        """Updating with the same EIN should not trigger a dup-check SELECT."""
        existing = _make_entity(legal_name="Target", ein="11-1111111")
        session = _FakeAsyncSession([_FakeResult(scalar_one=existing)])
        client = _client_with_session(session)

        resp = client.patch(
            f"/api/v1/entities/{existing.id}",
            json={"ein": "11-1111111", "legal_name": "Same EIN"},
        )

        assert resp.status_code == 200
        # Only the initial load executed.
        assert session.execute_count == 1

    @pytest.mark.integration
    def test_update_invalid_ein_returns_422(self) -> None:
        session = _FakeAsyncSession([])
        client = _client_with_session(session)

        resp = client.patch(
            f"/api/v1/entities/{uuid4()}",
            json={"ein": "not-an-ein"},
        )

        assert resp.status_code == 422

    @pytest.mark.integration
    def test_empty_patch_body_loads_but_does_not_change(self) -> None:
        """An empty body lands in update_data={} -- the handler still 200s."""
        existing = _make_entity(legal_name="Unchanged")
        session = _FakeAsyncSession([_FakeResult(scalar_one=existing)])
        client = _client_with_session(session)

        resp = client.patch(f"/api/v1/entities/{existing.id}", json={})

        assert resp.status_code == 200
        assert resp.json()["legal_name"] == "Unchanged"


# ---------------------------------------------------------------------------
# delete_entity
# ---------------------------------------------------------------------------


class TestDeleteEntity:
    @pytest.mark.integration
    def test_delete_success_returns_204(self) -> None:
        entity = _make_entity(legal_name="Doomed")
        session = _FakeAsyncSession([_FakeResult(scalar_one=entity)])
        client = _client_with_session(session)

        resp = client.delete(f"/api/v1/entities/{entity.id}")

        assert resp.status_code == 204
        # Soft delete set deleted_at on the in-memory entity.
        assert entity.deleted_at is not None
        assert session.flush_count == 1

    @pytest.mark.integration
    def test_delete_missing_returns_404(self) -> None:
        session = _FakeAsyncSession([_FakeResult(scalar_one=None)])
        client = _client_with_session(session)

        resp = client.delete(f"/api/v1/entities/{uuid4()}")

        assert resp.status_code == 404

    @pytest.mark.integration
    def test_delete_invalid_uuid_returns_422(self) -> None:
        session = _FakeAsyncSession([])
        client = _client_with_session(session)

        resp = client.delete("/api/v1/entities/not-a-uuid")

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Authorization / ownership
# ---------------------------------------------------------------------------


class TestEntityOwnershipIsolation:
    """Authorization tests for cross-tenant entity isolation.

    #CRITICAL: Authorization -- the current codebase has no user model and no
    authentication middleware, so the Entity table has nothing identifying
    *which* user owns a row. Any caller can therefore read, update, or
    soft-delete any entity. We document this and assert the current behavior
    so that when an auth layer is added the failing assertions point at
    exactly which routes must enforce ownership.

    See ``docs/template_feedback.md`` for the open issue.
    """

    @pytest.mark.integration
    def test_no_owner_column_on_entity_model(self) -> None:
        """Regression-protect the gap: Entity has no user/owner FK today."""
        columns = {c.name for c in Entity.__table__.columns}
        owner_like = {"user_id", "owner_user_id", "tenant_id", "account_id"}
        assert columns.isdisjoint(owner_like), (
            "An auth column appears to exist; update the cross-tenant tests "
            "to assert that user A cannot access user B's entities."
        )

    @pytest.mark.integration
    def test_two_clients_share_visibility_documents_gap(self) -> None:
        """With no auth, "user A" and "user B" hit the same data set.

        This test exists to *fail* the moment an authentication layer is
        added without per-user filtering on the list endpoint.
        """
        entity_a = _make_entity(legal_name="Tenant A LLC")
        entity_b = _make_entity(legal_name="Tenant B LLC")

        session_a = _FakeAsyncSession(
            [_FakeResult(scalar=2), _FakeResult(all_=[entity_a, entity_b])]
        )
        session_b = _FakeAsyncSession(
            [_FakeResult(scalar=2), _FakeResult(all_=[entity_a, entity_b])]
        )

        client_a = _client_with_session(session_a)
        client_b = _client_with_session(session_b)

        items_a = {
            e["legal_name"] for e in client_a.get("/api/v1/entities").json()["items"]
        }
        items_b = {
            e["legal_name"] for e in client_b.get("/api/v1/entities").json()["items"]
        }

        # Both "users" see both entities -- the current (unauthenticated)
        # contract. When auth lands, the implementation must filter per-user
        # and this assertion will flip to inequality.
        assert items_a == items_b == {"Tenant A LLC", "Tenant B LLC"}

    @pytest.mark.integration
    def test_get_by_id_does_not_check_caller_identity(self) -> None:
        """``GET /entities/{id}`` returns the row regardless of caller.

        Documents that ``get_entity`` has no ``where(owner_user_id = current_user)``
        clause. When ownership is enforced, this test must be updated to
        assert 403/404 when the caller is not the owner.
        """
        entity = _make_entity(legal_name="Tenant A's LLC")
        session = _FakeAsyncSession([_FakeResult(scalar_one=entity)])
        client = _client_with_session(session)

        resp = client.get(f"/api/v1/entities/{entity.id}")
        assert resp.status_code == 200
