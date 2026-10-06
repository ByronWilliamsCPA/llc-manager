"""Seed production entities from a private seed file.

Usage::

    python -m llc_manager.cli.seed_entities --file /path/outside/repo/seed.json
    python -m llc_manager.cli.seed_entities --validate-only
    python -m llc_manager.cli.seed_entities --mapping-out /private/entity-map.json

The seed file path comes from ``--file`` or ``LLC_MANAGER_ENTITY_SEED_FILE``.
A file inside this source checkout is refused unless it declares
``"synthetic": true`` (the committed example does). The command prints counts
and value-free problems only; it never prints names, IDs, or tenant IDs.

Exit codes: 0 success, 1 validation problems, 2 usage or file errors.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

from llc_manager.db.session import AsyncSessionLocal
from llc_manager.services.entity_seed import (
    SeedFile,
    SeedFileError,
    apply_seed,
    build_mapping,
    is_inside_repo,
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


def _build_parser() -> argparse.ArgumentParser:
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
        help="Check the file and print counts; do not touch the database.",
    )
    parser.add_argument(
        "--mapping-out",
        type=Path,
        default=None,
        help="Write the key-to-UUID mapping JSON here (outside the repository).",
    )
    return parser


async def _apply(
    session_factory: Callable[[], AsyncSession],
    seed: SeedFile,
    out: TextIO,
) -> None:
    async with session_factory() as session:
        try:
            result = await apply_seed(session, seed)
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    print(
        f"created={result.created} updated={result.updated} "
        f"unchanged={result.unchanged} skipped_deleted={result.skipped_deleted}",
        file=out,
    )


class _UsageError(Exception):
    """A command-line or path problem; the message holds no seed values."""


def _resolve_paths(args: argparse.Namespace) -> tuple[Path, Path | None]:
    """Return the seed path and optional mapping path, or raise _UsageError."""
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


def _check_location(seed_path: Path, seed: SeedFile) -> None:
    """Refuse a real (non-synthetic) seed file stored inside the checkout."""
    if is_inside_repo(seed_path) and not seed.synthetic:
        msg = (
            "seed file is inside the repository; real seed data must live "
            "outside it (only a file marked synthetic may be used from here)"
        )
        raise _UsageError(msg)


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
        int: Process exit code.
    """
    stream = out or sys.stdout
    args = _build_parser().parse_args(argv)
    try:
        seed_path, mapping_out = _resolve_paths(args)
        seed = load_seed_file(seed_path)
        _check_location(seed_path, seed)
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

    if not args.validate_only:
        asyncio.run(_apply(session_factory or AsyncSessionLocal, seed, stream))

    if mapping_out is not None:
        write_mapping(mapping_out, build_mapping(seed))
        print("mapping written", file=stream)

    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
