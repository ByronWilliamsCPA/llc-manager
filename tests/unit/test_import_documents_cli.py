"""Unit tests for the ``import_documents`` command."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

import pytest

from llc_manager.cli import import_documents
from llc_manager.cli.import_documents import EXIT_INVALID, EXIT_OK, EXIT_USAGE, main
from tests.unit.test_document_import import HEADER, HOUSEHOLD, PERSON, InMemoryRepo

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = REPO_ROOT / "data" / "examples" / "document_manifest.example.csv"
SENTINEL = "Zyxwv Sentinel"


class _FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


@pytest.fixture
def repo(monkeypatch: pytest.MonkeyPatch) -> InMemoryRepo:
    fake = InMemoryRepo()
    monkeypatch.setattr(import_documents, "SqlDocumentRepository", lambda _s: fake)
    return fake


def _factory(sessions: list[_FakeSession]) -> Callable[[], AsyncSession]:
    def make() -> AsyncSession:
        session = _FakeSession()
        sessions.append(session)
        return cast("AsyncSession", session)

    return make


def _setup(tmp_path: Path, *lines: str) -> tuple[Path, Path]:
    (tmp_path / "a.pdf").write_bytes(b"A")
    (tmp_path / "b.pdf").write_bytes(b"B")
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(HEADER + "".join(f"{x}\n" for x in lines), "utf-8")
    entity_map = tmp_path / "map.json"
    entity_map.write_text(
        json.dumps(
            {
                "entities": {
                    "household": {"id": str(HOUSEHOLD)},
                    "person-a": {"id": str(PERSON)},
                }
            }
        ),
        "utf-8",
    )
    return manifest, entity_map


def _run(argv: list[str], **kwargs: Any) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, out=out, **kwargs)
    return code, out.getvalue()


def test_requires_a_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(import_documents.MANIFEST_ENV, raising=False)
    code, out = _run([])
    assert code == EXIT_USAGE
    assert "pass --manifest" in out


def test_missing_manifest(tmp_path: Path) -> None:
    code, out = _run(["--manifest", str(tmp_path / "none.csv")])
    assert code == EXIT_USAGE
    assert "manifest not found" in out


def test_real_manifest_inside_repo_is_refused(tmp_path: Path) -> None:
    inside = REPO_ROOT / "data" / f"tmp-{uuid4().hex}.csv"
    inside.write_text(HEADER, "utf-8")
    try:
        code, out = _run(["--manifest", str(inside), "--validate-only"])
    finally:
        inside.unlink()
    assert code == EXIT_USAGE
    assert "inside the repository" in out


def test_malformed_entity_map(tmp_path: Path) -> None:
    manifest, entity_map = _setup(tmp_path, "a.pdf,household,will,Other,T,,,,")
    entity_map.write_text("nope", "utf-8")
    code, out = _run(["--manifest", str(manifest), "--entity-map", str(entity_map)])
    assert code == EXIT_USAGE
    assert "entity map is missing or malformed" in out


def test_validate_only_prints_counts_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, repo: InMemoryRepo
) -> None:
    manifest, entity_map = _setup(
        tmp_path,
        f"a.pdf,household,will,Estate Planning,{SENTINEL},,,,",
        f"b.pdf,person-a,tax_return,Tax Returns,{SENTINEL},,,,",
    )
    monkeypatch.setenv(import_documents.MANIFEST_ENV, str(manifest))
    code, out = _run(["--entity-map", str(entity_map), "--validate-only"])
    assert code == EXIT_OK
    assert "rows=2" in out
    assert "category[Estate Planning]=1" in out
    assert "category[Tax Returns]=1" in out
    assert "tax_returns_without_consent=1" in out
    assert SENTINEL not in out
    assert str(tmp_path) not in out
    assert repo.docs == {}


def test_problems_exit_invalid(tmp_path: Path) -> None:
    manifest, entity_map = _setup(tmp_path, "a.pdf,household,will,Nope,T,,,,")
    code, out = _run(["--manifest", str(manifest), "--entity-map", str(entity_map)])
    assert code == EXIT_INVALID
    assert "problem: line 2: column 'category'" in out


def test_import_commits_and_prints_counts(tmp_path: Path, repo: InMemoryRepo) -> None:
    manifest, entity_map = _setup(
        tmp_path,
        "a.pdf,household,insurance_policy,Insurance,T,,,,",
        "b.pdf,person-a,will,Estate Planning,T,,,,",
    )
    store = tmp_path / "store"
    sessions: list[_FakeSession] = []
    argv = [
        "--manifest",
        str(manifest),
        "--entity-map",
        str(entity_map),
        "--documents-root",
        str(store),
    ]

    code, out = _run(argv, session_factory=_factory(sessions))
    assert code == EXIT_OK
    assert "created=2 updated=0 unchanged=0 duplicates=0" in out
    assert sessions[0].committed

    code, out = _run(argv, session_factory=_factory(sessions))
    assert "created=0 updated=0 unchanged=2" in out
    assert len(repo.docs) == 2
    assert {d.entity_id for d in repo.docs.values()} == {HOUSEHOLD, PERSON}


def test_unknown_entity_rolls_back(tmp_path: Path, repo: InMemoryRepo) -> None:
    repo.entities = set()
    manifest, entity_map = _setup(tmp_path, "a.pdf,household,will,Other,T,,,,")
    sessions: list[_FakeSession] = []
    code, out = _run(
        [
            "--manifest",
            str(manifest),
            "--entity-map",
            str(entity_map),
            "--documents-root",
            str(tmp_path / "store"),
        ],
        session_factory=_factory(sessions),
    )
    assert code == EXIT_INVALID
    assert "no such entity" in out
    assert sessions[0].rolled_back
    assert not sessions[0].committed


def test_committed_example_validates(tmp_path: Path) -> None:
    keys = ("household", "person-a", "person-b", "holding-llc", "family-trust")
    entity_map = tmp_path / "map.json"
    entity_map.write_text(
        json.dumps({"entities": {k: {"id": str(uuid4())} for k in keys}}), "utf-8"
    )
    code, out = _run(
        ["--manifest", str(EXAMPLE), "--entity-map", str(entity_map), "--validate-only"]
    )
    assert code == EXIT_OK, out
    assert "rows=4" in out
    assert "tax_returns_without_consent=0" in out
