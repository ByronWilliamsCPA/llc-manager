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

import contextlib
import json
import os
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar
from uuid import UUID, uuid5

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from sqlalchemy.orm import lazyload

from llc_manager.core.exceptions import ProjectBaseError
from llc_manager.models.entity import Entity, EntityType
from llc_manager.schemas.entity import EntityCreate

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

# #CRITICAL: Data integrity - entity IDs are uuid5(namespace, key). Changing
# this constant, a seed file's namespace, or an entry's key re-keys the entity,
# and every downstream system that stored the old UUID loses its link.
# #VERIFY: tests/unit/test_entity_seed.py pins literal UUIDs for this
# namespace; that test must fail if the constant or the derivation changes.
DEFAULT_ENTITY_NAMESPACE = UUID("3146b117-50d6-4895-a248-6487901ede9b")

SEED_FILE_VERSION = 1

# Root of the source checkout when running from one (``src/llc_manager/..``).
_REPO_ROOT = Path(__file__).resolve().parents[3]

# Fields with a database uniqueness constraint. A re-seed may move one of these
# values between seeded rows, so apply_seed releases them before reassigning.
_UNIQUE_FIELDS = ("ein", "xero_tenant_id")


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

        The field keeps the inherited ``llc`` default for type checkers (a
        subclass may not make a defaulted field required), so the seed
        enforces presence here instead.

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

    @field_validator("ein")
    @classmethod
    def _blank_ein_is_none(cls, value: str | None) -> str | None:
        """Store a blank EIN as null.

        ``entities.ein`` is unique, so two blank strings would collide on
        insert while two nulls do not.

        Args:
            value (str | None): EIN after pattern validation.

        Returns:
            str | None: The EIN, or None when blank.
        """
        return value or None


class SeedFile(BaseModel):
    """Top-level seed file document."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    version: int = Field(SEED_FILE_VERSION, ge=1, le=SEED_FILE_VERSION)
    synthetic: bool = False
    namespace: UUID = DEFAULT_ENTITY_NAMESPACE
    entities: list[SeedEntity] = Field(..., min_length=1)


class SeedFileError(ProjectBaseError):
    """The seed file could not be read or does not match the schema.

    Args:
        problems (Sequence[str]): Value-free descriptions of each problem;
            at least one.

    Attributes:
        problems (tuple[str, ...]): Value-free descriptions of each problem.

    Raises:
        ValueError: If ``problems`` is empty.
    """

    problems: tuple[str, ...]

    def __init__(self, problems: Sequence[str]) -> None:
        if not problems:
            msg = "SeedFileError needs at least one problem"
            raise ValueError(msg)
        self.problems = tuple(problems)
        super().__init__(
            f"{len(self.problems)} problem(s) in seed file",
            error_code="SEED_FILE_INVALID",
        )


@dataclass(frozen=True)
class SeedResult:
    """Counts from applying a seed. Holds no field values.

    Attributes:
        created (int): Entities inserted.
        updated (int): Existing entities with at least one changed field.
        unchanged (int): Existing entities already matching the seed.
        skipped_entries (tuple[int, ...]): 1-based positions of entries whose
            entity exists but is soft-deleted; left alone so a deliberate
            delete is not undone by a re-seed.
    """

    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped_entries: tuple[int, ...] = ()

    @property
    def skipped_deleted(self) -> int:
        """Number of entries skipped because their entity is soft-deleted.

        Returns:
            int: ``len(skipped_entries)``.
        """
        return len(self.skipped_entries)


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

    This is an advisory guard against committing private data, not a
    security boundary. It recognises a checkout by a ``pyproject.toml`` at
    ``repo_root``; when that file is absent (an installed wheel, or a
    container image that does not ship it) the check returns False and lets
    the path through.

    Args:
        path (Path): Path to test.
        repo_root (Path): Checkout root to test against.

    Returns:
        bool: True when ``path`` resolves under ``repo_root``.
    """
    # #ASSUME: Security - fails open outside a source checkout. Real seed and
    # mapping files are kept out of git by operator practice and .gitignore,
    # not by this check.
    # #VERIFY: run the seed command from a checkout when preparing seed files,
    # so a path under the repository is refused.
    if not (repo_root / "pyproject.toml").is_file():
        return False
    return path.resolve().is_relative_to(repo_root.resolve())


