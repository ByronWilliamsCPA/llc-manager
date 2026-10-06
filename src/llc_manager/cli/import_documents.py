r"""Import documents into the store from an admin manifest.

Usage::

    python -m llc_manager.cli.import_documents \
        --manifest /private/manifest.csv \
        --source-root /private/scans \
        --entity-map /private/entity-map.json
    python -m llc_manager.cli.import_documents --validate-only ...

The manifest path comes from ``--manifest`` or ``LLC_MANAGER_DOCUMENT_MANIFEST``.
A manifest inside this source checkout is refused unless its name ends in
``.example.csv`` (the committed synthetic example). Files are copied to
``--documents-root`` (default: the ``LLC_MANAGER_DOCUMENTS_ROOT`` setting).

The command prints counts and value-free problems only; it never prints
titles, paths, or IDs. An unexpected failure prints only the exception class
name. ``--validate-only`` checks the manifest and the source files without
touching the database or the store (entity existence is checked when
importing).

Exit codes: 0 success, 1 validation problems, 2 usage or file errors
(including a manifest that cannot be opened or decoded), 3 unexpected
failure while importing (the transaction is rolled back and staged files are
deleted; if it happened while renaming files after the commit, re-run the
import to repair the store).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

from sqlalchemy.exc import SQLAlchemyError

from llc_manager.core.config import settings
from llc_manager.db.session import AsyncSessionLocal
from llc_manager.models.document import DocumentCategory
from llc_manager.services.document_import import (
    ImportProblemError,
    ManifestRow,
    SqlDocumentRepository,
    apply_import,
    load_entity_map,
    read_manifest,
)
from llc_manager.services.entity_seed import is_inside_repo

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

MANIFEST_ENV = "LLC_MANAGER_DOCUMENT_MANIFEST"
EXAMPLE_SUFFIX = ".example.csv"

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2
EXIT_FAILURE = 3


class _UsageError(Exception):
    """A command-line or path problem; the message holds no manifest values."""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m llc_manager.cli.import_documents",
        description="Import documents into the store from a manifest CSV.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help=f"Manifest CSV path (default: ${MANIFEST_ENV}).",
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=None,
        help="Directory relative file paths are resolved against "
        "(default: the manifest's directory).",
    )
    parser.add_argument(
        "--entity-map",
        type=Path,
        default=None,
        help="Key-to-UUID map written by seed_entities --mapping-out. It must "
        "be under the home directory (or $LLC_MANAGER_MAPPING_DIR when set).",
    )
    parser.add_argument(
        "--documents-root",
        type=Path,
        default=None,
        help="Store directory (default: the documents_root setting).",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Check the manifest and print counts; change nothing.",
    )
    return parser


def _resolve_manifest(args: argparse.Namespace) -> Path:
    raw: Path | None = args.manifest
    if raw is None and os.environ.get(MANIFEST_ENV):
        raw = Path(os.environ[MANIFEST_ENV])
    if raw is None:
        msg = f"pass --manifest or set {MANIFEST_ENV}"
        raise _UsageError(msg)
    manifest = raw.expanduser()
    if not manifest.is_file():
        msg = "manifest not found"
        raise _UsageError(msg)
    if is_inside_repo(manifest) and not manifest.name.endswith(EXAMPLE_SUFFIX):
        msg = (
            "manifest is inside the repository; real manifests must live "
            f"outside it (only a *{EXAMPLE_SUFFIX} file may be used from here)"
        )
        raise _UsageError(msg)
    return manifest


def _summarize(rows: list[ManifestRow], out: TextIO) -> None:
    print(f"rows={len(rows)}", file=out)
    by_category = Counter(row.category for row in rows)
    for category in DocumentCategory:
        if by_category[category]:
            print(f"category[{category.value}]={by_category[category]}", file=out)
    missing_consent = sum(
        1
        for row in rows
        if row.category is DocumentCategory.TAX_RETURNS and not row.consent_on_file
    )
    print(f"tax_returns_without_consent={missing_consent}", file=out)


async def _apply(
    session_factory: Callable[[], AsyncSession],
    rows: list[ManifestRow],
    documents_root: Path,
    out: TextIO,
) -> None:
    async with session_factory() as session:
        try:
            result = await apply_import(
                SqlDocumentRepository(session),
                rows,
                documents_root,
                commit=session.commit,
            )
        except Exception:
            await session.rollback()
            raise
    print(
        f"created={result.created} updated={result.updated} "
        f"unchanged={result.unchanged} duplicates={result.duplicates} "
        f"skipped_deleted={result.skipped_deleted}",
        file=out,
    )
    if result.duplicate_lines:
        lines = ",".join(str(number) for number in result.duplicate_lines)
        print(f"duplicate_lines={lines}", file=out)


def _import(
    session_factory: Callable[[], AsyncSession],
    rows: list[ManifestRow],
    documents_root: Path,
    out: TextIO,
) -> int:
    """Apply the import and map failures to exit codes without leaking values.

    Args:
        session_factory (Callable[[], AsyncSession]): Session factory.
        rows (list[ManifestRow]): Validated manifest rows.
        documents_root (Path): Store directory.
        out (TextIO): Output stream.

    Returns:
        int: Exit code.
    """
    try:
        asyncio.run(_apply(session_factory, rows, documents_root, out))
    except ImportProblemError as exc:
        for problem in exc.problems:
            print(f"problem: {problem}", file=out)
        return EXIT_INVALID
    except (OSError, SQLAlchemyError) as exc:
        # #CRITICAL: Security - the message of these exceptions can carry a
        # file path or bound SQL parameters (a title, a file name), so only the
        # class name is printed and the traceback is suppressed.
        # #VERIFY: tests/unit/test_import_documents_cli.py injects an OSError
        # and an IntegrityError carrying sentinel values and checks the output.
        print(f"error: import failed ({type(exc).__name__})", file=out)
        return EXIT_FAILURE
    return EXIT_OK


def _load_inputs(args: argparse.Namespace) -> tuple[Path, dict[str, UUID] | None]:
    """Resolve the manifest path and load the optional entity map.

    Args:
        args (argparse.Namespace): Parsed arguments.

    Returns:
        tuple[Path, dict[str, UUID] | None]: Manifest path and entity map.

    Raises:
        _UsageError: If the manifest or the entity map cannot be used.
    """
    manifest = _resolve_manifest(args)
    try:
        entity_map = load_entity_map(args.entity_map) if args.entity_map else None
    except ImportProblemError as exc:
        raise _UsageError("; ".join(exc.problems)) from None
    return manifest, entity_map


def main(
    argv: Sequence[str] | None = None,
    *,
    session_factory: Callable[[], AsyncSession] | None = None,
    out: TextIO | None = None,
) -> int:
    """Run the import command.

    Args:
        argv (Sequence[str] | None): Arguments; defaults to ``sys.argv[1:]``.
        session_factory (Callable[[], AsyncSession] | None): Session factory
            override for tests; defaults to the application's factory.
        out (TextIO | None): Output stream; defaults to stdout.

    Returns:
        int: Process exit code.
    """
    stream = out or sys.stdout
    args = _build_parser().parse_args(argv)
    try:
        manifest, entity_map = _load_inputs(args)
    except _UsageError as exc:
        print(f"error: {exc}", file=stream)
        return EXIT_USAGE

    source_root: Path = (args.source_root or manifest.parent).expanduser()
    report = read_manifest(manifest, source_root, entity_map)
    _summarize(report.rows, stream)
    for problem in report.problems:
        print(f"problem: {problem}", file=stream)
    if report.unreadable:
        return EXIT_USAGE
    if report.problems:
        return EXIT_INVALID
    if args.validate_only:
        return EXIT_OK

    documents_root: Path = (args.documents_root or settings.documents_root).expanduser()
    return _import(
        session_factory or AsyncSessionLocal, report.rows, documents_root, stream
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
