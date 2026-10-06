"""Seed production entities from a private seed file.

Usage::

    python -m llc_manager.cli.seed_entities --file /path/outside/repo/seed.json
    python -m llc_manager.cli.seed_entities --validate-only
    python -m llc_manager.cli.seed_entities --mapping-out /private/entity-map.json

The seed file path comes from ``--file`` or ``LLC_MANAGER_ENTITY_SEED_FILE``.
A file inside this source checkout is refused unless it is under
``data/examples/`` and declares ``"synthetic": true`` (the committed example
does). A synthetic file is applied to a database only with
``--allow-synthetic``. The command prints counts and value-free problems
only; it never prints names, IDs, or tenant IDs, and it reports a database
error by its class and constraint name only. See ``docs/guides/entity-seed.md``.

``--mapping-out`` is written after the database commit and leaves out entries
whose entity is soft-deleted. With ``--validate-only`` it is computed from the
file alone, so soft-deleted entities are not detected.

Exit codes:
    0: Success.
    1: The seed file is invalid (schema or cross-entry rules); nothing applied.
    2: Usage, path, or location error; nothing applied.
    3: Database error; the transaction was not committed.
    4: Applied, but some entries name a soft-deleted entity; those entries were
       left unchanged and left out of the mapping.
    5: Applied and committed, but the mapping file could not be written.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

from sqlalchemy.exc import SQLAlchemyError

from llc_manager.services.entity_seed import (
    SeedFile,
    SeedFileError,
    SeedResult,
    apply_seed,
    build_mapping,
    is_inside_repo,
    is_repo_example,
    load_seed_file,
    summarize_seed,
    validate_seed,
    write_mapping,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

SEED_FILE_ENV = "LLC_MANAGER_ENTITY_SEED_FILE"

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2
EXIT_DATABASE = 3
EXIT_SKIPPED = 4
EXIT_MAPPING = 5


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser.

    Returns:
        argparse.ArgumentParser: The parser.
    """
    parser = argparse.ArgumentParser(
        prog="python -m llc_manager.cli.seed_entities",
        description="Create or update entities from a private seed file.",
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help=f"Seed file path (default: ${SEED_FILE_ENV}).",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help=(
            "Check the file and print counts; do not touch the database. "
            "--mapping-out is still written, computed from the file alone."
        ),
    )
    parser.add_argument(
        "--mapping-out",
        type=Path,
        default=None,
        help=(
            "Write the key-to-UUID mapping JSON here (outside the repository). "
            "Owner-only permissions on POSIX systems."
        ),
    )
    parser.add_argument(
        "--allow-synthetic",
        action="store_true",
        help="Allow a file marked synthetic to be applied to the database.",
    )
    return parser


async def _apply_with(
    session_factory: Callable[[], AsyncSession], seed: SeedFile
) -> SeedResult:
    """Apply the seed in one transaction.

    Args:
        session_factory (Callable[[], AsyncSession]): Session factory.
        seed (SeedFile): A validated seed.

    Returns:
        SeedResult: Counts from :func:`apply_seed`.

    Raises:
        Exception: Any error from the database, after rolling back.
    """
    async with session_factory() as session:
        try:
            result = await apply_seed(session, seed)
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    return result


async def _apply(
    session_factory: Callable[[], AsyncSession] | None, seed: SeedFile
) -> SeedResult:
    """Apply the seed with the given factory, or the application's engine.

    The application's engine is imported here, not at module load, so
    ``--validate-only`` works without database settings; it is disposed
    before the event loop closes.

    Args:
        session_factory (Callable[[], AsyncSession] | None): Override for
            tests; None uses the application's session factory.
        seed (SeedFile): A validated seed.

    Returns:
        SeedResult: Counts from :func:`apply_seed`.
    """
    if session_factory is not None:
        return await _apply_with(session_factory, seed)
    from llc_manager.db.session import AsyncSessionLocal, async_engine

    try:
        return await _apply_with(AsyncSessionLocal, seed)
    finally:
        await async_engine.dispose()


def _describe_db_error(exc: BaseException) -> str:
    """Name a database error without its message or bound parameters.

    SQLAlchemy messages carry the statement's parameters (names, EINs, tenant
    IDs), so only the class name and, when the driver exposes it, the
    violated constraint's name are reported.

    Args:
        exc (BaseException): The error.

    Returns:
        str: ``ClassName`` or ``ClassName, constraint <name>``.
    """
    name = type(exc).__name__
    orig = getattr(exc, "orig", None)
    constraint = getattr(orig, "constraint_name", None) or getattr(
        getattr(orig, "__cause__", None), "constraint_name", None
    )
    if isinstance(constraint, str) and constraint:
        return f"{name}, constraint {constraint}"
    return name


class _UsageError(Exception):
    """A command-line or path problem; the message holds no seed values."""


