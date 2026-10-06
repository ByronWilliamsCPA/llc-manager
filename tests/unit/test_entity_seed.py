"""Unit tests for the idempotent entity seed service."""

from __future__ import annotations

import json
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID, uuid4, uuid5

import pytest

from llc_manager.models.entity import Entity, EntityType
from llc_manager.services.entity_seed import (
    DEFAULT_ENTITY_NAMESPACE,
    SeedFile,
    SeedFileError,
    apply_seed,
    build_mapping,
    is_inside_repo,
    load_seed_file,
    resolve_entity_id,
    stable_entity_id,
    summarize_seed,
    validate_seed,
    write_mapping,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.unit

EXAMPLE = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "examples"
    / "entity_seed.example.json"
)

# A marker value that must never appear in problem text or command output.
SENTINEL_NAME = "Zyxwv Sentinel Name"


def _seed(entities: list[dict[str, Any]], **top: Any) -> SeedFile:
    return SeedFile.model_validate({"entities": entities, **top})


def _base_entities() -> list[dict[str, Any]]:
    return [
        {"key": "household", "entity_type": "household", "legal_name": "H"},
        {"key": "person-a", "entity_type": "individual", "legal_name": SENTINEL_NAME},
        {
            "key": "biz",
            "entity_type": "llc",
            "legal_name": "Biz LLC",
            "xero_tenant_id": "tenant-1",
        },
    ]


class _FakeSession:
    """Minimal AsyncSession stand-in: get by primary key, add, flush."""

    def __init__(self, existing: list[Entity] | None = None) -> None:
        self.rows: dict[UUID, Entity] = {e.id: e for e in existing or []}
        self.added: list[Entity] = []
        self.flushes = 0

    async def get(self, _model: type[Entity], ident: UUID) -> Entity | None:
        return self.rows.get(ident)

    def add(self, obj: Entity) -> None:
        self.added.append(obj)
        self.rows[obj.id] = obj

    async def flush(self) -> None:
        self.flushes += 1


def _as_session(session: _FakeSession) -> AsyncSession:
    return cast("AsyncSession", session)


