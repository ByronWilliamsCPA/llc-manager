#!/usr/bin/env python3
"""Check that files using | union syntax have 'from __future__ import annotations'.

This script enforces a code quality standard to ensure that Python files using
the modern | union type syntax (introduced in Python 3.10) also include the
future annotations import for clarity and consistency.

NOTE: Python 3.14 deprecates 'from __future__ import annotations' (PEP 649),
but it will remain functional until at least Python 3.13 EOL in 2029. This
script will be updated when the ecosystem transitions to PEP 649's deferred
annotation evaluation. For now, continue using the future import for Python
3.10+ compatibility.

Usage:
    python scripts/check_type_hints.py [--fix]

Exit codes:
    0: All checks passed
    1: Violations found (or other errors)
"""

import argparse
import ast
import re
import sys
from pathlib import Path


class UnionSyntaxVisitor(ast.NodeVisitor):
    """AST visitor to detect | union syntax in type annotations."""

    def __init__(self) -> None:
        self.has_union_syntax = False

    def visit_BinOp(self, node: ast.BinOp) -> None:
        """Visit binary operations to detect | in type contexts."""
        if isinstance(node.op, ast.BitOr):
            # Check if this is likely a type annotation context
            # This is a heuristic - it will catch most cases
            self.has_union_syntax = True
        self.generic_visit(node)

    def visit_arg(self, node: ast.arg) -> None:
        """Visit function arguments with annotations."""
        if node.annotation:
            self.visit(node.annotation)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Visit annotated assignments."""
        if node.annotation:
            self.visit(node.annotation)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definitions with return annotations."""
        if node.returns:
            self.visit(node.returns)
        for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
            if arg.annotation:
                self.visit(arg.annotation)
        if node.args.vararg and node.args.vararg.annotation:
            self.visit(node.args.vararg.annotation)
        if node.args.kwarg and node.args.kwarg.annotation:
            self.visit(node.args.kwarg.annotation)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit async function definitions."""
        self.visit_FunctionDef(node)  # type: ignore[arg-type]


def _is_future_annotations_import(node: ast.AST) -> bool:
    """Check if an AST node is 'from __future__ import annotations'."""
    if not isinstance(node, ast.ImportFrom):
        return False
    if node.module != "__future__":
        return False
    return any(alias.name == "annotations" for alias in node.names)


def has_future_annotations_import(content: str) -> bool:
    """Check if file has 'from __future__ import annotations'."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return False

    return any(_is_future_annotations_import(node) for node in ast.walk(tree))


def has_union_pipe_syntax(content: str) -> bool:
    """Check if file uses | union syntax in type hints.

    Uses multiple detection methods:
    1. AST parsing to detect BinOp with BitOr in annotation contexts
    2. Regex pattern matching for common type hint patterns
    """
    # Method 1: AST-based detection
    try:
        tree = ast.parse(content)
        visitor = UnionSyntaxVisitor()
        visitor.visit(tree)
        if visitor.has_union_syntax:
            return True
    except SyntaxError:
        pass

    # Method 2: Regex patterns for common type hint usage
    # Match patterns like: ": int | str", "-> bool | None", "[int | float]"
    patterns = [
        r":\s*\w+\s*\|\s*\w+",  # : Type | Type
        r"->\s*\w+\s*\|\s*\w+",  # -> Type | Type
        r"\[\s*\w+\s*\|\s*\w+",  # [Type | Type
        r"=\s*\w+\s*\|\s*\w+",  # = Type | Type (in function params)
    ]

    for pattern in patterns:
        if re.search(pattern, content):
            return True

    return False


