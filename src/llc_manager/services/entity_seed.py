"""Idempotent entity seed: load, validate, and apply a private seed file.

The seed file names every production entity (one ``individual`` per person,
one ``household``, and the business entities). It holds private data, so it
lives outside this repository and is passed in by path. Only the synthetic
example under ``data/examples/`` is committed.

Entity IDs are stable across re-seeds: each entry carries a private ``key``
and its UUID is ``uuid5(namespace, key)``, unless the entry pins an explicit
``id`` (for entities created before the seed existed). Re-running the seed
never changes an ID, so downstream systems can store the UUIDs.

Nothing in this module prints or logs field values. Validation problems name
the entry by its position in the file and the field by name only.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from llc_manager.models.entity import Entity, EntityType
from llc_manager.schemas.entity import EntityCreate

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Default namespace for uuid5 entity IDs. A seed file may set its own
# ``namespace`` so IDs cannot be derived from guessable keys alone.
DEFAULT_ENTITY_NAMESPACE = UUID("3146b117-50d6-4895-a248-6487901ede9b")

SEED_FILE_VERSION = 1

# Root of the source checkout when running from one (``src/llc_manager/..``).
_REPO_ROOT = Path(__file__).resolve().parents[3]


class SeedEntity(EntityCreate):
    """One entity in the seed file.

    All ``EntityCreate`` fields are accepted. ``entity_type`` is required here
    (it defaults to ``llc`` in the API) so a missing type is caught instead of
    silently turning a person into an LLC.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        str_strip_whitespace=True,
        extra="forbid",
    )

    key: str = Field(
        ..., min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9_.-]*$"
    )
    id: UUID | None = None

    @model_validator(mode="before")
    @classmethod
    def _require_entity_type(cls, data: object) -> object:
        """Reject an entry that omits ``entity_type``.

        Args:
            data (object): Raw entry before field validation.

        Returns:
            object: The unchanged entry.

        Raises:
            ValueError: If the entry is a mapping without ``entity_type``.
        """
        if isinstance(data, dict) and "entity_type" not in data:
            msg = "entity_type is required in a seed entry"
            raise ValueError(msg)
        return data


class SeedFile(BaseModel):
    """Top-level seed file document."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    version: int = Field(SEED_FILE_VERSION, ge=1, le=SEED_FILE_VERSION)
    synthetic: bool = False
    namespace: UUID = DEFAULT_ENTITY_NAMESPACE
    entities: list[SeedEntity] = Field(..., min_length=1)


class SeedFileError(Exception):
    """The seed file could not be read or does not match the schema.

    Args:
        problems (list[str]): Value-free descriptions of each problem.

    Attributes:
        problems (list[str]): Value-free descriptions of each problem.
    """

    problems: list[str]

    def __init__(self, problems: list[str]) -> None:
        super().__init__(f"{len(problems)} problem(s) in seed file")
        self.problems = problems


@dataclass(frozen=True)
class SeedResult:
    """Counts from applying a seed. Holds no field values.

    Attributes:
        created (int): Entities inserted.
        updated (int): Existing entities with at least one changed field.
        unchanged (int): Existing entities already matching the seed.
        skipped_deleted (int): Entities that exist but are soft-deleted; left
            alone so a deliberate delete is not undone by a re-seed.
    """

    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped_deleted: int = 0


def stable_entity_id(namespace: UUID, key: str) -> UUID:
    """Derive the stable entity UUID for a seed key.

    Args:
        namespace (UUID): The seed file's uuid5 namespace.
        key (str): The entry's private stable key.

    Returns:
        UUID: ``uuid5(namespace, key)``.
    """
    return uuid5(namespace, key)


def resolve_entity_id(seed: SeedFile, entry: SeedEntity) -> UUID:
    """Return the pinned ``id`` of an entry, or its derived stable UUID.

    Args:
        seed (SeedFile): The seed file (for its namespace).
        entry (SeedEntity): The entry.

    Returns:
        UUID: The entity ID this entry seeds.
    """
    return entry.id or stable_entity_id(seed.namespace, entry.key)


def is_inside_repo(path: Path, repo_root: Path = _REPO_ROOT) -> bool:
    """Report whether ``path`` lies inside this source checkout.

    Only meaningful when running from a checkout (the root has a
    ``pyproject.toml``); in an installed package it always returns False.

    Args:
        path (Path): Path to test.
        repo_root (Path): Checkout root to test against.

    Returns:
        bool: True when ``path`` resolves under ``repo_root``.
    """
    if not (repo_root / "pyproject.toml").is_file():
        return False
    return path.resolve().is_relative_to(repo_root.resolve())


def _format_validation_error(exc: ValidationError) -> list[str]:
    """Describe pydantic errors by location and message, never by input."""
    problems: list[str] = []
    for err in exc.errors(include_input=False, include_url=False):
        loc = err["loc"]
        # An entry error has loc ("entities", <index>, <field>, ...).
        if loc[:1] == ("entities",) and len(loc) > 1 and isinstance(loc[1], int):
            where = f"entry {loc[1] + 1}"
            field = ".".join(str(part) for part in loc[2:]) or "(entry)"
        else:
            where = "file"
            field = ".".join(str(part) for part in loc) or "(root)"
        problems.append(f"{where}: field '{field}': {err['msg']}")
    return problems


def load_seed_file(path: Path) -> SeedFile:
    """Read and parse a seed file.

    Args:
        path (Path): Path to the JSON seed file.

    Returns:
        SeedFile: The parsed seed.

    Raises:
        SeedFileError: If the file is missing, not JSON, or off-schema.
    """
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SeedFileError(["seed file not found"]) from None
    except (OSError, UnicodeDecodeError):
        raise SeedFileError(["seed file could not be read"]) from None
    except json.JSONDecodeError as exc:
        raise SeedFileError(
            [f"seed file is not valid JSON (line {exc.lineno}, column {exc.colno})"]
        ) from None
    try:
        return SeedFile.model_validate(raw)
    except ValidationError as exc:
        raise SeedFileError(_format_validation_error(exc)) from None


def _duplicates(values: list[tuple[int, Any]], label: str) -> list[str]:
    """Report entries whose non-null value repeats an earlier entry's."""
    counts = Counter(value for _, value in values if value is not None)
    first_seen: dict[Any, int] = {}
    problems: list[str] = []
    for index, value in values:
        if value is None or counts[value] == 1:
            continue
        if value in first_seen:
            problems.append(
                f"entry {index}: {label} duplicates entry {first_seen[value]}"
            )
        else:
            first_seen[value] = index
    return problems


