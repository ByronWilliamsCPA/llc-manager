"""Manifest-driven document import into the document store.

An admin manifest (CSV) lists the files to import with their metadata. The
import copies each file to ``{documents_root}/{document_id}{extension}``,
records its SHA-256, skips exact duplicates, and creates or updates the
``documents`` row. The manifest format is described in
``docs/guides/document-manifest.md``.

Document IDs are stable: ``uuid5(DOCUMENT_NAMESPACE, <file path as written
relative to the source root>)``. Re-importing the same manifest therefore
updates rows in place instead of creating new ones.

Problems are reported by manifest line and column name only; no cell value,
title, or path is ever included.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Protocol
from uuid import UUID, uuid5

from sqlalchemy import select

from llc_manager.models.document import Document, DocumentCategory, DocumentType
from llc_manager.models.entity import Entity
from llc_manager.services.document_store import mime_for_source, stored_name

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.ext.asyncio import AsyncSession

DOCUMENT_NAMESPACE = UUID("b1f8a6f4-1c0e-4f43-9a52-7d0c2e6b9a10")

REQUIRED_COLUMNS = ("file", "entity", "document_type", "category", "title")
OPTIONAL_COLUMNS = (
    "document_date",
    "effective_date",
    "confidential",
    "consent_on_file",
)
ALL_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

_TRUE = {"true", "yes", "y", "1"}
_FALSE = {"false", "no", "n", "0", ""}
_CATEGORY_BY_LOWER = {c.value.lower(): c for c in DocumentCategory}
_TYPE_BY_LOWER = {t.value: t for t in DocumentType}
_CHUNK = 1024 * 1024
_MAX_TITLE = 255  # Document.title is String(255)


@dataclass(frozen=True)
class ManifestRow:
    """One validated manifest row.

    Attributes:
        line (int): Line number in the manifest (header is line 1).
        document_id (UUID): Stable document ID.
        source (Path): Resolved source file.
        mime_type (str): Store MIME type for the source file.
        entity_id (UUID): Owning entity.
        document_type (DocumentType): Document type.
        category (DocumentCategory): Category.
        title (str): Title.
        document_date (date | None): Document date.
        effective_date (date | None): Effective date.
        is_confidential (bool): Confidential flag.
        consent_on_file (bool): Tax-return consent flag.
    """

    line: int
    document_id: UUID
    source: Path
    mime_type: str
    entity_id: UUID
    document_type: DocumentType
    category: DocumentCategory
    title: str
    document_date: date | None
    effective_date: date | None
    is_confidential: bool
    consent_on_file: bool


@dataclass
class ManifestReport:
    """Result of reading a manifest: valid rows plus value-free problems.

    Attributes:
        rows (list[ManifestRow]): Rows that passed validation.
        problems (list[str]): Problems, by line and column name only.
    """

    rows: list[ManifestRow] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ImportResult:
    """Counts from an import. Holds no values.

    Attributes:
        created (int): New documents stored.
        updated (int): Existing documents whose file or metadata changed.
        unchanged (int): Existing documents already matching the manifest.
        duplicates (int): New rows skipped because identical bytes are
            already stored under another document.
        skipped_deleted (int): Rows whose document is soft-deleted.
    """

    created: int = 0
    updated: int = 0
    unchanged: int = 0
    duplicates: int = 0
    skipped_deleted: int = 0


class ImportProblemError(Exception):
    """The import cannot proceed; ``problems`` explains why without values.

    Args:
        problems (list[str]): Value-free problem descriptions.

    Attributes:
        problems (list[str]): Value-free problem descriptions.
    """

    problems: list[str]

    def __init__(self, problems: list[str]) -> None:
        super().__init__(f"{len(problems)} problem(s) prevent the import")
        self.problems = problems


class DocumentRepository(Protocol):
    """Database operations the import needs."""

    async def live_entity_ids(self, ids: set[UUID]) -> set[UUID]:
        """Return the subset of ``ids`` that are non-deleted entities."""
        ...

    async def get(self, document_id: UUID) -> Document | None:
        """Return a document by ID, including soft-deleted ones."""
        ...

    async def live_id_with_sha(self, sha256: str) -> UUID | None:
        """Return the ID of a non-deleted document with these bytes, if any."""
        ...

    def add(self, document: Document) -> None:
        """Stage a new document."""
        ...

    async def flush(self) -> None:
        """Flush staged changes."""
        ...


class SqlDocumentRepository:
    """:class:`DocumentRepository` backed by an ``AsyncSession``.

    Args:
        session (AsyncSession): Database session; the caller owns the
            transaction.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def live_entity_ids(self, ids: set[UUID]) -> set[UUID]:
        """Return the subset of ``ids`` that are non-deleted entities.

        Args:
            ids (set[UUID]): Candidate entity IDs.

        Returns:
            set[UUID]: IDs that exist and are not soft-deleted.
        """
        if not ids:
            return set()
        result = await self._session.execute(
            select(Entity.id).where(Entity.id.in_(ids), Entity.deleted_at.is_(None))
        )
        return set(result.scalars().all())

    async def get(self, document_id: UUID) -> Document | None:
        """Return a document by ID, including soft-deleted ones.

        Args:
            document_id (UUID): Document ID.

        Returns:
            Document | None: The document, if it exists.
        """
        return await self._session.get(Document, document_id)

    async def live_id_with_sha(self, sha256: str) -> UUID | None:
        """Return the ID of a non-deleted document with these bytes, if any.

        Args:
            sha256 (str): Hex SHA-256.

        Returns:
            UUID | None: A matching document ID, or None.
        """
        result = await self._session.execute(
            select(Document.id)
            .where(Document.sha256 == sha256, Document.deleted_at.is_(None))
            .limit(1)
        )
        return result.scalars().first()

    def add(self, document: Document) -> None:
        """Stage a new document.

        Args:
            document (Document): The new row.
        """
        self._session.add(document)

    async def flush(self) -> None:
        """Flush staged changes to the database."""
        await self._session.flush()