def _resolve_paths(args: argparse.Namespace) -> tuple[Path, Path | None]:
    """Return the seed path and optional mapping path.

    Args:
        args (argparse.Namespace): Parsed arguments.

    Returns:
        tuple[Path, Path | None]: Seed path and mapping path.

    Raises:
        _UsageError: If no seed path is given, it does not exist, or the
            mapping path is inside the repository.
    """
    raw_path: Path | None = args.file
    if raw_path is None and os.environ.get(SEED_FILE_ENV):
        raw_path = Path(os.environ[SEED_FILE_ENV])
    if raw_path is None:
        msg = f"pass --file or set {SEED_FILE_ENV}"
        raise _UsageError(msg)
    seed_path = raw_path.expanduser()
    if not seed_path.is_file():
        msg = "seed file not found"
        raise _UsageError(msg)

    mapping_out: Path | None = args.mapping_out
    if mapping_out is not None:
        mapping_out = mapping_out.expanduser()
        if is_inside_repo(mapping_out):
            msg = "--mapping-out must be outside the repository"
            raise _UsageError(msg)
    return seed_path, mapping_out


def _check_seed_use(seed_path: Path, seed: SeedFile, args: argparse.Namespace) -> None:
    """Refuse a seed in the wrong place, or a synthetic seed on a database.

    Args:
        seed_path (Path): Path the seed was read from.
        seed (SeedFile): The parsed seed.
        args (argparse.Namespace): Parsed arguments.

    Raises:
        _UsageError: If a file inside the checkout is not a synthetic example
            under ``data/examples/``, or a synthetic file would be applied
            without ``--allow-synthetic``.
    """
    if is_inside_repo(seed_path) and not (
        seed.synthetic and is_repo_example(seed_path)
    ):
        msg = (
            "seed file is inside the repository; real seed data must live "
            "outside it (only a synthetic file under data/examples/ may be "
            "used from here)"
        )
        raise _UsageError(msg)
    if seed.synthetic and not args.validate_only and not args.allow_synthetic:
        msg = (
            "seed file is marked synthetic; pass --allow-synthetic to apply it "
            "to a database"
        )
        raise _UsageError(msg)


def _load(
    args: argparse.Namespace, stream: TextIO
) -> tuple[SeedFile, Path | None] | int:
    """Resolve paths, load the seed, and check every rule.

    Args:
        args (argparse.Namespace): Parsed arguments.
        stream (TextIO): Output stream for value-free messages.

    Returns:
        tuple[SeedFile, Path | None] | int: The seed and mapping path, or an
        exit code when the command must stop.
    """
    try:
        seed_path, mapping_out = _resolve_paths(args)
        seed = load_seed_file(seed_path)
        _check_seed_use(seed_path, seed, args)
    except _UsageError as exc:
        print(f"error: {exc}", file=stream)
        return EXIT_USAGE
    except SeedFileError as exc:
        for problem in exc.problems:
            print(f"problem: {problem}", file=stream)
        return EXIT_INVALID

    for name, count in summarize_seed(seed).items():
        print(f"{name}={count}", file=stream)
    problems = validate_seed(seed)
    for problem in problems:
        print(f"problem: {problem}", file=stream)
    if problems:
        return EXIT_INVALID
    return seed, mapping_out


def main(
    argv: Sequence[str] | None = None,
    *,
    session_factory: Callable[[], AsyncSession] | None = None,
    out: TextIO | None = None,
) -> int:
    """Run the seed command.

    Args:
        argv (Sequence[str] | None): Arguments; defaults to ``sys.argv[1:]``.
        session_factory (Callable[[], AsyncSession] | None): Session factory
            override for tests; defaults to the application's factory.
        out (TextIO | None): Output stream; defaults to stdout.

    Returns:
        int: Process exit code (see the module docstring).
    """
    stream = out or sys.stdout
    args = _build_parser().parse_args(argv)
    loaded = _load(args, stream)
    if isinstance(loaded, int):
        return loaded
    seed, mapping_out = loaded

    result: SeedResult | None = None
    if not args.validate_only:
        try:
            result = asyncio.run(_apply(session_factory, seed))
        except (SQLAlchemyError, OSError) as exc:
            print(
                f"error: database error ({_describe_db_error(exc)}); "
                "no changes were committed",
                file=stream,
            )
            return EXIT_DATABASE
        print(
            f"created={result.created} updated={result.updated} "
            f"unchanged={result.unchanged} skipped_deleted={result.skipped_deleted}",
            file=stream,
        )
    skipped = result.skipped_entries if result is not None else ()
    for position in skipped:
        print(
            f"problem: entry {position}: entity is soft-deleted; left unchanged "
            "and left out of the mapping",
            file=stream,
        )

    if mapping_out is not None:
        try:
            write_mapping(mapping_out, build_mapping(seed, frozenset(skipped)))
        except OSError:
            committed = (
                " (database changes were committed)" if result is not None else ""
            )
            print(f"error: mapping file could not be written{committed}", file=stream)
            return EXIT_MAPPING
        print("mapping written", file=stream)

    return EXIT_SKIPPED if skipped else EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
