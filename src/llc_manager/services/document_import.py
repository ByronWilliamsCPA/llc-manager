"""Manifest-driven document import into the document store.

An admin manifest (CSV) lists the files to import with their metadata. The
import copies each file to ``{documents_root}/{document_id}{extension}``,
records its SHA-256, skips exact duplicates, and creates or updates the
``documents`` row. The manifest format is described in
``docs/guides/documents.md``.

Document IDs are stable: ``uuid5(DOCUMENT_NAMESPACE, <file path relative to
the source root>)``, taken after ``..`` segments and symlinks are resolved.
Every file must live under the source root. Re-importing the same manifest
therefore updates rows in place instead of creating new ones.

Files are staged under temporary names and renamed into place only after the
database transaction commits, so a failed import leaves the store as it was.

Problems are reported by manifest line and column name or position only; no
cell value, title, or path is ever included.
"""

from __future__ import annotations

import contextlib
import csv
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Protocol
from uuid import UUID, uuid5

from sqlalchemy import select

from llc_manager.models.document import Document, DocumentCategory, DocumentType
from llc_manager.models.entity import Entity
from llc_manager.services.document_store import mime_for_source, stored_name
from llc_manager.services.entity_seed import confine_path, mapping_base_dir

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterable

    from sqlalchemy.ext.asyncio import AsyncSession

# #CRITICAL: Data integrity - this namespace turns a relative file path into a
# document ID. Changing even one digit re-mints every ID: re-imports create
# duplicates and IDs held by other services stop resolving. The value is public
# on purpose: document IDs are identifiers, not secrets (every read is behind
# the API key), unlike the private entity-seed namespace.
# #VERIFY: tests/unit/test_document_import.py pins golden IDs for this value.
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
_MAX_FILE_NAME = 255  # Document.file_name is String(255)
_EXTRA_CELLS_KEY = "__extra_cells__"  # csv.DictReader restkey for long rows
_STORED_MODE = 0o640


