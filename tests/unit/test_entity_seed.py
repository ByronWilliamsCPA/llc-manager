"""Unit tests for the idempotent entity seed service."""

from __future__ import annotations

import json
import os
import stat
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID, uuid4, uuid5

import pytest

from llc_manager.models.entity import Entity, EntityType
from llc_manager.services.entity_seed import (
    DEFAULT_ENTITY_NAMESPACE,
    MAPPING_DIR_ENV,
    SeedFile,
    SeedFileError,
    apply_seed,
    build_mapping,
    confine_path,
    is_inside_repo,
    is_repo_example,
    load_seed_file,
    mapping_base_dir,
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

# A private namespace, as a real seed must set.
TEST_NAMESPACE = UUID("0b6f7f43-2d0e-4c1a-9d55-5c7f8a2e9b10")


def _seed(entities: list[dict[str, Any]], **top: Any) -> SeedFile:
    top.setdefault("namespace", str(TEST_NAMESPACE))
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
    """Minimal AsyncSession stand-in: get by primary key, add, flush.

    Each flush enforces the unique EIN and Xero tenant ID indexes over live
    rows, as PostgreSQL would, and records the tenant IDs it saw.
    """

    def __init__(self, existing: list[Entity] | None = None) -> None:
        self.rows: dict[UUID, Entity] = {e.id: e for e in existing or []}
        self.added: list[Entity] = []
        self.flushes = 0
        self.get_options: list[object] = []
        self.tenants_at_flush: list[dict[UUID, str | None]] = []

    async def get(
        self, _model: type[Entity], ident: UUID, **kwargs: object
    ) -> Entity | None:
        self.get_options.append(kwargs.get("options"))
        return self.rows.get(ident)

    def add(self, obj: Entity) -> None:
        self.added.append(obj)
        self.rows[obj.id] = obj

    async def flush(self) -> None:
        self.flushes += 1
        live = [e for e in self.rows.values() if e.deleted_at is None]
        for name in ("ein", "xero_tenant_id"):
            counts = Counter(getattr(e, name) for e in live)
            counts.pop(None, None)
            if any(n > 1 for n in counts.values()):
                msg = f"unique violation on {name}"
                raise AssertionError(msg)
        self.tenants_at_flush.append({e.id: e.xero_tenant_id for e in live})


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
        assert exc.value.problems == ("seed file not found",)

    def test_unreadable_file(self, tmp_path: Path) -> None:
        path = tmp_path / "bin.json"
        path.write_bytes(b"\xff\xfe\x00bad")
        with pytest.raises(SeedFileError) as exc:
            load_seed_file(path)
        assert exc.value.problems == ("seed file could not be read",)

    def test_deeply_nested_json_is_a_seed_error(self, tmp_path: Path) -> None:
        path = tmp_path / "deep.json"
        path.write_text("[" * 200_000 + "]" * 200_000, encoding="utf-8")
        with pytest.raises(SeedFileError) as exc:
            load_seed_file(path)
        assert exc.value.problems == ("seed file could not be parsed",)

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
        entities[2][SENTINEL_NAME] = "x"  # an unknown field named by a value
        path.write_text(json.dumps({"entities": entities}), encoding="utf-8")
        with pytest.raises(SeedFileError) as exc:
            load_seed_file(path)
        text = " | ".join(exc.value.problems)
        assert "entry 2: field 'ein'" in text
        assert "entry 3: field '(unknown field)'" in text
        assert SENTINEL_NAME not in text

    def test_uuid_errors_do_not_quote_the_input(self, tmp_path: Path) -> None:
        path = tmp_path / "seed.json"
        entities = _base_entities()
        entities[0]["id"] = "Zyxwv-not-a-uuid"
        path.write_text(
            json.dumps({"namespace": "Qqqq-not-a-uuid", "entities": entities}),
            encoding="utf-8",
        )
        with pytest.raises(SeedFileError) as exc:
            load_seed_file(path)
        text = " | ".join(exc.value.problems)
        assert "file: field 'namespace': Input should be a valid UUID" in text
        assert "entry 1: field 'id': Input should be a valid UUID" in text
        assert "Z" not in text
        assert "Q" not in text

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

    def test_blank_ein_becomes_null(self) -> None:
        entities = _base_entities()
        entities[2]["ein"] = ""
        seed = _seed(entities)
        assert seed.entities[2].ein is None

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("ein", "12-3456789"),
            ("formation_state", "TX"),
            ("formation_date", "2020-01-01"),
        ],
    )
    def test_personal_entity_rejects_legal_fields(self, field: str, value: str) -> None:
        entities = _base_entities()
        entities[1][field] = value
        with pytest.raises(ValueError, match="must be empty for individual"):
            _seed(entities)

    def test_seed_file_error_needs_a_problem(self) -> None:
        with pytest.raises(ValueError, match="at least one problem"):
            SeedFileError([])


