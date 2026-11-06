"""Static checks for migration 0e0121ec4817 (document store fields).

The upgrade and downgrade need PostgreSQL. The file is parsed rather than
imported because the repository's own ``alembic/`` directory shadows the
alembic package on ``sys.path``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from llc_manager.models.document import DocumentType

pytestmark = pytest.mark.unit

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "20261005_130000_0e0121ec4817_add_document_store_fields.py"
)


def _tree() -> ast.Module:
    return ast.parse(MIGRATION.read_text(encoding="utf-8"))


def _literal(name: str) -> object:
    for node in _tree().body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
        ):
            return ast.literal_eval(node.value)
    pytest.fail(f"{name} not found in migration")


def test_document_type_labels_cover_the_enum() -> None:
    new = _literal("_NEW_DOCUMENT_TYPES")
    old = _literal("_OLD_DOCUMENT_TYPES")
    assert isinstance(new, tuple)
    assert isinstance(old, tuple)
    assert set(new) | set(old) == {member.name for member in DocumentType}
    assert not set(new) & set(old)


def test_downgrade_guard_runs_before_anything_is_dropped() -> None:
    downgrade = next(
        node
        for node in _tree().body
        if isinstance(node, ast.FunctionDef) and node.name == "downgrade"
    )
    calls = [
        n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
        for n in ast.walk(downgrade)
        if isinstance(n, ast.Call)
    ]
    assert "_refuse_if_new_types_in_use" in calls
    guard_line = next(
        n.lineno
        for n in ast.walk(downgrade)
        if isinstance(n, ast.Call)
        and getattr(n.func, "id", "") == "_refuse_if_new_types_in_use"
    )
    drop_lines = [
        n.lineno
        for n in ast.walk(downgrade)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr.startswith("drop_")
    ]
    assert drop_lines
    assert guard_line < min(drop_lines)


def test_in_use_sql_names_exactly_the_new_labels() -> None:
    new = _literal("_NEW_DOCUMENT_TYPES")
    sql = _literal("_IN_USE_SQL")
    assert isinstance(new, tuple)
    assert isinstance(sql, str)
    listed = re.findall(r"'([A-Z_]+)'", sql)
    assert sorted(listed) == sorted(new)