@dataclass(frozen=True)
class ManifestRow:
    """One validated manifest row.

    Attributes:
        line (int): Line number where the record ends in the manifest (the
            header is line 1; a quoted multi-line cell moves it down).
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
        problems (list[str]): Problems, by line and column name or position
            only.
        unreadable (bool): True when the manifest file itself could not be
            opened or decoded (a file error, not a validation problem).
    """

    rows: list[ManifestRow] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    unreadable: bool = False


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
        duplicate_lines (tuple[int, ...]): Manifest line numbers of the
            skipped duplicates, so a skipped row is never silent.
    """

    created: int = 0
    updated: int = 0
    unchanged: int = 0
    duplicates: int = 0
    skipped_deleted: int = 0
    duplicate_lines: tuple[int, ...] = ()


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
        raise NotImplementedError

    async def get(self, document_id: UUID) -> Document | None:
        """Return a document by ID, including soft-deleted ones."""
        raise NotImplementedError

    async def live_id_with_sha(self, sha256: str) -> UUID | None:
        """Return the ID of a non-deleted document with these bytes, if any."""
        raise NotImplementedError

    def add(self, document: Document) -> None:
        """Stage a new document."""

    async def flush(self) -> None:
        """Flush staged changes."""


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


def load_entity_map(path: Path, base_dir: Path | None = None) -> dict[str, UUID]:
    """Load the key-to-UUID map written by the entity seed command.

    The file must resolve inside ``base_dir`` (default
    :func:`~llc_manager.services.entity_seed.mapping_base_dir`), the same
    directory the seed command is confined to when it writes the map, so a
    crafted path cannot make the import read an arbitrary file.

    Args:
        path (Path): Mapping JSON (``{"entities": {key: {"id": ...}}}``).
        base_dir (Path | None): Directory the file must be inside.

    Returns:
        dict[str, UUID]: Entity key to entity ID.

    Raises:
        ImportProblemError: If the file is outside the allowed directory,
            missing, or malformed.
    """
    try:
        target = confine_path(path, base_dir or mapping_base_dir())
    except OSError:
        raise ImportProblemError(
            ["entity map is outside the allowed mapping directory"]
        ) from None
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
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
    """Resolve a manifest ``file`` cell to its ID key, path, and MIME type.

    Args:
        value (str): The cell text.
        source_root (Path): Directory that the file must live under.

    Returns:
        tuple[str, Path, str]: POSIX path relative to the source root, the
            resolved path, and the store MIME type.

    Raises:
        _RowError: If the cell is empty, outside the root, missing, or of an
            unsupported type.
    """
    text = value.strip()
    if not text:
        msg = "column 'file': empty"
        raise _RowError(msg)
    # #EDGE: Security - a manifest path is untrusted input. Resolve ``..`` and
    # symlinks, then require the result to stay under the source root, so a
    # row cannot import a file from elsewhere on the disk.
    # #VERIFY: tests/unit/test_document_import.py covers an absolute path, a
    # ``..`` path, and a symlink that point outside the source root.
    try:
        root = source_root.resolve()
        written = Path(text)
        source = (written if written.is_absolute() else root / written).resolve()
        if not source.is_relative_to(root):
            msg = "column 'file': path is outside the source root"
            raise _RowError(msg)
        if not source.is_file():
            msg = "column 'file': file not found"
            raise _RowError(msg)
    except (OSError, ValueError, RuntimeError):
        # An embedded NUL, an over-long name, or a symlink loop.
        msg = "column 'file': path could not be read"
        raise _RowError(msg) from None
    mime = mime_for_source(source)
    if mime is None:
        msg = "column 'file': unsupported file type"
        raise _RowError(msg)
    return source.relative_to(root).as_posix(), source, mime


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


def _check_header(names: list[str]) -> list[str]:
    """Check the header row without echoing any cell text.

    A manifest saved without a header row makes its first data row the
    header, so unknown columns are reported by position, never by name.

    Args:
        names (list[str]): Stripped header cells.

    Returns:
        list[str]: Value-free problems; empty when the header is valid.
    """
    problems = [
        f"header: missing column '{c}'" for c in REQUIRED_COLUMNS if c not in names
    ]
    seen: set[str] = set()
    for position, name in enumerate(names, start=1):
        if name not in ALL_COLUMNS:
            problems.append(f"header: unknown column at position {position}")
        elif name in seen:
            problems.append(f"header: duplicate column at position {position}")
        seen.add(name)
    return problems


def _read_rows(
    handle: Iterable[str],
    source_root: Path,
    keys: dict[str, UUID],
    report: ManifestReport,
) -> None:
    """Validate the header and every row of an open manifest into ``report``.

    Args:
        handle (Iterable[str]): Open manifest text.
        source_root (Path): Directory that ``file`` cells resolve against.
        keys (dict[str, UUID]): Entity key to UUID.
        report (ManifestReport): Receives rows and problems.
    """
    reader = csv.DictReader(handle, restkey=_EXTRA_CELLS_KEY)
    names = [n.strip() for n in reader.fieldnames or []]
    report.problems += _check_header(names)
    if report.problems:
        return
    # Normalize so a space-padded header cell still matches its column.
    reader.fieldnames = names
    seen: dict[UUID, int] = {}
    for raw in reader:
        line = reader.line_num
        if _EXTRA_CELLS_KEY in raw:
            report.problems.append(f"line {line}: more cells than header columns")
            continue
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
        ManifestReport: Valid rows and value-free problems. A manifest that
            cannot be opened or decoded yields one problem and
            ``unreadable=True``.
    """
    report = ManifestReport()
    try:
        # Decoding is lazy, so a bad byte surfaces inside the row loop.
        with manifest.open(encoding="utf-8-sig", newline="") as handle:
            _read_rows(handle, source_root, entity_map or {}, report)
    except (OSError, ValueError, csv.Error):
        # ValueError covers UnicodeDecodeError. Drop partial results: a
        # manifest that fails midway is not trustworthy.
        return ManifestReport(problems=["manifest could not be read"], unreadable=True)
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