def is_repo_example(path: Path, repo_root: Path = _REPO_ROOT) -> bool:
    """Report whether ``path`` lies under the checkout's ``data/examples/``.

    Args:
        path (Path): Path to test.
        repo_root (Path): Checkout root to test against.

    Returns:
        bool: True when ``path`` is inside the checkout's examples directory.
    """
    if not is_inside_repo(path, repo_root):
        return False
    examples = (repo_root / "data" / "examples").resolve()
    return path.resolve().is_relative_to(examples)


def _format_validation_error(exc: ValidationError) -> list[str]:
    """Describe pydantic errors by location and message, never by input.

    Unknown field names are not echoed (a value pasted in as a key would
    otherwise be printed), and UUID parse messages, which quote the offending
    character, are replaced with a fixed message.

    Args:
        exc (ValidationError): The pydantic error.

    Returns:
        list[str]: One value-free description per error.
    """
    problems: list[str] = []
    for err in exc.errors(include_input=False, include_url=False):
        loc = err["loc"]
        message = err["msg"]
        if err["type"] == "extra_forbidden":
            loc = (*loc[:-1], "(unknown field)")
        elif err["type"].startswith("uuid"):
            message = "Input should be a valid UUID"
        # An entry error has loc ("entities", <index>, <field>, ...).
        if loc[:1] == ("entities",) and len(loc) > 1 and isinstance(loc[1], int):
            where = f"entry {loc[1] + 1}"
            field = ".".join(str(part) for part in loc[2:]) or "(entry)"
        else:
            where = "file"
            field = ".".join(str(part) for part in loc) or "(root)"
        problems.append(f"{where}: field '{field}': {message}")
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
    except (RecursionError, ValueError):
        raise SeedFileError(["seed file could not be parsed"]) from None
    try:
        return SeedFile.model_validate(raw)
    except ValidationError as exc:
        raise SeedFileError(_format_validation_error(exc)) from None


def _duplicates(values: list[tuple[int, Any]], label: str) -> list[str]:
    """Report entries whose non-null value repeats an earlier entry's.

    Args:
        values (list[tuple[int, Any]]): ``(1-based position, value)`` pairs.
        label (str): Field label for the problem text.

    Returns:
        list[str]: One value-free problem per repeated entry.
    """
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
    exactly one ``household`` entity and at least one ``individual``; and a
    real (non-synthetic) seed sets its own namespace, so its IDs cannot be
    derived from guessable keys and the public default namespace.

    Args:
        seed (SeedFile): The parsed seed.

    Returns:
        list[str]: Value-free problem descriptions; empty when valid.
    """
    numbered = list(enumerate(seed.entities, start=1))
    problems: list[str] = []
    if not seed.synthetic and seed.namespace == DEFAULT_ENTITY_NAMESPACE:
        problems.append(
            "file: field 'namespace': a non-synthetic seed must set its own "
            "private namespace UUID"
        )
    problems += _duplicates([(i, e.key) for i, e in numbered], "key")
    problems += _duplicates(
        [(i, resolve_entity_id(seed, e)) for i, e in numbered], "entity id"
    )
    problems += _duplicates([(i, e.ein) for i, e in numbered], "ein")
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
    names, so details added later through the UI are not wiped. A field the
    file sets to null explicitly is cleared.

    Args:
        entry (SeedEntity): The entry.

    Returns:
        dict[str, Any]: Column name to value.
    """
    fields = entry.model_dump(exclude_unset=True, exclude={"key", "id"})
    fields["entity_type"] = entry.entity_type
    return fields


@dataclass
class _SeedPlan:
    """Rows to insert and update, gathered before anything is written."""

    new_rows: list[Entity] = field(default_factory=list)
    changes: list[tuple[Entity, dict[str, Any]]] = field(default_factory=list)
    unchanged: int = 0
    skipped: list[int] = field(default_factory=list)


async def _plan_seed(session: AsyncSession, seed: SeedFile) -> _SeedPlan:
    """Compare every entry with the database and plan the writes.

    Args:
        session (AsyncSession): Database session.
        seed (SeedFile): A validated seed.

    Returns:
        _SeedPlan: New rows, per-row changed fields, and skip positions.
    """
    plan = _SeedPlan()
    for position, entry in enumerate(seed.entities, start=1):
        entity_id = resolve_entity_id(seed, entry)
        fields = _entity_fields(entry)
        # lazyload("*"): the seed reads columns only, so skip the eager
        # relationship loads the model declares.
        existing = await session.get(Entity, entity_id, options=[lazyload("*")])
        if existing is None:
            plan.new_rows.append(Entity(id=entity_id, **fields))
            continue
        if existing.deleted_at is not None:
            plan.skipped.append(position)
            continue
        diff = {
            name: value
            for name, value in fields.items()
            if getattr(existing, name) != value
        }
        if diff:
            plan.changes.append((existing, diff))
        else:
            plan.unchanged += 1
    return plan


