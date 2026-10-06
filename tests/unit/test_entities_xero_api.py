"""Entity API: individual and household types, Xero mapping fields, filters."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import ClauseElement

from llc_manager.models.bank_account import AccountType, BankAccount
from llc_manager.models.entity import EntityType
from tests.integration.test_entities_api import (
    _client_with_session,
    _FakeAsyncSession,
    _FakeResult,
    _make_entity,
)

pytestmark = pytest.mark.unit


class _StampingSession(_FakeAsyncSession):
    """Fake session that stamps id and timestamps on add, as the DB would."""

    def add(self, obj: Any) -> None:
        obj.id = uuid4()
        obj.created_at = obj.updated_at = datetime.now(UTC)
        super().add(obj)


class _RecordingSession(_FakeAsyncSession):
    """Fake session that also keeps the compiled SQL of each query."""

    def __init__(self, results: list[_FakeResult]) -> None:
        super().__init__(results)
        self.sql: list[str] = []

    async def execute(self, query: object) -> _FakeResult:
        assert isinstance(query, ClauseElement)
        compiled = query.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
        self.sql.append(str(compiled))
        return await super().execute(query)


def test_response_carries_xero_tenant_and_bank_account_refs() -> None:
    entity = _make_entity(legal_name="Biz LLC")
    entity.xero_tenant_id = "tenant-1"
    account = BankAccount(
        id=uuid4(),
        entity_id=entity.id,
        bank_name="Example Bank",
        account_type=AccountType.BUSINESS_CHECKING,
        account_nickname="Operating",
        account_number_last4="1234",
        routing_number="000000000",
        xero_account_id="acct-1",
        is_active=True,
    )
    entity.bank_accounts = [account]
    client = _client_with_session(_FakeAsyncSession([_FakeResult(scalar_one=entity)]))

    body = client.get(f"/api/v1/entities/{entity.id}").json()

    assert body["xero_tenant_id"] == "tenant-1"
    assert body["bank_accounts"] == [
        {
            "id": str(account.id),
            "account_nickname": "Operating",
            "account_number_last4": "1234",
            "xero_account_id": "acct-1",
            "is_active": True,
        }
    ]
    assert "routing_number" not in body["bank_accounts"][0]


@pytest.mark.parametrize("entity_type", [EntityType.INDIVIDUAL, EntityType.HOUSEHOLD])
def test_create_individual_and_household(entity_type: EntityType) -> None:
    session = _StampingSession([])
    client = _client_with_session(session)

    resp = client.post(
        "/api/v1/entities",
        json={"legal_name": "Example", "entity_type": entity_type.value},
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["entity_type"] == entity_type.value
    assert session.added[0].entity_type is entity_type


def test_list_filters_by_type_and_tenant() -> None:
    session = _RecordingSession([_FakeResult(scalar=0), _FakeResult(all_=[])])
    client = _client_with_session(session)

    resp = client.get(
        "/api/v1/entities",
        params={"entity_type": "household", "xero_tenant_id": "tenant-9"},
    )

    assert resp.status_code == 200
    assert "entities.entity_type = 'HOUSEHOLD'" in session.sql[-1]
    assert "entities.xero_tenant_id = 'tenant-9'" in session.sql[-1]


def test_list_rejects_unknown_entity_type() -> None:
    client = _client_with_session(_FakeAsyncSession([]))
    assert (
        client.get("/api/v1/entities", params={"entity_type": "nope"}).status_code
        == 422
    )


def test_create_with_taken_tenant_returns_409() -> None:
    other = _make_entity(legal_name="Other", ein=None)
    session = _FakeAsyncSession([_FakeResult(scalar_one=other)])
    client = _client_with_session(session)

    resp = client.post(
        "/api/v1/entities",
        json={"legal_name": "New", "entity_type": "llc", "xero_tenant_id": "tenant-1"},
    )

    assert resp.status_code == 409
    assert "Xero tenant" in resp.json()["detail"]
    assert session.added == []


def test_create_with_free_tenant_succeeds() -> None:
    session = _StampingSession([_FakeResult(scalar_one=None)])
    client = _client_with_session(session)

    resp = client.post(
        "/api/v1/entities",
        json={"legal_name": "New", "entity_type": "llc", "xero_tenant_id": "tenant-1"},
    )

    assert resp.status_code == 201
    assert session.added[0].xero_tenant_id == "tenant-1"


def test_update_to_taken_tenant_returns_409() -> None:
    entity = _make_entity(legal_name="Mine", ein=None)
    other = _make_entity(legal_name="Other", ein=None)
    session = _RecordingSession(
        [_FakeResult(scalar_one=entity), _FakeResult(scalar_one=other)]
    )
    client = _client_with_session(session)

    resp = client.patch(f"/api/v1/entities/{entity.id}", json={"xero_tenant_id": "t-2"})

    assert resp.status_code == 409
    assert "entities.id !=" in session.sql[-1]


def test_update_same_tenant_skips_conflict_check() -> None:
    entity = _make_entity(legal_name="Mine", ein=None)
    entity.xero_tenant_id = "t-1"
    session = _FakeAsyncSession([_FakeResult(scalar_one=entity)])
    client = _client_with_session(session)

    resp = client.patch(f"/api/v1/entities/{entity.id}", json={"xero_tenant_id": "t-1"})

    assert resp.status_code == 200
    assert session.execute_count == 1
