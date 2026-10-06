"""Unit tests for the ``seed_entities`` command."""

from __future__ import annotations

import io
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from llc_manager.cli import seed_entities
from llc_manager.cli.seed_entities import (
    EXIT_DATABASE,
    EXIT_INVALID,
    EXIT_MAPPING,
    EXIT_OK,
    EXIT_SKIPPED,
    EXIT_USAGE,
    MAPPING_DIR_ENV,
    main,
)

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
SENTINEL_TENANT = "Qqqqq-sentinel-tenant"
TEST_NAMESPACE = "0b6f7f43-2d0e-4c1a-9d55-5c7f8a2e9b10"


class _FakeSession:
    def __init__(self, store: dict[UUID, Entity]) -> None:
        self.store = store
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def get(
        self, _model: type[Entity], ident: UUID, **_kwargs: object
    ) -> Entity | None:
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
        "namespace": TEST_NAMESPACE,
        "entities": [
            {"key": "household", "entity_type": "household", "legal_name": "H"},
            {
                "key": "person-a",
                "entity_type": "individual",
                "legal_name": SENTINEL_NAME,
                "xero_tenant_id": SENTINEL_TENANT,
            },
        ],
    }
    data.update(overrides)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _mapping_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Allow mapping files under each test's temporary directory."""
    monkeypatch.setenv(MAPPING_DIR_ENV, str(tmp_path))


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
    assert "household=1" in out


def test_synthetic_file_inside_repo_outside_examples_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = _write_seed(tmp_path / "seed.json", synthetic=True)
    monkeypatch.setattr(seed_entities, "is_inside_repo", lambda _p: True)
    monkeypatch.setattr(seed_entities, "is_repo_example", lambda _p: False)
    code, out = _run(["--file", str(seed), "--validate-only"])
    assert code == EXIT_USAGE
    assert "data/examples/" in out


def test_synthetic_seed_needs_allow_synthetic_to_apply() -> None:
    sessions: list[_FakeSession] = []
    code, out = _run(["--file", str(EXAMPLE)], session_factory=_factory({}, sessions))
    assert code == EXIT_USAGE
    assert "--allow-synthetic" in out
    assert sessions == []

    code, out = _run(
        ["--file", str(EXAMPLE), "--allow-synthetic"],
        session_factory=_factory({}, sessions),
    )
    assert code == EXIT_OK
    assert "created=5" in out


def test_mapping_inside_repo_is_refused(tmp_path: Path) -> None:
    seed = _write_seed(tmp_path / "seed.json")
    inside = EXAMPLE.parent / "map.json"
    code, out = _run(["--file", str(seed), "--mapping-out", str(inside)])
    assert code == EXIT_USAGE
    assert "--mapping-out" in out
    assert not inside.exists()


def test_mapping_outside_the_allowed_directory_is_refused_before_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setenv(MAPPING_DIR_ENV, str(allowed))
    seed = _write_seed(tmp_path / "seed.json")
    sessions: list[_FakeSession] = []
    code, out = _run(
        ["--file", str(seed), "--mapping-out", str(tmp_path / "map.json")],
        session_factory=_factory({}, sessions),
    )
    assert code == EXIT_USAGE
    assert MAPPING_DIR_ENV in out
    assert sessions == []
    assert not (tmp_path / "map.json").exists()


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


class _DriverError(Exception):
    """Stand-in for a driver exception that exposes the constraint name."""

    constraint_name = "ix_entities_xero_tenant_id_active"