def document_id_for(file_key: str) -> UUID:
    """Return the stable document ID for a manifest file key.

    Args:
        file_key (str): The file path as written, relative to the source
            root, in POSIX form.

    Returns:
        UUID: ``uuid5(DOCUMENT_NAMESPACE, file_key)``.
    """
    return uuid5(DOCUMENT_NAMESPACE, file_key)


def load_entity_map(path: Path) -> dict[str, UUID]:
    """Load the key-to-UUID map written by the entity seed command.

    Args:
        path (Path): Mapping JSON (``{"entities": {key: {"id": ...}}}``).

    Returns:
        dict[str, UUID]: Entity key to entity ID.

    Raises:
        ImportProblemError: If the file is missing or malformed.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        entities = raw["entities"]
        return {str(key): UUID(str(value["id"])) for key, value in entities.items()}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise ImportProblemError(["entity map is missing or malformed"]) from None


class _RowError(Exception):
    """A single cell failed validation; the message names the column only."""


def _parse_bool(value: str, column: str) -> bool:
    lowered = value.strip().lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    msg = f"column '{column}': expected true or false"
    raise _RowError(msg)


def _parse_date(value: str, column: str) -> date | None:
    if not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        msg = f"column '{column}': expected a YYYY-MM-DD date"
        raise _RowError(msg) from None


def _parse_entity(value: str, entity_map: dict[str, UUID]) -> UUID:
    text = value.strip()
    if text in entity_map:
        return entity_map[text]
    try:
        return UUID(text)
    except ValueError:
        msg = "column 'entity': not a UUID or a key in the entity map"
        raise _RowError(msg) from None


def _parse_source(value: str, source_root: Path) -> tuple[str, Path, str]:
    text = value.strip()
    if not text:
        msg = "column 'file': empty"
        raise _RowError(msg)
    written = Path(text)
    source = (written if written.is_absolute() else source_root / written).resolve()
    if not source.is_file():
        msg = "column 'file': file not found"
        raise _RowError(msg)
    mime = mime_for_source(source)
    if mime is None:
        msg = "column 'file': unsupported file type"
        raise _RowError(msg)
    try:
        key = source.relative_to(source_root.resolve()).as_posix()
    except ValueError:
        key = source.as_posix()
    return key, source, mime


def _parse_row(
    line: int, raw: dict[str, str], source_root: Path, entity_map: dict[str, UUID]
) -> ManifestRow:
    def cell(name: str) -> str:
        return (raw.get(name) or "").strip()

    key, source, mime = _parse_source(cell("file"), source_root)
    entity_id = _parse_entity(cell("entity"), entity_map)

    document_type = _TYPE_BY_LOWER.get(cell("document_type").lower())
    if document_type is None:
        msg = "column 'document_type': unknown document type"
        raise _RowError(msg)
    category = _CATEGORY_BY_LOWER.get(cell("category").lower())
    if category is None:
        msg = "column 'category': unknown category"
        raise _RowError(msg)

    title = cell("title")
    if not 1 <= len(title) <= _MAX_TITLE:
        msg = "column 'title': must be 1 to 255 characters"
        raise _RowError(msg)

    consent = _parse_bool(cell("consent_on_file"), "consent_on_file")
    if consent and category is not DocumentCategory.TAX_RETURNS:
        msg = (
            "column 'consent_on_file': true is only valid for the Tax Returns category"
        )
        raise _RowError(msg)

    return ManifestRow(
        line=line,
        document_id=document_id_for(key),
        source=source,
        mime_type=mime,
        entity_id=entity_id,
        document_type=document_type,
        category=category,
        title=title,
        document_date=_parse_date(cell("document_date"), "document_date"),
        effective_date=_parse_date(cell("effective_date"), "effective_date"),
        is_confidential=_parse_bool(cell("confidential"), "confidential"),
        consent_on_file=consent,
    )


def _check_header(fieldnames: Iterable[str] | None) -> list[str]:
    names = [n.strip() for n in fieldnames or []]
    problems = [
        f"header: missing column '{c}'" for c in REQUIRED_COLUMNS if c not in names
    ]
    problems += [f"header: unknown column '{n}'" for n in names if n not in ALL_COLUMNS]
    return problems


def read_manifest(
    manifest: Path, source_root: Path, entity_map: dict[str, UUID] | None = None
) -> ManifestReport:
    """Read and validate a manifest without touching the database.

    Args:
        manifest (Path): Manifest CSV (UTF-8, header row required).
        source_root (Path): Directory that relative ``file`` paths are
            resolved against.
        entity_map (dict[str, UUID] | None): Entity key to UUID, from the
            entity seed's mapping file.

    Returns:
        ManifestReport: Valid rows and value-free problems.
    """
    report = ManifestReport()
    keys = entity_map or {}
    try:
        handle = manifest.open(encoding="utf-8-sig", newline="")
    except OSError:
        report.problems.append("manifest could not be read")
        return report
    with handle:
        reader = csv.DictReader(handle)
        report.problems += _check_header(reader.fieldnames)
        if report.problems:
            return report
        seen: dict[UUID, int] = {}
        for raw in reader:
            line = reader.line_num
            try:
                row = _parse_row(line, raw, source_root, keys)
            except _RowError as exc:
                report.problems.append(f"line {line}: {exc}")
                continue
            if row.document_id in seen:
                report.problems.append(
                    f"line {line}: column 'file': same file as line {seen[row.document_id]}"
                )
                continue
            seen[row.document_id] = line
            report.rows.append(row)
    if not report.rows and not report.problems:
        report.problems.append("manifest has no rows")
    return report


def sha256_file(path: Path) -> str:
    """Return the hex SHA-256 of a file, read in chunks.

    Args:
        path (Path): File to hash.

    Returns:
        str: Hex digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def copy_into_store(source: Path, root: Path, document_id: UUID, mime_type: str) -> str:
    """Copy a file into the store atomically and return its stored name.

    Args:
        source (Path): Source file.
        root (Path): Documents root.
        document_id (UUID): Document ID.
        mime_type (str): Store MIME type.

    Returns:
        str: The stored file name, relative to ``root``.
    """
    root.mkdir(parents=True, exist_ok=True)
    name = stored_name(document_id, mime_type)
    tmp = root / f".{name}.tmp"
    shutil.copyfile(source, tmp)
    tmp.chmod(0o640)
    tmp.replace(root / name)
    return name


