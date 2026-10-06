"""Read-only /api/v1/documents endpoints."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import ClauseElement

from llc_manager.core.config import settings
from llc_manager.db.session import get_async_session
from llc_manager.main import create_app
from llc_manager.models.document import Document, DocumentCategory, DocumentType
from tests.auth_helpers import AUTH_HEADERS
from tests.integration.test_entities_api import _FakeAsyncSession, _FakeResult

pytestmark = pytest.mark.unit

C2_FIELDS = {
    "id",
    "title",
    "category",
    "document_type",
    "entity_id",
    "document_date",
    "effective_date",
    "is_confidential",
    "consent_on_file",
    "sha256",
    "mime_type",
    "created_at",
    "updated_at",
}


class _RecordingSession(_FakeAsyncSession):
    def __init__(self, results: list[_FakeResult]) -> None:
        super().__init__(results)
        self.sql: list[str] = []

    async def execute(self, query: object) -> _FakeResult:
        assert isinstance(query, ClauseElement)
        self.sql.append(
            str(
                query.compile(
                    dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
                )
            )
        )
        return await super().execute(query)


def _doc(**overrides: Any) -> Document:
    now = datetime(2026, 9, 28, 14, 2, 11, tzinfo=UTC)
    fields: dict[str, Any] = {
        "id": uuid4(),
        "entity_id": uuid4(),
        "document_type": DocumentType.OPERATING_AGREEMENT,
        "category": DocumentCategory.LLCS,
        "title": "Operating Agreement",
        "document_date": date(2024, 5, 1),
        "effective_date": date(2024, 5, 1),
        "is_confidential": False,
        "consent_on_file": False,
        "sha256": "0" * 64,
        "mime_type": "application/pdf",
        "file_size": 8,
        "file_path": "/somewhere/private/original.pdf",
    }
    fields.update(overrides)
    doc = Document(**fields)
    doc.created_at = doc.updated_at = now
    doc.deleted_at = None
    return doc


def _client(session: _FakeAsyncSession, **kwargs: Any) -> TestClient:
    app = create_app()

    async def _override() -> Any:
        yield session

    app.dependency_overrides[get_async_session] = _override
    return TestClient(app, headers=AUTH_HEADERS, **kwargs)


class TestList:
    def test_items_match_the_contract_and_hide_paths(self) -> None:
        doc = _doc()
        session = _RecordingSession([_FakeResult(scalar=1), _FakeResult(all_=[doc])])
        body = _client(session).get("/api/v1/documents").json()

        assert body["total"] == 1
        assert (body["page"], body["size"], body["pages"]) == (1, 50, 1)
        item = body["items"][0]
        assert set(item) >= C2_FIELDS
        assert "file_path" not in item
        assert item["category"] == "LLCs"
        assert item["document_type"] == "operating_agreement"
        assert item["document_date"] == "2024-05-01"
        assert "ORDER BY documents.updated_at, documents.id" in session.sql[-1]
        assert "documents.deleted_at IS NULL" in session.sql[-1]

    def test_pagination_offset_and_pages(self) -> None:
        session = _RecordingSession([_FakeResult(scalar=45), _FakeResult(all_=[])])
        body = _client(session).get("/api/v1/documents?page=3&size=20").json()
        assert (body["total"], body["page"], body["size"], body["pages"]) == (
            45,
            3,
            20,
            3,
        )
        assert "LIMIT 20 OFFSET 40" in session.sql[-1]

    def test_empty_list_reports_one_page(self) -> None:
        session = _RecordingSession([_FakeResult(scalar=0), _FakeResult(all_=[])])
        body = _client(session).get("/api/v1/documents").json()
        assert body == {"items": [], "total": 0, "page": 1, "size": 50, "pages": 1}

    @pytest.mark.parametrize("params", ["page=0", "size=0", "size=201", "page=x"])
    def test_bad_pagination_is_422(self, params: str) -> None:
        resp = _client(_FakeAsyncSession([])).get(f"/api/v1/documents?{params}")
        assert resp.status_code == 422

    def test_updated_since_with_zone(self) -> None:
        session = _RecordingSession([_FakeResult(scalar=0), _FakeResult(all_=[])])
        resp = _client(session).get(
            "/api/v1/documents", params={"updated_since": "2026-09-28T10:00:00-04:00"}
        )
        assert resp.status_code == 200
        assert "documents.updated_at >= '2026-09-28 10:00:00-04:00'" in session.sql[-1]

    def test_updated_since_without_zone_is_utc(self) -> None:
        session = _RecordingSession([_FakeResult(scalar=0), _FakeResult(all_=[])])
        _client(session).get(
            "/api/v1/documents", params={"updated_since": "2026-09-28T14:00:00"}
        )
        assert "documents.updated_at >= '2026-09-28 14:00:00+00:00'" in session.sql[-1]

    def test_updated_since_must_be_a_timestamp(self) -> None:
        resp = _client(_FakeAsyncSession([])).get(
            "/api/v1/documents", params={"updated_since": "yesterday"}
        )
        assert resp.status_code == 422

    def test_entity_and_category_filters(self) -> None:
        entity_id = uuid4()
        session = _RecordingSession([_FakeResult(scalar=0), _FakeResult(all_=[])])
        _client(session).get(
            "/api/v1/documents",
            params={"entity_id": str(entity_id), "category": "Tax Returns"},
        )
        assert f"documents.entity_id = '{entity_id}'" in session.sql[-1]
        assert "documents.category = 'TAX_RETURNS'" in session.sql[-1]


class TestDetail:
    def test_returns_metadata(self) -> None:
        doc = _doc(category=DocumentCategory.TAX_RETURNS, consent_on_file=True)
        session = _FakeAsyncSession([_FakeResult(scalar_one=doc)])
        body = _client(session).get(f"/api/v1/documents/{doc.id}").json()
        assert body["id"] == str(doc.id)
        assert body["category"] == "Tax Returns"
        assert body["consent_on_file"] is True

    def test_unknown_id_is_404(self) -> None:
        session = _FakeAsyncSession([_FakeResult(scalar_one=None)])
        resp = _client(session).get(f"/api/v1/documents/{uuid4()}")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Document not found"


class TestFile:
    @pytest.fixture
    def root(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        root = tmp_path / "docs"
        root.mkdir()
        monkeypatch.setattr(settings, "documents_root", root)
        return root

    def test_streams_identical_bytes_with_headers(self, root: Path) -> None:
        payload = b"%PDF-1.4\n" + bytes(range(256)) * 300
        doc = _doc(sha256=hashlib.sha256(payload).hexdigest())
        (root / f"{doc.id}.pdf").write_bytes(payload)
        session = _FakeAsyncSession([_FakeResult(scalar_one=doc)])

        resp = _client(session).get(f"/api/v1/documents/{doc.id}/file")

        assert resp.status_code == 200
        assert resp.content == payload
        assert hashlib.sha256(resp.content).hexdigest() == doc.sha256
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.headers["content-length"] == str(len(payload))
        assert resp.headers["x-content-type-options"] == "nosniff"

    def test_uses_stored_mime_type(self, root: Path) -> None:
        doc = _doc(mime_type="image/png")
        (root / f"{doc.id}.png").write_bytes(b"\x89PNG")
        session = _FakeAsyncSession([_FakeResult(scalar_one=doc)])
        resp = _client(session).get(f"/api/v1/documents/{doc.id}/file")
        assert resp.headers["content-type"] == "image/png"

    def test_ignores_database_file_path(self, root: Path, tmp_path: Path) -> None:
        elsewhere = tmp_path / "elsewhere.pdf"
        elsewhere.write_bytes(b"not served")
        doc = _doc(file_path=str(elsewhere))
        session = _FakeAsyncSession([_FakeResult(scalar_one=doc)])
        resp = _client(session).get(f"/api/v1/documents/{doc.id}/file")
        assert resp.status_code == 404

    def test_unknown_document_is_404(self, root: Path) -> None:
        session = _FakeAsyncSession([_FakeResult(scalar_one=None)])
        resp = _client(session).get(f"/api/v1/documents/{uuid4()}/file")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Document not found"

    def test_missing_file_is_404_without_path(self, root: Path) -> None:
        doc = _doc()
        session = _FakeAsyncSession([_FakeResult(scalar_one=doc)])
        resp = _client(session).get(f"/api/v1/documents/{doc.id}/file")
        assert resp.status_code == 404
        assert resp.json() == {"detail": "Document file not found"}
        assert str(root) not in resp.text

    def test_symlink_out_of_root_is_404(self, root: Path, tmp_path: Path) -> None:
        secret = tmp_path / "secret.txt"
        secret.write_text("top secret", encoding="utf-8")
        doc = _doc()
        (root / f"{doc.id}.pdf").symlink_to(secret)
        session = _FakeAsyncSession([_FakeResult(scalar_one=doc)])
        resp = _client(session).get(f"/api/v1/documents/{doc.id}/file")
        assert resp.status_code == 404
        assert "top secret" not in resp.text
        assert str(tmp_path) not in resp.text

    @pytest.mark.parametrize(
        "raw",
        [
            "..%2F..%2Fetc%2Fpasswd",
            "%2e%2e%2f%2e%2e%2fetc%2fpasswd",
            "..%5C..%5Cwindows",
            "not-a-uuid",
        ],
    )
    def test_traversal_strings_never_reach_the_filesystem(
        self, root: Path, raw: str
    ) -> None:
        session = _FakeAsyncSession([])
        resp = _client(session).get(f"/api/v1/documents/{raw}/file")
        assert resp.status_code in {404, 422}
        assert session.execute_count == 0
        assert "root:" not in resp.text

    def test_dot_dot_segments_do_not_escape_the_route(self, root: Path) -> None:
        session = _FakeAsyncSession([])
        resp = _client(session).get("/api/v1/documents/../../../etc/passwd")
        assert resp.status_code in {401, 404}
        assert "root:" not in resp.text


def test_requires_key_for_file() -> None:
    app = create_app()
    client = TestClient(app)
    resp = client.get(f"/api/v1/documents/{UUID(int=1)}/file")
    assert resp.status_code == 401