class TestStableIds:
    def test_id_is_uuid5_of_namespace_and_key(self) -> None:
        assert stable_entity_id(DEFAULT_ENTITY_NAMESPACE, "household") == uuid5(
            DEFAULT_ENTITY_NAMESPACE, "household"
        )

    def test_default_namespace_is_pinned(self) -> None:
        # Golden values: changing the namespace constant or the derivation
        # re-keys every seeded entity, so this must fail loudly.
        assert UUID("3146b117-50d6-4895-a248-6487901ede9b") == DEFAULT_ENTITY_NAMESPACE
        assert stable_entity_id(DEFAULT_ENTITY_NAMESPACE, "household") == UUID(
            "bcaeb3d1-fd33-563a-bf5b-accb8c2827cb"
        )

    def test_example_ids_are_pinned(self) -> None:
        seed = load_seed_file(EXAMPLE)
        assert {e.key: str(resolve_entity_id(seed, e)) for e in seed.entities} == {
            "household": "ea809da2-51e3-5fb3-a09d-5ab529187411",
            "person-a": "7a98fd4d-5afe-53ec-b12f-8b12f476e4bb",
            "person-b": "13f5a558-0d4f-5e97-90e5-f60dc80682c1",
            "holding-llc": "339e2dea-a486-5738-9fba-71853520a047",
            "family-trust": "7edada4e-b42c-50ed-8a0a-5d8d0828044c",
        }

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