def test_integrity_error_prints_no_values_and_rolls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions: list[_FakeSession] = []
    seed = _write_seed(tmp_path / "seed.json")

    async def boom(*_args: object) -> None:
        raise IntegrityError(
            "INSERT INTO entities ...",
            {"legal_name": SENTINEL_NAME, "xero_tenant_id": SENTINEL_TENANT},
            _DriverError(f"duplicate key ({SENTINEL_TENANT})"),
        )

    monkeypatch.setattr(seed_entities, "apply_seed", boom)
    code, out = _run(["--file", str(seed)], session_factory=_factory({}, sessions))
    assert code == EXIT_DATABASE
    assert (
        "database error (IntegrityError, constraint "
        "ix_entities_xero_tenant_id_active)" in out
    )
    assert SENTINEL_NAME not in out
    assert SENTINEL_TENANT not in out
    assert sessions[0].rolled_back
    assert not sessions[0].committed


def test_connection_error_is_reported_without_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = _write_seed(tmp_path / "seed.json")
    mapping = tmp_path / "map.json"

    async def boom(*_args: object) -> None:
        raise OperationalError("SELECT ...", {"id": SENTINEL_NAME}, OSError("refused"))

    monkeypatch.setattr(seed_entities, "apply_seed", boom)
    code, out = _run(
        ["--file", str(seed), "--mapping-out", str(mapping)],
        session_factory=_factory({}, []),
    )
    assert code == EXIT_DATABASE
    assert "database error (OperationalError)" in out
    assert SENTINEL_NAME not in out
    assert not mapping.exists()


def test_mapping_failure_after_commit_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions: list[_FakeSession] = []
    seed = _write_seed(tmp_path / "seed.json")

    def fail(*_args: object) -> None:
        msg = "read-only file system"
        raise OSError(msg)

    monkeypatch.setattr(seed_entities, "write_mapping", fail)
    code, out = _run(
        ["--file", str(seed), "--mapping-out", str(tmp_path / "map.json")],
        session_factory=_factory({}, sessions),
    )
    assert code == EXIT_MAPPING
    assert "mapping file could not be written (database changes were committed)" in out
    assert sessions[0].committed


def test_validate_only_writes_mapping_from_the_file(tmp_path: Path) -> None:
    sessions: list[_FakeSession] = []
    seed = _write_seed(tmp_path / "seed.json")
    mapping = tmp_path / "map.json"
    code, out = _run(
        ["--file", str(seed), "--validate-only", "--mapping-out", str(mapping)],
        session_factory=_factory({}, sessions),
    )
    assert code == EXIT_OK
    assert "mapping written" in out
    assert sessions == []
    assert set(json.loads(mapping.read_text(encoding="utf-8"))["entities"]) == {
        "household",
        "person-a",
    }


def test_soft_deleted_entity_exits_nonzero_and_is_left_out_of_mapping(
    tmp_path: Path,
) -> None:
    store: dict[UUID, Entity] = {}
    seed = _write_seed(tmp_path / "seed.json")
    mapping = tmp_path / "map.json"
    _run(["--file", str(seed)], session_factory=_factory(store, []))
    person = next(e for e in store.values() if e.legal_name == SENTINEL_NAME)
    person.deleted_at = datetime.now(UTC)

    code, out = _run(
        ["--file", str(seed), "--mapping-out", str(mapping)],
        session_factory=_factory(store, []),
    )
    assert code == EXIT_SKIPPED
    assert "problem: entry 2: entity is soft-deleted" in out
    assert SENTINEL_NAME not in out
    assert set(json.loads(mapping.read_text(encoding="utf-8"))["entities"]) == {
        "household"
    }


def test_default_engine_is_used_and_disposed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions: list[_FakeSession] = []
    disposed: list[bool] = []

    class _Engine:
        async def dispose(self) -> None:
            disposed.append(True)

    fake_module = SimpleNamespace(
        AsyncSessionLocal=_factory({}, sessions), async_engine=_Engine()
    )
    monkeypatch.setitem(sys.modules, "llc_manager.db.session", fake_module)
    seed = _write_seed(tmp_path / "seed.json")

    code, out = _run(["--file", str(seed)])

    assert code == EXIT_OK
    assert "created=2" in out
    assert sessions[0].committed
    assert disposed == [True]