class TestLoad:
    def test_example_file_is_valid_and_synthetic(self) -> None:
        seed = load_seed_file(EXAMPLE)
        assert seed.synthetic is True
        assert validate_seed(seed) == []
        assert summarize_seed(seed)["household"] == 1

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(SeedFileError) as exc:
            load_seed_file(tmp_path / "nope.json")
        assert exc.value.problems == ["seed file not found"]

    def test_unreadable_file(self, tmp_path: Path) -> None:
        path = tmp_path / "bin.json"
        path.write_bytes(b"\xff\xfe\x00bad")
        with pytest.raises(SeedFileError) as exc:
            load_seed_file(path)
        assert exc.value.problems == ["seed file could not be read"]

    def test_invalid_json_reports_position_only(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text('{"entities": [' + SENTINEL_NAME, encoding="utf-8")
        with pytest.raises(SeedFileError) as exc:
            load_seed_file(path)
        assert "not valid JSON" in exc.value.problems[0]
        assert SENTINEL_NAME not in " ".join(exc.value.problems)

    def test_schema_errors_name_entry_and_field_not_value(self, tmp_path: Path) -> None:
        path = tmp_path / "seed.json"
        entities = _base_entities()
        entities[1]["ein"] = SENTINEL_NAME  # fails the EIN pattern
        entities[2]["unknown_field"] = SENTINEL_NAME
        path.write_text(json.dumps({"entities": entities}), encoding="utf-8")
        with pytest.raises(SeedFileError) as exc:
            load_seed_file(path)
        text = " | ".join(exc.value.problems)
        assert "entry 2: field 'ein'" in text
        assert "entry 3: field 'unknown_field'" in text
        assert SENTINEL_NAME not in text

    def test_entity_type_is_required(self) -> None:
        with pytest.raises(ValueError, match="entity_type is required"):
            _seed([{"key": "x", "legal_name": "X"}])

    def test_file_level_error(self, tmp_path: Path) -> None:
        path = tmp_path / "seed.json"
        path.write_text(json.dumps({"entities": []}), encoding="utf-8")
        with pytest.raises(SeedFileError) as exc:
            load_seed_file(path)
        assert exc.value.problems[0].startswith("file: field 'entities'")

    def test_bad_key_pattern_rejected(self) -> None:
        with pytest.raises(ValueError, match="key"):
            _seed(
                [{"key": "Has Spaces", "entity_type": "household", "legal_name": "H"}]
            )


class TestStableIds:
    def test_id_is_uuid5_of_namespace_and_key(self) -> None:
        assert stable_entity_id(DEFAULT_ENTITY_NAMESPACE, "household") == uuid5(
            DEFAULT_ENTITY_NAMESPACE, "household"
        )

    def test_custom_namespace_changes_ids(self) -> None:
        other = uuid4()
        seed = _seed(_base_entities(), namespace=str(other))
        assert resolve_entity_id(seed, seed.entities[0]) == uuid5(other, "household")

    def test_pinned_id_wins(self) -> None:
        pinned = uuid4()
        entities = _base_entities()
        entities[2]["id"] = str(pinned)
        seed = _seed(entities)
        assert resolve_entity_id(seed, seed.entities[2]) == pinned

    def test_ids_are_stable_across_loads(self, tmp_path: Path) -> None:
        first = load_seed_file(EXAMPLE)
        second = load_seed_file(EXAMPLE)
        assert [resolve_entity_id(first, e) for e in first.entities] == [
            resolve_entity_id(second, e) for e in second.entities
        ]


class TestValidate:
    def test_valid_seed_has_no_problems(self) -> None:
        assert validate_seed(_seed(_base_entities())) == []

    def test_duplicate_key_ein_tenant_and_id(self) -> None:
        entities = _base_entities()
        entities[1]["ein"] = "11-1111111"
        dup = dict(entities[2])
        dup["ein"] = "11-1111111"
        entities.append(dup)  # same key, tenant, id; ein matches entry 2
        problems = validate_seed(_seed(entities))
        assert "entry 4: key duplicates entry 3" in problems
        assert "entry 4: entity id duplicates entry 3" in problems
        assert "entry 4: xero_tenant_id duplicates entry 3" in problems
        assert "entry 4: ein duplicates entry 2" in problems

    def test_household_and_individual_counts(self) -> None:
        problems = validate_seed(
            _seed([{"key": "biz", "entity_type": "llc", "legal_name": "B"}])
        )
        assert "expected exactly one household entity, found 0" in problems
        assert "expected at least one individual entity, found 0" in problems

    def test_two_households_rejected(self) -> None:
        entities = _base_entities()
        entities.append({"key": "h2", "entity_type": "household", "legal_name": "H2"})
        assert "expected exactly one household entity, found 2" in validate_seed(
            _seed(entities)
        )

    def test_problems_never_contain_values(self) -> None:
        entities = _base_entities()
        entities.append(dict(entities[1]))
        assert SENTINEL_NAME not in " ".join(validate_seed(_seed(entities)))

    def test_summary_counts_by_type(self) -> None:
        assert summarize_seed(_seed(_base_entities())) == {
            "household": 1,
            "individual": 1,
            "llc": 1,
            "total": 3,
        }


def _existing(entity_id: UUID, **fields: Any) -> Entity:
    entity = Entity(id=entity_id, **fields)
    entity.deleted_at = None
    return entity


@pytest.mark.asyncio
class TestApply:
    async def test_first_run_creates_every_entity(self) -> None:
        seed = _seed(_base_entities())
        session = _FakeSession()
        result = await apply_seed(_as_session(session), seed)
        assert (result.created, result.updated, result.unchanged) == (3, 0, 0)
        assert {e.id for e in session.added} == {
            resolve_entity_id(seed, e) for e in seed.entities
        }
        household = session.added[0]
        assert household.entity_type is EntityType.HOUSEHOLD
        assert session.flushes == 1

    async def test_second_run_is_a_no_op(self) -> None:
        seed = _seed(_base_entities())
        session = _FakeSession()
        await apply_seed(_as_session(session), seed)
        session.added.clear()
        result = await apply_seed(_as_session(session), seed)
        assert (result.created, result.updated, result.unchanged) == (0, 0, 3)
        assert session.added == []

    async def test_changed_field_updates_only_named_fields(self) -> None:
        seed = _seed(_base_entities())
        biz_id = resolve_entity_id(seed, seed.entities[2])
        existing = _existing(
            biz_id,
            legal_name="Biz LLC",
            entity_type=EntityType.LLC,
            xero_tenant_id="old-tenant",
            notes="added in the UI",
        )
        session = _FakeSession([existing])
        result = await apply_seed(_as_session(session), seed)
        assert result.updated == 1
        assert result.created == 2
        assert existing.xero_tenant_id == "tenant-1"
        assert existing.notes == "added in the UI"

    async def test_soft_deleted_entity_is_left_alone(self) -> None:
        seed = _seed(_base_entities())
        biz_id = resolve_entity_id(seed, seed.entities[2])
        existing = _existing(biz_id, legal_name="Gone", entity_type=EntityType.LLC)
        existing.deleted_at = datetime.now(UTC)
        session = _FakeSession([existing])
        result = await apply_seed(_as_session(session), seed)
        assert result.skipped_deleted == 1
        assert existing.legal_name == "Gone"


class TestMapping:
    def test_mapping_lists_ids_types_and_tenants(self) -> None:
        seed = _seed(_base_entities())
        mapping = build_mapping(seed)
        assert mapping["namespace"] == str(DEFAULT_ENTITY_NAMESPACE)
        assert mapping["entities"]["biz"] == {
            "id": str(resolve_entity_id(seed, seed.entities[2])),
            "entity_type": "llc",
            "xero_tenant_id": "tenant-1",
        }

    def test_write_mapping_is_owner_only(self, tmp_path: Path) -> None:
        out = tmp_path / "private" / "map.json"
        write_mapping(out, build_mapping(_seed(_base_entities())))
        assert json.loads(out.read_text(encoding="utf-8"))["entities"]["household"]
        assert stat.S_IMODE(out.stat().st_mode) == 0o600


class TestRepoGuard:
    def test_path_inside_checkout(self) -> None:
        assert is_inside_repo(EXAMPLE) is True

    def test_path_outside_checkout(self, tmp_path: Path) -> None:
        assert is_inside_repo(tmp_path / "seed.json") is False

    def test_installed_package_has_no_checkout(self, tmp_path: Path) -> None:
        assert is_inside_repo(tmp_path / "x", repo_root=tmp_path) is False