class TestValidate:
    def test_valid_seed_has_no_problems(self) -> None:
        assert validate_seed(_seed(_base_entities())) == []

    def test_real_seed_must_set_its_own_namespace(self) -> None:
        seed = _seed(_base_entities(), namespace=str(DEFAULT_ENTITY_NAMESPACE))
        assert validate_seed(seed) == [
            "file: field 'namespace': a non-synthetic seed must set its own "
            "private namespace UUID"
        ]

    def test_synthetic_seed_may_use_default_namespace(self) -> None:
        seed = _seed(
            _base_entities(), namespace=str(DEFAULT_ENTITY_NAMESPACE), synthetic=True
        )
        assert validate_seed(seed) == []

    def test_duplicate_key_ein_tenant_and_id(self) -> None:
        entities = _base_entities()
        entities.append(
            {
                "key": "other",
                "entity_type": "llc",
                "legal_name": "Other",
                "ein": "11-1111111",
            }
        )
        dup = dict(entities[2])
        dup["ein"] = "11-1111111"
        entities.append(dup)  # same key, tenant, id as entry 3; ein as entry 4
        problems = validate_seed(_seed(entities))
        assert "entry 5: key duplicates entry 3" in problems
        assert "entry 5: entity id duplicates entry 3" in problems
        assert "entry 5: xero_tenant_id duplicates entry 3" in problems
        assert "entry 5: ein duplicates entry 4" in problems

    def test_blank_eins_do_not_collide(self) -> None:
        entities = _base_entities()
        entities.append({"key": "b2", "entity_type": "llc", "legal_name": "B2"})
        entities[2]["ein"] = ""
        entities[3]["ein"] = ""
        assert validate_seed(_seed(entities)) == []

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
        assert all(options for options in session.get_options)

    async def test_second_run_is_a_no_op(self) -> None:
        seed = _seed(_base_entities())
        session = _FakeSession()
        await apply_seed(_as_session(session), seed)
        session.added.clear()
        result = await apply_seed(_as_session(session), seed)
        assert (result.created, result.updated, result.unchanged) == (0, 0, 3)
        assert session.added == []

    async def test_invalid_seed_is_refused(self) -> None:
        seed = _seed(_base_entities()[1:])  # no household
        session = _FakeSession()
        db = _as_session(session)
        with pytest.raises(SeedFileError):
            await apply_seed(db, seed)
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

    async def test_explicit_null_clears_a_field(self) -> None:
        entities = _base_entities()
        entities[2]["notes"] = None
        seed = _seed(entities)
        biz_id = resolve_entity_id(seed, seed.entities[2])
        existing = _existing(
            biz_id,
            legal_name="Biz LLC",
            entity_type=EntityType.LLC,
            xero_tenant_id="tenant-1",
            notes="stale",
        )
        session = _FakeSession([existing])
        result = await apply_seed(_as_session(session), seed)
        assert result.updated == 1
        assert existing.notes is None

    async def test_entity_type_change_is_applied(self) -> None:
        seed = _seed(_base_entities())
        biz_id = resolve_entity_id(seed, seed.entities[2])
        existing = _existing(
            biz_id,
            legal_name="Biz LLC",
            entity_type=EntityType.TRUST,
            xero_tenant_id="tenant-1",
        )
        session = _FakeSession([existing])
        await apply_seed(_as_session(session), seed)
        assert existing.entity_type is EntityType.LLC

    async def test_tenant_swap_between_seeded_rows(self) -> None:
        entities = _base_entities()
        entities.append(
            {
                "key": "biz-2",
                "entity_type": "llc",
                "legal_name": "Biz Two",
                "xero_tenant_id": "tenant-2",
            }
        )
        seed = _seed(entities)
        one = _existing(
            resolve_entity_id(seed, seed.entities[2]),
            legal_name="Biz LLC",
            entity_type=EntityType.LLC,
            xero_tenant_id="tenant-2",
        )
        two = _existing(
            resolve_entity_id(seed, seed.entities[3]),
            legal_name="Biz Two",
            entity_type=EntityType.LLC,
            xero_tenant_id="tenant-1",
        )
        session = _FakeSession([one, two])
        result = await apply_seed(_as_session(session), seed)
        assert result.updated == 2
        assert (one.xero_tenant_id, two.xero_tenant_id) == ("tenant-1", "tenant-2")
        # The first flush released both values before reassigning them.
        assert session.flushes == 2
        assert session.tenants_at_flush[0] == {one.id: None, two.id: None}

    async def test_soft_deleted_entity_is_left_alone(self) -> None:
        seed = _seed(_base_entities())
        biz_id = resolve_entity_id(seed, seed.entities[2])
        existing = _existing(biz_id, legal_name="Gone", entity_type=EntityType.LLC)
        existing.deleted_at = datetime.now(UTC)
        session = _FakeSession([existing])
        result = await apply_seed(_as_session(session), seed)
        assert result.skipped_deleted == 1
        assert result.skipped_entries == (3,)
        assert existing.legal_name == "Gone"


