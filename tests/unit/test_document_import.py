"""Unit tests for the manifest-driven document import service."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.sql import ClauseElement

from llc_manager.models.document import Document, DocumentCategory, DocumentType
from llc_manager.services.document_import import (
    ImportProblemError,
    ManifestRow,
    SqlDocumentRepository,
    apply_import,
    document_id_for,
    load_entity_map,
    read_manifest,
    sha256_file,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.unit

HEADER = (
    "file,entity,document_type,category,title,document_date,effective_date,"
    "confidential,consent_on_file\n"
)
SENTINEL_TITLE = "Zyxwv Sentinel Title"
HOUSEHOLD = uuid4()
PERSON = uuid4()


class InMemoryRepo:
    """In-memory :class:`DocumentRepository` for tests."""

    def __init__(self, entities: set[UUID] | None = None) -> None:
        self.entities = {HOUSEHOLD, PERSON} if entities is None else entities
        self.docs: dict[UUID, Document] = {}
        self.flushes = 0

    async def live_entity_ids(self, ids: set[UUID]) -> set[UUID]:
        return ids & self.entities

    async def get(self, document_id: UUID) -> Document | None:
        return self.docs.get(document_id)

    async def live_id_with_sha(self, sha256: str) -> UUID | None:
        for doc in self.docs.values():
            if doc.sha256 == sha256 and doc.deleted_at is None:
                return doc.id
        return None

    def add(self, document: Document) -> None:
        document.deleted_at = None
        self.docs[document.id] = document

    async def flush(self) -> None:
        self.flushes += 1


def _files(root: Path, **contents: bytes) -> None:
    for name, data in contents.items():
        (root / name).write_bytes(data)


def _manifest(root: Path, *lines: str) -> Path:
    path = root / "manifest.csv"
    path.write_text(HEADER + "".join(f"{line}\n" for line in lines), "utf-8")
    return path


def _entity_map() -> dict[str, UUID]:
    return {"household": HOUSEHOLD, "person-a": PERSON}


def _rows(root: Path, *lines: str) -> list[ManifestRow]:
    report = read_manifest(_manifest(root, *lines), root, _entity_map())
    assert report.problems == []
    return report.rows


# ---------------------------------------------------------------------------
# read_manifest
# ---------------------------------------------------------------------------


def test_reads_valid_rows(tmp_path: Path) -> None:
    _files(tmp_path, **{"a.pdf": b"A", "b.png": b"B"})
    rows = _rows(
        tmp_path,
        f"a.pdf,household,insurance_policy,insurance,{SENTINEL_TITLE},"
        "2025-01-02,2025-02-03,yes,",
        f"b.png,{PERSON},tax_return,Tax Returns,T,,,0,true",
    )
    first, second = rows
    assert first.entity_id == HOUSEHOLD
    assert first.category is DocumentCategory.INSURANCE
    assert first.document_type is DocumentType.INSURANCE_POLICY
    assert first.document_date == date(2025, 1, 2)
    assert first.effective_date == date(2025, 2, 3)
    assert first.is_confidential is True
    assert first.consent_on_file is False
    assert first.mime_type == "application/pdf"
    assert first.document_id == document_id_for("a.pdf")
    assert second.entity_id == PERSON
    assert second.mime_type == "image/png"
    assert second.consent_on_file is True
    assert second.document_date is None


def test_document_id_is_stable_and_path_based() -> None:
    assert document_id_for("x/a.pdf") == document_id_for("x/a.pdf")
    assert document_id_for("x/a.pdf") != document_id_for("x/b.pdf")


def test_absolute_path_outside_source_root(tmp_path: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    src = tmp_path / "src"
    src.mkdir()
    _files(other, **{"a.pdf": b"A"})
    report = read_manifest(
        _manifest(src, f"{other / 'a.pdf'},household,will,Estate Planning,T,,,,"),
        src,
        _entity_map(),
    )
    assert report.problems == []
    assert report.rows[0].document_id == document_id_for(
        (other / "a.pdf").resolve().as_posix()
    )


def test_header_problems(tmp_path: Path) -> None:
    path = tmp_path / "m.csv"
    path.write_text("file,entity,extra\n", "utf-8")
    report = read_manifest(path, tmp_path)
    assert "header: missing column 'title'" in report.problems
    assert "header: unknown column 'extra'" in report.problems
    assert report.rows == []


def test_unreadable_manifest(tmp_path: Path) -> None:
    report = read_manifest(tmp_path / "missing.csv", tmp_path)
    assert report.problems == ["manifest could not be read"]


def test_empty_manifest(tmp_path: Path) -> None:
    report = read_manifest(_manifest(tmp_path), tmp_path)
    assert report.problems == ["manifest has no rows"]


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (",household,will,Other,T,,,,", "column 'file': empty"),
        ("nope.pdf,household,will,Other,T,,,,", "column 'file': file not found"),
        ("a.doc,household,will,Other,T,,,,", "unsupported file type"),
        ("a.pdf,someone,will,Other,T,,,,", "column 'entity'"),
        ("a.pdf,household,napkin,Other,T,,,,", "column 'document_type'"),
        ("a.pdf,household,will,Recipes,T,,,,", "column 'category'"),
        ("a.pdf,household,will,Other,,,,,", "column 'title'"),
        ("a.pdf,household,will,Other,T,2025-13-01,,,", "column 'document_date'"),
        ("a.pdf,household,will,Other,T,,soon,,", "column 'effective_date'"),
        ("a.pdf,household,will,Other,T,,,maybe,", "column 'confidential'"),
        ("a.pdf,household,will,Other,T,,,,true", "only valid for the Tax Returns"),
    ],
)
def test_row_problems_name_line_and_column(
    tmp_path: Path, line: str, expected: str
) -> None:
    _files(tmp_path, **{"a.pdf": b"A", "a.doc": b"D"})
    report = read_manifest(_manifest(tmp_path, line), tmp_path, _entity_map())
    assert len(report.problems) == 1
    assert report.problems[0].startswith("line 2: ")
    assert expected in report.problems[0]
    assert report.rows == []


def test_title_too_long(tmp_path: Path) -> None:
    _files(tmp_path, **{"a.pdf": b"A"})
    line = f"a.pdf,household,will,Other,{'x' * 256},,,,"
    report = read_manifest(_manifest(tmp_path, line), tmp_path, _entity_map())
    assert "column 'title'" in report.problems[0]


def test_same_file_twice_is_a_problem(tmp_path: Path) -> None:
    _files(tmp_path, **{"a.pdf": b"A"})
    report = read_manifest(
        _manifest(
            tmp_path,
            "a.pdf,household,will,Other,T,,,,",
            "./a.pdf,household,will,Other,T2,,,,",
        ),
        tmp_path,
        _entity_map(),
    )
    assert report.problems == ["line 3: column 'file': same file as line 2"]
    assert len(report.rows) == 1


def test_problems_never_contain_values(tmp_path: Path) -> None:
    _files(tmp_path, **{"a.pdf": b"A"})
    report = read_manifest(
        _manifest(
            tmp_path,
            f"secret-dir/{SENTINEL_TITLE}.pdf,household,will,Other,T,,,,",
            f"a.pdf,{SENTINEL_TITLE},will,Other,{SENTINEL_TITLE},,,,",
        ),
        tmp_path,
        _entity_map(),
    )
    assert len(report.problems) == 2
    assert all(SENTINEL_TITLE not in p for p in report.problems)
    assert all("secret-dir" not in p for p in report.problems)


# ---------------------------------------------------------------------------
# load_entity_map
# ---------------------------------------------------------------------------


def test_load_entity_map(tmp_path: Path) -> None:
    path = tmp_path / "map.json"
    path.write_text(
        json.dumps({"entities": {"household": {"id": str(HOUSEHOLD)}}}), "utf-8"
    )
    assert load_entity_map(path) == {"household": HOUSEHOLD}


@pytest.mark.parametrize("content", ["not json", '{"x": 1}', '{"entities": {"a": 1}}'])
def test_load_entity_map_malformed(tmp_path: Path, content: str) -> None:
    path = tmp_path / "map.json"
    path.write_text(content, "utf-8")
    with pytest.raises(ImportProblemError) as exc:
        load_entity_map(path)
    assert exc.value.problems == ["entity map is missing or malformed"]


# ---------------------------------------------------------------------------
# apply_import
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_twice_creates_once(tmp_path: Path) -> None:
    src = tmp_path / "src"
    store = tmp_path / "store"
    src.mkdir()
    _files(src, **{"a.pdf": b"AAA", "b.pdf": b"BBB"})
    rows = _rows(
        src,
        "a.pdf,household,insurance_policy,Insurance,House policy,,,,",
        "b.pdf,person-a,will,Estate Planning,Will,,,true,",
    )
    repo = InMemoryRepo()

    first = await apply_import(repo, rows, store)
    second = await apply_import(repo, rows, store)

    assert (first.created, first.unchanged) == (2, 0)
    assert (second.created, second.updated, second.unchanged) == (0, 0, 2)
    assert len(repo.docs) == 2
    doc = repo.docs[document_id_for("a.pdf")]
    assert doc.sha256 == sha256_file(src / "a.pdf")
    assert doc.file_size == 3
    assert doc.entity_id == HOUSEHOLD
    stored = store / f"{doc.id}.pdf"
    assert stored.read_bytes() == b"AAA"
    assert stored.stat().st_mode & 0o777 == 0o640
    assert doc.file_path == stored.name
    assert not list(store.glob(".*.tmp"))


@pytest.mark.asyncio
async def test_changed_file_updates_sha_and_store(tmp_path: Path) -> None:
    _files(tmp_path, **{"a.pdf": b"v1"})
    store = tmp_path / "store"
    line = "a.pdf,household,will,Other,T,,,,"
    repo = InMemoryRepo()
    await apply_import(repo, _rows(tmp_path, line), store)
    doc = repo.docs[document_id_for("a.pdf")]
    old_sha = doc.sha256

    _files(tmp_path, **{"a.pdf": b"version two"})
    result = await apply_import(repo, _rows(tmp_path, line), store)

    assert result.updated == 1
    assert doc.sha256 != old_sha
    assert doc.file_size == len(b"version two")
    assert (store / f"{doc.id}.pdf").read_bytes() == b"version two"


@pytest.mark.asyncio
async def test_metadata_change_updates_without_copy(tmp_path: Path) -> None:
    _files(tmp_path, **{"a.pdf": b"v1"})
    store = tmp_path / "store"
    repo = InMemoryRepo()
    await apply_import(
        repo, _rows(tmp_path, "a.pdf,household,will,Other,Old,,,,"), store
    )
    result = await apply_import(
        repo, _rows(tmp_path, "a.pdf,person-a,will,Trusts,New,,,,"), store
    )
    doc = repo.docs[document_id_for("a.pdf")]
    assert result.updated == 1
    assert (doc.title, doc.entity_id, doc.category) == (
        "New",
        PERSON,
        DocumentCategory.TRUSTS,
    )


@pytest.mark.asyncio
async def test_missing_stored_file_is_restored(tmp_path: Path) -> None:
    _files(tmp_path, **{"a.pdf": b"v1"})
    store = tmp_path / "store"
    line = "a.pdf,household,will,Other,T,,,,"
    repo = InMemoryRepo()
    await apply_import(repo, _rows(tmp_path, line), store)
    stored = store / f"{document_id_for('a.pdf')}.pdf"
    stored.unlink()

    result = await apply_import(repo, _rows(tmp_path, line), store)

    assert result.unchanged == 1
    assert stored.read_bytes() == b"v1"


@pytest.mark.asyncio
async def test_exact_duplicates_are_skipped(tmp_path: Path) -> None:
    _files(tmp_path, **{"a.pdf": b"same", "copy.pdf": b"same"})
    store = tmp_path / "store"
    repo = InMemoryRepo()
    result = await apply_import(
        repo,
        _rows(
            tmp_path,
            "a.pdf,household,will,Other,T,,,,",
            "copy.pdf,household,will,Other,T,,,,",
        ),
        store,
    )
    assert (result.created, result.duplicates) == (1, 1)
    assert len(list(store.iterdir())) == 1

    _files(tmp_path, **{"later.pdf": b"same"})
    again = await apply_import(
        repo, _rows(tmp_path, "later.pdf,household,will,Other,T,,,,"), store
    )
    assert again.duplicates == 1


@pytest.mark.asyncio
async def test_soft_deleted_documents_are_left_alone(tmp_path: Path) -> None:
    _files(tmp_path, **{"a.pdf": b"v1"})
    store = tmp_path / "store"
    line = "a.pdf,household,will,Other,T,,,,"
    repo = InMemoryRepo()
    await apply_import(repo, _rows(tmp_path, line), store)
    doc = repo.docs[document_id_for("a.pdf")]
    doc.deleted_at = datetime.now(UTC)

    _files(tmp_path, **{"a.pdf": b"v2"})
    result = await apply_import(repo, _rows(tmp_path, line), store)

    assert result.skipped_deleted == 1
    assert (store / f"{doc.id}.pdf").read_bytes() == b"v1"


@pytest.mark.asyncio
async def test_unknown_entity_aborts_before_any_copy(tmp_path: Path) -> None:
    _files(tmp_path, **{"a.pdf": b"A"})
    store = tmp_path / "store"
    repo = InMemoryRepo(entities={PERSON})
    with pytest.raises(ImportProblemError) as exc:
        await apply_import(
            repo, _rows(tmp_path, "a.pdf,household,will,Other,T,,,,"), store
        )
    assert exc.value.problems == ["line 2: column 'entity': no such entity"]
    assert not store.exists()
    assert repo.docs == {}


# ---------------------------------------------------------------------------
# SqlDocumentRepository
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, values: list[Any]) -> None:
        self._values = values

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[Any]:
        return self._values

    def first(self) -> Any:
        return self._values[0] if self._values else None


class _Session:
    def __init__(self, results: list[list[Any]]) -> None:
        self.results = results
        self.queries: list[str] = []
        self.added: list[Any] = []
        self.flushed = False
        self.got: list[tuple[type, UUID]] = []

    async def execute(self, query: ClauseElement) -> _Result:
        assert isinstance(query, ClauseElement)
        self.queries.append(str(query))
        return _Result(self.results.pop(0))

    async def get(self, model: type, ident: UUID) -> Any:
        self.got.append((model, ident))
        return None

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushed = True


def _sql_repo(results: list[list[Any]]) -> tuple[SqlDocumentRepository, _Session]:
    session = _Session(results)
    return SqlDocumentRepository(cast("AsyncSession", session)), session


@pytest.mark.asyncio
async def test_sql_repo_live_entity_ids() -> None:
    repo, session = _sql_repo([[HOUSEHOLD]])
    assert await repo.live_entity_ids({HOUSEHOLD, PERSON}) == {HOUSEHOLD}
    assert "deleted_at IS NULL" in session.queries[0]
    assert await repo.live_entity_ids(set()) == set()
    assert len(session.queries) == 1


@pytest.mark.asyncio
async def test_sql_repo_sha_lookup_and_writes() -> None:
    found = uuid4()
    repo, session = _sql_repo([[found], []])
    assert await repo.live_id_with_sha("a" * 64) == found
    assert await repo.live_id_with_sha("b" * 64) is None
    assert "documents.sha256" in session.queries[0]

    ident = uuid4()
    assert await repo.get(ident) is None
    assert session.got == [(Document, ident)]
    doc = Document(title="x")
    repo.add(doc)
    await repo.flush()
    assert session.added == [doc]
    assert session.flushed