def validate_seed(seed: SeedFile) -> list[str]:
    """Check cross-entry rules the schema cannot express.

    Rules: keys, resolved IDs, EINs, and Xero tenant IDs are unique; there is
    exactly one ``household`` entity and at least one ``individual``.

    Args:
        seed (SeedFile): The parsed seed.

    Returns:
        list[str]: Value-free problem descriptions; empty when valid.
    """
    numbered = list(enumerate(seed.entities, start=1))
    problems: list[str] = []
    problems += _duplicates([(i, e.key) for i, e in numbered], "key")
    problems += _duplicates(
        [(i, resolve_entity_id(seed, e)) for i, e in numbered], "entity id"
    )
    problems += _duplicates([(i, e.ein or None) for i, e in numbered], "ein")
    problems += _duplicates(
        [(i, e.xero_tenant_id) for i, e in numbered], "xero_tenant_id"
    )

    types = Counter(e.entity_type for e in seed.entities)
    if types[EntityType.HOUSEHOLD] != 1:
        problems.append(
            f"expected exactly one household entity, found {types[EntityType.HOUSEHOLD]}"
        )
    if types[EntityType.INDIVIDUAL] == 0:
        problems.append("expected at least one individual entity, found 0")
    return problems


def summarize_seed(seed: SeedFile) -> dict[str, int]:
    """Count entries by entity type, for value-free reporting.

    Args:
        seed (SeedFile): The parsed seed.

    Returns:
        dict[str, int]: Entity type value to count, plus ``total``.
    """
    counts = Counter(e.entity_type.value for e in seed.entities)
    summary = dict(sorted(counts.items()))
    summary["total"] = len(seed.entities)
    return summary


def _entity_fields(entry: SeedEntity) -> dict[str, Any]:
    """Return the Entity column values the entry explicitly sets.

    ``exclude_unset`` means a re-seed only touches fields the seed file
    names, so details added later through the UI are not wiped.
    """
    fields = entry.model_dump(exclude_unset=True, exclude={"key", "id"})
    fields["entity_type"] = entry.entity_type
    return fields


async def apply_seed(session: AsyncSession, seed: SeedFile) -> SeedResult:
    """Create or update every entity in the seed, keyed by stable UUID.

    The caller owns the transaction: commit on success, roll back on error.

    Args:
        session (AsyncSession): Database session.
        seed (SeedFile): A seed that passed :func:`validate_seed`.

    Returns:
        SeedResult: Counts of created, updated, unchanged, and skipped rows.
    """
    created = updated = unchanged = skipped_deleted = 0
    for entry in seed.entities:
        entity_id = resolve_entity_id(seed, entry)
        fields = _entity_fields(entry)
        existing = await session.get(Entity, entity_id)
        if existing is None:
            session.add(Entity(id=entity_id, **fields))
            created += 1
            continue
        if existing.deleted_at is not None:
            skipped_deleted += 1
            continue
        changed = False
        for name, value in fields.items():
            if getattr(existing, name) != value:
                setattr(existing, name, value)
                changed = True
        if changed:
            updated += 1
        else:
            unchanged += 1
    await session.flush()
    return SeedResult(
        created=created,
        updated=updated,
        unchanged=unchanged,
        skipped_deleted=skipped_deleted,
    )


def build_mapping(seed: SeedFile) -> dict[str, Any]:
    """Build the private key-to-UUID mapping that downstream seeds read.

    Args:
        seed (SeedFile): The parsed seed.

    Returns:
        dict[str, Any]: ``{"namespace": ..., "entities": {key: {...}}}``.
    """
    return {
        "namespace": str(seed.namespace),
        "entities": {
            entry.key: {
                "id": str(resolve_entity_id(seed, entry)),
                "entity_type": entry.entity_type.value,
                "xero_tenant_id": entry.xero_tenant_id,
            }
            for entry in seed.entities
        },
    }


def write_mapping(path: Path, mapping: dict[str, Any]) -> None:
    """Write the mapping JSON with owner-only permissions.

    Args:
        path (Path): Destination outside this repository.
        mapping (dict[str, Any]): Output of :func:`build_mapping`.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(
        json.dumps(mapping, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    tmp.chmod(0o600)
    tmp.replace(path)