def check_file(file_path: Path) -> tuple[bool, str]:
    """Check a single Python file for union syntax compliance.

    Returns:
        (is_compliant, message): Tuple indicating compliance and message
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        return False, f"Error reading file: {e}"

    has_union = has_union_pipe_syntax(content)
    has_import = has_future_annotations_import(content)

    if has_union and not has_import:
        return False, "Uses | union syntax without 'from __future__ import annotations'"

    return True, "OK"


def _get_shebang_offset(lines: list[str]) -> int:
    """Return 1 if file starts with shebang, else 0."""
    if lines and lines[0].startswith("#!"):
        return 1
    return 0


def _get_docstring_end_line(tree: ast.Module) -> int:
    """Return the end line of module docstring, or 0 if none."""
    if not tree.body:
        return 0
    first_node = tree.body[0]
    if isinstance(first_node, ast.Expr) and isinstance(first_node.value, ast.Constant):
        return first_node.end_lineno or 0
    return 0


def _find_import_insert_index(lines: list[str], start_index: int) -> int:
    """Find the line index where the future import should be inserted."""
    for i, line in enumerate(lines[start_index:], start=start_index):
        stripped = line.strip()
        if stripped.startswith("from __future__ import"):
            continue
        if stripped and not stripped.startswith("#"):
            return i
    return start_index


def _insert_import_line(lines: list[str], insert_index: int) -> list[str]:
    """Insert the future annotations import at the specified index."""
    import_line = "from __future__ import annotations\n"
    has_preceding_blank = insert_index > 0 and not lines[insert_index - 1].strip()

    if has_preceding_blank:
        lines.insert(insert_index, import_line)
    else:
        lines.insert(insert_index, import_line)
        lines.insert(insert_index + 1, "\n")

    return lines


def _is_path_within_cwd(file_path: Path) -> bool:
    """Check if file path is within current working directory."""
    return file_path.resolve().is_relative_to(Path.cwd())


def add_future_import(file_path: Path) -> bool:
    """Add 'from __future__ import annotations' to a file.

    Returns:
        True if the import was added, False otherwise
    """
    try:
        content = file_path.read_text(encoding="utf-8")
        lines = content.splitlines(keepends=True)
        tree = ast.parse(content)

        # Calculate insertion point
        insert_index = _get_shebang_offset(lines)
        insert_index = max(insert_index, _get_docstring_end_line(tree))
        insert_index = _find_import_insert_index(lines, insert_index)

        # Insert the import
        lines = _insert_import_line(lines, insert_index)

        # Security: Validate file path is within expected directory
        if not _is_path_within_cwd(file_path):
            print(
                f"Security: Path {file_path} is outside current directory",
                file=sys.stderr,
            )
            return False

        file_path.write_text("".join(lines), encoding="utf-8")
        return True
    except Exception as e:
        print(f"Error adding import to {file_path}: {e}", file=sys.stderr)
        return False


def _create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        description="Check for | union syntax with future annotations import"
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Automatically add 'from __future__ import annotations' to files",
    )
    parser.add_argument(
        "--src-dir",
        type=Path,
        default=Path("src"),
        help="Source directory to check (default: src)",
    )
    parser.add_argument(
        "--include-tests",
        action="store_true",
        help="Also check test files",
    )
    return parser


def _collect_python_files(src_dir: Path, include_tests: bool) -> list[Path]:
    """Collect all Python files to check, excluding __pycache__."""
    python_files: list[Path] = []

    if src_dir.exists():
        python_files.extend(src_dir.rglob("*.py"))

    if include_tests:
        tests_dir = Path("tests")
        if tests_dir.exists():
            python_files.extend(tests_dir.rglob("*.py"))

    return [f for f in python_files if "__pycache__" not in str(f)]


def _handle_non_compliant_file(
    file_path: Path,
    message: str,
    fix: bool,
    violations: list[tuple[Path, str]],
    fixed: list[Path],
) -> None:
    """Handle a non-compliant file by either fixing it or recording the violation."""
    if not fix:
        violations.append((file_path, message))
        print(f"✗ {file_path}: {message}", file=sys.stderr)
        return

    if add_future_import(file_path):
        fixed.append(file_path)
        print(f"✓ Fixed: {file_path}")
    else:
        violations.append((file_path, message))
        print(f"✗ Failed to fix: {file_path}: {message}", file=sys.stderr)


def _print_summary(violations: list[tuple[Path, str]], fixed: list[Path]) -> int:
    """Print summary and return exit code."""
    print()
    if violations:
        print(f"Found {len(violations)} violation(s):")
        for file_path, message in violations:
            print(f"  - {file_path}: {message}")
        print()
        print("Run with --fix to automatically add the import")
        return 1
    if fixed:
        print(f"Fixed {len(fixed)} file(s)")
        return 0
    print("All files compliant ✓")
    return 0


def main() -> int:
    """Main entry point."""
    parser = _create_argument_parser()
    args = parser.parse_args()

    python_files = _collect_python_files(args.src_dir, args.include_tests)

    if not python_files:
        print(f"No Python files found in {args.src_dir}", file=sys.stderr)
        return 1

    violations: list[tuple[Path, str]] = []
    fixed: list[Path] = []

    for file_path in python_files:
        is_compliant, message = check_file(file_path)
        if not is_compliant:
            _handle_non_compliant_file(file_path, message, args.fix, violations, fixed)

    return _print_summary(violations, fixed)


if __name__ == "__main__":
    sys.exit(main())