class StagedFiles:
    """Files copied next to the store under temporary names.

    :meth:`stage` copies a source file into a temporary file inside the
    documents root. :meth:`publish` renames every staged file to its final
    name; :meth:`discard` deletes them. Nothing reaches a final name until
    the caller has committed the database transaction.

    Args:
        root (Path): Documents root directory.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._pending: list[tuple[Path, Path]] = []

    def stage(self, source: Path, name: str) -> tuple[str, int]:
        """Copy ``source`` to a temporary file and report what was copied.

        Args:
            source (Path): Source file.
            name (str): Final file name, relative to the root.

        Returns:
            tuple[str, int]: Hex SHA-256 and size of the bytes actually copied.
        """
        self._root.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(
            dir=self._root, prefix=".stage-", suffix=".tmp"
        )
        temp = Path(temp_name)
        # Registered before any write so discard() removes it on failure.
        self._pending.append((temp, self._root / name))
        digest = hashlib.sha256()
        size = 0
        with os.fdopen(descriptor, "wb") as target, source.open("rb") as origin:
            while chunk := origin.read(_CHUNK):
                digest.update(chunk)
                target.write(chunk)
                size += len(chunk)
            target.flush()
            os.fsync(target.fileno())
        temp.chmod(_STORED_MODE)
        return digest.hexdigest(), size

    def publish(self) -> None:
        """Rename every staged file to its final name, replacing any old file.

        Raises:
            OSError: If a rename fails; staged files not yet renamed are
                deleted first.
        """
        # #ASSUME: Data integrity - staged files sit in the documents root, so
        # the rename stays on one filesystem and is atomic.
        # #VERIFY: documents_root is one mounted volume, not a union of mounts.
        pending, self._pending = self._pending, []
        for index, (temp, final) in enumerate(pending):
            try:
                temp.replace(final)
            except OSError:
                self._remove(pending[index:])
                raise

    def discard(self) -> None:
        """Delete every staged file that has not been published."""
        pending, self._pending = self._pending, []
        self._remove(pending)

    @staticmethod
    def _remove(pending: list[tuple[Path, Path]]) -> None:
        for temp, _final in pending:
            with contextlib.suppress(OSError):
                temp.unlink(missing_ok=True)


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


def _file_fields(
    row: ManifestRow, sha: str, stored: str, size: int
) -> dict[str, object]:
    return {
        "sha256": sha,
        "mime_type": row.mime_type,
        "file_size": size,
        "file_name": row.source.name[:_MAX_FILE_NAME],
        "file_path": stored,
    }


@dataclass
class _Tally:
    """Running counts for one import."""

    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped_deleted: int = 0
    duplicate_lines: list[int] = field(default_factory=list)
    # Hashes staged earlier in this run: the repository may not see pending
    # rows until the flush, so a repeated file in one manifest is caught here.
    staged_hashes: set[str] = field(default_factory=set)

    def result(self) -> ImportResult:
        """Return the counts as an immutable result."""
        return ImportResult(
            created=self.created,
            updated=self.updated,
            unchanged=self.unchanged,
            duplicates=len(self.duplicate_lines),
            skipped_deleted=self.skipped_deleted,
            duplicate_lines=tuple(self.duplicate_lines),
        )


def _stage_row(row: ManifestRow, sha: str, staged: StagedFiles) -> tuple[str, int]:
    """Stage a row's file and confirm it still matches the hash taken earlier.

    Args:
        row (ManifestRow): The row.
        sha (str): SHA-256 computed before staging.
        staged (StagedFiles): Where the copy is staged.

    Returns:
        tuple[str, int]: Stored file name and the copied size in bytes.

    Raises:
        ImportProblemError: If the source changed between hashing and copying.
    """
    name = stored_name(row.document_id, row.mime_type)
    copied_sha, size = staged.stage(row.source, name)
    if copied_sha != sha:
        msg = f"line {row.line}: column 'file': file changed while importing"
        raise ImportProblemError([msg])
    return name, size


def _stored_file_matches(path: Path, sha: str) -> bool:
    """Return True when ``path`` is a regular file holding bytes with ``sha``."""
    return path.is_file() and sha256_file(path) == sha


async def _create_row(
    repo: DocumentRepository,
    row: ManifestRow,
    sha: str,
    staged: StagedFiles,
    tally: _Tally,
) -> None:
    if sha in tally.staged_hashes or await repo.live_id_with_sha(sha) is not None:
        tally.duplicate_lines.append(row.line)
        return
    stored, size = _stage_row(row, sha, staged)
    repo.add(
        Document(
            id=row.document_id,
            **_metadata(row),
            **_file_fields(row, sha, stored, size),
        )
    )
    tally.staged_hashes.add(sha)
    tally.created += 1


def _update_row(
    existing: Document,
    row: ManifestRow,
    sha: str,
    documents_root: Path,
    staged: StagedFiles,
    tally: _Tally,
) -> None:
    wanted = _metadata(row)
    stored_file = documents_root / stored_name(row.document_id, row.mime_type)
    # The stored bytes are checked, not just the row: a crash between commit
    # and publish, or a file deleted by hand, leaves a row that claims bytes the
    # store does not hold. Re-importing repairs it.
    restage = (
        existing.sha256 != sha
        or existing.mime_type != row.mime_type
        or not _stored_file_matches(stored_file, sha)
    )
    if restage:
        stored, size = _stage_row(row, sha, staged)
        wanted.update(_file_fields(row, sha, stored, size))
    changed = restage
    for name, value in wanted.items():
        if getattr(existing, name) != value:
            setattr(existing, name, value)
            changed = True
    tally.staged_hashes.add(sha)
    if changed:
        tally.updated += 1
    else:
        tally.unchanged += 1


async def _record_rows(
    repo: DocumentRepository,
    rows: list[ManifestRow],
    documents_root: Path,
    staged: StagedFiles,
) -> ImportResult:
    tally = _Tally()
    for row in rows:
        sha = sha256_file(row.source)
        existing = await repo.get(row.document_id)
        if existing is None:
            await _create_row(repo, row, sha, staged, tally)
        elif existing.deleted_at is not None:
            tally.skipped_deleted += 1
        else:
            _update_row(existing, row, sha, documents_root, staged, tally)
    await repo.flush()
    return tally.result()


async def apply_import(
    repo: DocumentRepository,
    rows: list[ManifestRow],
    documents_root: Path,
    *,
    commit: Callable[[], Awaitable[None]],
) -> ImportResult:
    """Stage files, record rows, commit, then publish the files.

    Every row's entity must exist first; otherwise nothing is imported. Files
    are copied to temporary names, ``commit`` runs, and only then are the
    files renamed to their final names. A failure before the commit deletes
    the staged files and leaves the store untouched.

    Args:
        repo (DocumentRepository): Database operations.
        rows (list[ManifestRow]): Rows from :func:`read_manifest`.
        documents_root (Path): Documents root directory.
        commit (Callable[[], Awaitable[None]]): Commits the caller's
            transaction. The caller still owns rollback.

    Returns:
        ImportResult: Counts by outcome.

    Raises:
        ImportProblemError: If any row names an entity that does not exist,
            or a source file changes while it is copied.
        BaseException: Whatever staging or ``commit`` raised, re-raised after
            the staged files are deleted.
    """
    live = await repo.live_entity_ids({r.entity_id for r in rows})
    missing = [
        f"line {r.line}: column 'entity': no such entity"
        for r in rows
        if r.entity_id not in live
    ]
    if missing:
        raise ImportProblemError(missing)

    # #ASSUME: Data integrity - one importer runs at a time against a store.
    # #EDGE: a crash after the commit but before publish() leaves rows whose
    # files are missing or stale; the next import notices (the stored bytes are
    # re-hashed) and repairs them.
    # #VERIFY: tests/unit/test_document_import.py fails the commit and a later
    # row and asserts the store is unchanged.
    staged = StagedFiles(documents_root)
    try:
        result = await _record_rows(repo, rows, documents_root, staged)
        await commit()
    except BaseException:
        staged.discard()
        raise
    staged.publish()
    return result