class TestMapping:
    def test_mapping_lists_ids_types_and_tenants(self) -> None:
        seed = _seed(_base_entities())
        mapping = build_mapping(seed)
        assert mapping["namespace"] == str(TEST_NAMESPACE)
        assert mapping["entities"]["biz"] == {
            "id": str(resolve_entity_id(seed, seed.entities[2])),
            "entity_type": "llc",
            "xero_tenant_id": "tenant-1",
        }

    def test_mapping_omits_skipped_entries(self) -> None:
        mapping = build_mapping(_seed(_base_entities()), frozenset({3}))
        assert set(mapping["entities"]) == {"household", "person-a"}

    def test_write_mapping_content(self, tmp_path: Path) -> None:
        out = tmp_path / "private" / "map.json"
        write_mapping(out, build_mapping(_seed(_base_entities())), tmp_path)
        assert json.loads(out.read_text(encoding="utf-8"))["entities"]["household"]
        assert [p.name for p in out.parent.iterdir()] == ["map.json"]

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes only")
    def test_write_mapping_is_owner_only(self, tmp_path: Path) -> None:
        out = tmp_path / "private" / "map.json"
        write_mapping(out, build_mapping(_seed(_base_entities())), tmp_path)
        assert stat.S_IMODE(out.stat().st_mode) == 0o600
        assert stat.S_IMODE(out.parent.stat().st_mode) == 0o700

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes only")
    def test_write_mapping_replaces_a_world_readable_file(self, tmp_path: Path) -> None:
        out = tmp_path / "map.json"
        out.write_text("{}", encoding="utf-8")
        out.chmod(0o644)
        write_mapping(out, build_mapping(_seed(_base_entities())), tmp_path)
        assert stat.S_IMODE(out.stat().st_mode) == 0o600
        assert "household" in json.loads(out.read_text(encoding="utf-8"))["entities"]

    @pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges")
    def test_write_mapping_refuses_a_symlink(self, tmp_path: Path) -> None:
        target = tmp_path / "elsewhere.json"
        target.write_text("{}", encoding="utf-8")
        link = tmp_path / "map.json"
        link.symlink_to(target)
        mapping = build_mapping(_seed(_base_entities()))
        with pytest.raises(OSError, match="symbolic link"):
            write_mapping(link, mapping, tmp_path)
        assert target.read_text(encoding="utf-8") == "{}"

    def test_failed_write_leaves_no_temp_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fail(_fd: int) -> None:
            msg = "disk full"
            raise OSError(msg)

        monkeypatch.setattr(os, "fsync", fail)
        out = tmp_path / "map.json"
        mapping = build_mapping(_seed(_base_entities()))
        with pytest.raises(OSError, match="disk full"):
            write_mapping(out, mapping, tmp_path)
        assert list(tmp_path.iterdir()) == []

    def test_write_mapping_refuses_a_path_outside_the_base(
        self, tmp_path: Path
    ) -> None:
        base = tmp_path / "base"
        base.mkdir()
        mapping = build_mapping(_seed(_base_entities()))
        escape = base / ".." / "escaped.json"
        with pytest.raises(OSError, match="outside the allowed mapping directory"):
            write_mapping(escape, mapping, base)
        assert not (tmp_path / "escaped.json").exists()

    def test_write_mapping_defaults_to_the_configured_base(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(MAPPING_DIR_ENV, str(tmp_path))
        out = tmp_path / "nested" / "map.json"
        write_mapping(out, build_mapping(_seed(_base_entities())))
        assert out.is_file()


class TestConfinePath:
    def test_inside_is_resolved(self, tmp_path: Path) -> None:
        inside = tmp_path / "a" / ".." / "map.json"
        assert confine_path(inside, tmp_path) == (tmp_path / "map.json").resolve()

    def test_sibling_with_shared_prefix_is_refused(self, tmp_path: Path) -> None:
        base = tmp_path / "base"
        with pytest.raises(OSError, match="outside"):
            confine_path(tmp_path / "base-other" / "map.json", base)

    def test_base_itself_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(OSError, match="outside"):
            confine_path(tmp_path, tmp_path)

    def test_base_dir_comes_from_the_environment(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(MAPPING_DIR_ENV, str(tmp_path))
        assert mapping_base_dir() == tmp_path

    def test_base_dir_defaults_to_home(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(MAPPING_DIR_ENV, raising=False)
        assert mapping_base_dir() == Path.home()


class TestRepoGuard:
    def test_path_inside_checkout(self) -> None:
        assert is_inside_repo(EXAMPLE) is True

    def test_path_outside_checkout(self, tmp_path: Path) -> None:
        assert is_inside_repo(tmp_path / "seed.json") is False

    def test_installed_package_has_no_checkout(self, tmp_path: Path) -> None:
        assert is_inside_repo(tmp_path / "x", repo_root=tmp_path) is False

    def test_example_directory(self) -> None:
        assert is_repo_example(EXAMPLE) is True
        assert is_repo_example(EXAMPLE.parents[2] / "seed.json") is False

    def test_example_directory_outside_checkout(self, tmp_path: Path) -> None:
        assert is_repo_example(tmp_path / "seed.json") is False