def _metadata(row: ManifestRow) -> dict[str, object]:
    return {
        "entity_id": row.entity_id,
        "document_type": row.document_type,
        "category": row.category,
        "title": row.title,
        "document_date": row.document_date,
        "effective_date": row.effective_date,
        "is_confidential": row.is_confidential,
        "consent_on_file": row.consent_on_file,
    }


def _file_fields(row: ManifestRow, sha: str, stored: str) -> dict[str, object]:
    return {
        "sha256": sha,
        "mime_type": row.mime_type,
        "file_size": row.source.stat().st_size,
        "file_name": row.source.name[:_MAX_TITLE],
        "file_path": stored,
    }


async def apply_import(
    repo: DocumentRepository, rows: list[ManifestRow], documents_root: Path
) -> ImportResult:
    """Copy files into the store and create or update their rows.

    The caller owns the transaction. Every row's entity must exist first;
    otherwise nothing is imported.

    Args:
        repo (DocumentRepository): Database operations.
        rows (list[ManifestRow]): Rows from :func:`read_manifest`.
        documents_root (Path): Documents root directory.

    Returns:
        ImportResult: Counts by outcome.

    Raises:
        ImportProblemError: If any row names an entity that does not exist.
    """
    live = await repo.live_entity_ids({r.entity_id for r in rows})
    missing = [
        f"line {r.line}: column 'entity': no such entity"
        for r in rows
        if r.entity_id not in live
    ]
    if missing:
        raise ImportProblemError(missing)

    counts = {
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "duplicates": 0,
        "skipped_deleted": 0,
    }
    stored_this_run: set[str] = set()
    for row in rows:
        sha = sha256_file(row.source)
        existing = await repo.get(row.document_id)
        if existing is None:
            if sha in stored_this_run or await repo.live_id_with_sha(sha) is not None:
                counts["duplicates"] += 1
                continue
            stored = copy_into_store(
                row.source, documents_root, row.document_id, row.mime_type
            )
            repo.add(
                Document(
                    id=row.document_id,
                    **_metadata(row),
                    **_file_fields(row, sha, stored),
                )
            )
            stored_this_run.add(sha)
            counts["created"] += 1
            continue
        if existing.deleted_at is not None:
            counts["skipped_deleted"] += 1
            continue

        wanted = _metadata(row)
        stored_file = documents_root / stored_name(row.document_id, row.mime_type)
        if (
            existing.sha256 != sha
            or existing.mime_type != row.mime_type
            or not stored_file.is_file()
        ):
            stored = copy_into_store(
                row.source, documents_root, row.document_id, row.mime_type
            )
            wanted.update(_file_fields(row, sha, stored))
        changed = False
        for name, value in wanted.items():
            if getattr(existing, name) != value:
                setattr(existing, name, value)
                changed = True
        stored_this_run.add(sha)
        counts["updated" if changed else "unchanged"] += 1

    await repo.flush()
    return ImportResult(**counts)
