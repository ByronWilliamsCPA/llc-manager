"""Static checks for migration 316e25bc258b (individual and household types).

The upgrade and downgrade themselves need PostgreSQL (enum labels, partial
indexes); these checks keep the migration's hard-coded label lists in step
with ``EntityType`` without a database.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from llc_manager.models.entity import EntityType

pytestmark = pytest.mark.unit

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "20261005_120000_316e25bc258b_add_individual_household_entities.py"
)


def _constants(path: Path = MIGRATION) -> dict[str, object]:
    """Return a migration's module-level literal assignments.

    The file is parsed rather than imported: the repository's own
    ``alembic/`` directory shadows the alembic package on ``sys.path``.

    Args:
        path (Path): Migration file to parse.

    Returns:
        dict[str, object]: Name to literal value.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target, value = node.target.id, node.value
        elif (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            target, value = node.targets[0].id, node.value
        else:
            continue
        if value is not None:
            try:
                found[target] = ast.literal_eval(value)
            except ValueError:
                continue
    return found


def test_labels_cover_every_entity_type_name() -> None:
    constants = _constants()
    old = constants["_OLD_ENTITY_TYPES"]
    new = constants["_NEW_ENTITY_TYPES"]
    assert isinstance(old, tuple)
    assert isinstance(new, tuple)
    assert set(old) | set(new) == {member.name for member in EntityType}
    assert not set(old) & set(new)


def test_new_labels_are_the_personal_types() -> None:
    constants = _constants()
    new = constants["_NEW_ENTITY_TYPES"]
    in_use_sql = constants["_IN_USE_SQL"]
    assert isinstance(new, tuple)
    assert isinstance(in_use_sql, str)
    assert set(new) == {EntityType.INDIVIDUAL.name, EntityType.HOUSEHOLD.name}
    for label in new:
        assert f"'{label}'" in in_use_sql


def test_revision_chain() -> None:
    """The revision matches the file name and follows the previous migration."""
    constants = _constants()
    revision = constants["revision"]
    assert isinstance(revision, str)
    assert f"_{revision}_" in MIGRATION.name
    earlier = sorted(
        p for p in MIGRATION.parent.glob("*.py") if p.name < MIGRATION.name
    )
    assert earlier
    assert constants["down_revision"] == _constants(earlier[-1])["revision"]
