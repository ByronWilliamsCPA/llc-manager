"""Unit tests for the ``seed_entities`` command."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import pytest

from llc_manager.cli import seed_entities
from llc_manager.cli.seed_entities import EXIT_INVALID, EXIT_OK, EXIT_USAGE, main

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from llc_manager.models.entity import Entity

pytestmark = pytest.mark.unit

EXAMPLE = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "examples"
    / "entity_seed.example.json"
)
SENTINEL_NAME = "Zyxwv Sentinel Name"


class _FakeSession:
    def __init__(self, store: dict[UUID, Entity]) -> None:
        self.store = store
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def get(self, _model: type[Entity], ident: UUID) -> Entity | None:
        return self.store.get(ident)

    def add(self, obj: Entity) -> None:
        obj.deleted_at = None
        self.store[obj.id] = obj

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def _factory(
    store: dict[UUID, Entity], sessions: list[_FakeSession]
) -> Callable[[], AsyncSession]:
    def make() -> AsyncSession:
        session = _FakeSession(store)
        sessions.append(session)
        return cast("AsyncSession", session)

    return make


def _write_seed(path: Path, **overrides: Any) -> Path:
    data: dict[str, Any] = {
        "entities": [
            {"key": "household", "entity_type": "household", "legal_name": "H"},
            {
                "key": "person-a",
                "entity_type": "individual",
                "legal_name": SENTINEL_NAME,
            },
        ]
    }
    data.update(overrides)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _run(argv: list[str], **kwargs: Any) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, out=out, **kwargs)
    return code, out.getvalue()


def test_requires_a_seed_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(seed_entities.SEED_FILE_ENV, raising=False)
    code, out = _run([])
    assert code == EXIT_USAGE
    assert "pass --file" in out


def test_missing_file_is_usage_error(tmp_path: Path) -> None:
    code, out = _run(["--file", str(tmp_path / "none.json")])
    assert code == EXIT_USAGE
    assert "seed file not found" in out


def test_reads_path_from_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = _write_seed(tmp_path / "seed.json")
    monkeypatch.setenv(seed_entities.SEED_FILE_ENV, str(seed))
    code, out = _run(["--validate-only"])
    assert code == EXIT_OK
    assert "household=1" in out
    assert "individual=1" in out
    assert "total=2" in out


def test_validate_only_never_opens_a_session(tmp_path: Path) -> None:
    sessions: list[_FakeSession] = []
    seed = _write_seed(tmp_path / "seed.json")
    code, _ = _run(
        ["--file", str(seed), "--validate-only"],
        session_factory=_factory({}, sessions),
    )
    assert code == EXIT_OK
    assert sessions == []


def test_schema_problem_exits_invalid(tmp_path: Path) -> None:
    path = tmp_path / "seed.json"
    path.write_text(json.dumps({"entities": [{"key": "x"}]}), encoding="utf-8")
    code, out = _run(["--file", str(path)])
    assert code == EXIT_INVALID
    assert "problem: entry 1" in out


def test_rule_problem_exits_invalid_without_values(tmp_path: Path) -> None:
    seed = _write_seed(
        tmp_path / "seed.json",
        entities=[
            {"key": "p", "entity_type": "individual", "legal_name": SENTINEL_NAME}
        ],
    )
    code, out = _run(["--file", str(seed)])
    assert code == EXIT_INVALID
    assert "expected exactly one household entity" in out
    assert SENTINEL_NAME not in out


def test_real_seed_inside_repo_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = _write_seed(tmp_path / "seed.json")
    monkeypatch.setattr(seed_entities, "is_inside_repo", lambda _p: True)
    code, out = _run(["--file", str(seed), "--validate-only"])
    assert code == EXIT_USAGE
    assert "inside the repository" in out


def test_synthetic_example_inside_repo_is_allowed() -> None:
    code, out = _run(["--file", str(EXAMPLE), "--validate-only"])
    assert code == EXIT_OK
    assert "total=5" in out


def test_mapping_inside_repo_is_refused(tmp_path: Path) -> None:
    seed = _write_seed(tmp_path / "seed.json")
    inside = EXAMPLE.parent / "map.json"
    code, out = _run(["--file", str(seed), "--mapping-out", str(inside)])
    assert code == EXIT_USAGE
    assert "--mapping-out" in out
    assert not inside.exists()


def test_apply_twice_is_idempotent_and_writes_mapping(tmp_path: Path) -> None:
    store: dict[UUID, Entity] = {}
    sessions: list[_FakeSession] = []
    seed = _write_seed(tmp_path / "seed.json")
    mapping = tmp_path / "out" / "map.json"

    code, out = _run(
        ["--file", str(seed), "--mapping-out", str(mapping)],
        session_factory=_factory(store, sessions),
    )
    assert code == EXIT_OK
    assert "created=2 updated=0 unchanged=0 skipped_deleted=0" in out
    assert "mapping written" in out
    assert sessions[0].committed
    assert SENTINEL_NAME not in out
    ids = {
        v["id"]
        for v in json.loads(mapping.read_text(encoding="utf-8"))["entities"].values()
    }
    assert ids == {str(k) for k in store}

    code, out = _run(["--file", str(seed)], session_factory=_factory(store, sessions))
    assert code == EXIT_OK
    assert "created=0 updated=0 unchanged=2" in out
    assert len(store) == 2


def test_database_error_rolls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions: list[_FakeSession] = []
    seed = _write_seed(tmp_path / "seed.json")

    async def boom(*_args: object) -> None:
        msg = "db down"
        raise RuntimeError(msg)

    monkeypatch.setattr(seed_entities, "apply_seed", boom)
    with pytest.raises(RuntimeError, match="db down"):
        _run(["--file", str(seed)], session_factory=_factory({}, sessions))
    assert sessions[0].rolled_back
    assert not sessions[0].committed