def _release_unique_values(changes: list[tuple[Entity, dict[str, Any]]]) -> bool:
    """Null each unique value an existing row is about to change.

    Args:
        changes (list[tuple[Entity, dict[str, Any]]]): Planned updates.

    Returns:
        bool: True when at least one value was released (a flush is needed).
    """
    released = False
    for existing, diff in changes:
        for name in _UNIQUE_FIELDS:
            if name in diff and getattr(existing, name) is not None:
                setattr(existing, name, None)
                released = True
    return released


async def apply_seed(session: AsyncSession, seed: SeedFile) -> SeedResult:
    """Create or update every entity in the seed, keyed by stable UUID.

    The caller owns the transaction: commit on success, roll back on error.
    Unique values (EIN, Xero tenant ID) that change on existing rows are
    released and flushed first, so a value may move between seeded rows
    (including a swap) without a transient unique-index violation.

    Args:
        session (AsyncSession): Database session.
        seed (SeedFile): The parsed seed.

    Returns:
        SeedResult: Counts of created, updated, unchanged, and skipped rows.

    Raises:
        SeedFileError: If the seed fails :func:`validate_seed`.
    """
    problems = validate_seed(seed)
    if problems:
        raise SeedFileError(problems)

    # #EDGE: Data integrity - a value held by a live entity that is not in
    # the seed still violates a unique index at flush. The caller must roll
    # back and report the error without its parameters.
    # #VERIFY: tests/unit/test_seed_entities_cli.py checks an IntegrityError
    # is reported by class name only and nothing is committed.
    plan = await _plan_seed(session, seed)
    if _release_unique_values(plan.changes):
        await session.flush()
    for existing, diff in plan.changes:
        for name, value in diff.items():
            setattr(existing, name, value)
    for row in plan.new_rows:
        session.add(row)
    await session.flush()
    return SeedResult(
        created=len(plan.new_rows),
        updated=len(plan.changes),
        unchanged=plan.unchanged,
        skipped_entries=tuple(plan.skipped),
    )


def build_mapping(
    seed: SeedFile, omit_entries: frozenset[int] = frozenset()
) -> dict[str, Any]:
    """Build the private key-to-UUID mapping that downstream seeds read.

    Args:
        seed (SeedFile): The parsed seed.
        omit_entries (frozenset[int]): 1-based entry positions to leave out,
            such as entries whose entity is soft-deleted.

    Returns:
        dict[str, Any]: ``{"namespace": ..., "entities": {key: {"id",
        "entity_type", "xero_tenant_id"}}}``.
    """
    return {
        "namespace": str(seed.namespace),
        "entities": {
            entry.key: {
                "id": str(resolve_entity_id(seed, entry)),
                "entity_type": entry.entity_type.value,
                "xero_tenant_id": entry.xero_tenant_id,
            }
            for position, entry in enumerate(seed.entities, start=1)
            if position not in omit_entries
        },
    }


def write_mapping(path: Path, mapping: dict[str, Any]) -> None:
    """Write the mapping JSON atomically with owner-only permissions.

    The data goes to a temporary file that ``mkstemp`` creates in the
    destination directory (exclusive create, unpredictable name, mode 0600),
    is flushed to disk, and is then renamed over the destination. No reader
    sees a partial file, and the data is never readable by other users, even
    briefly. The owner-only mode is a POSIX guarantee; on Windows the file
    takes the directory's access control list instead.

    Args:
        path (Path): Destination outside this repository.
        mapping (dict[str, Any]): Output of :func:`build_mapping`.

    Raises:
        OSError: If the destination is a symbolic link, or the write fails.
            A failed write leaves no temporary file behind.
    """
    if path.is_symlink():
        msg = "refusing to write the mapping through a symbolic link"
        raise OSError(msg)
    parent = path.parent
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = json.dumps(mapping, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=parent)
    replaced = False
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        Path(tmp_name).replace(path)
        replaced = True
    finally:
        if not replaced:
            with contextlib.suppress(FileNotFoundError):
                Path(tmp_name).unlink()
