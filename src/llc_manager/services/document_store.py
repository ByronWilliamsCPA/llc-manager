"""Location rules for stored document files.

Every stored file is named by its document ID plus an extension derived from
its MIME type, directly under the configured documents root. No caller- or
database-supplied path is ever used to locate a file, and every resolved path
is checked to stay under the root (which also defeats symlinks that point
outside it).
"""

from pathlib import Path
from uuid import UUID

# MIME types the store accepts, with the extension used on disk.
EXTENSION_BY_MIME: dict[str, str] = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/tiff": ".tif",
    "text/plain": ".txt",
}

MIME_BY_EXTENSION: dict[str, str] = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".txt": "text/plain",
}

DEFAULT_MIME = "application/pdf"


class UnsafePathError(Exception):
    """A stored file cannot be served safely.

    Raised when the resolved path is outside the documents root, is not a
    regular file, cannot be read, or the stored MIME type is not one the store
    accepts. The message never contains a path.
    """


def mime_for_source(path: Path) -> str | None:
    """Return the store MIME type for a source file, by extension.

    Args:
        path (Path): Source file path.

    Returns:
        str | None: The MIME type, or None when the extension is unsupported.
    """
    return MIME_BY_EXTENSION.get(path.suffix.lower())


def stored_name(document_id: UUID, mime_type: str | None) -> str:
    """Return the on-disk file name for a document.

    Args:
        document_id (UUID): Document ID.
        mime_type (str | None): Stored MIME type; None (a row that predates
            the MIME column) means PDF.

    Returns:
        str: ``{document_id}{extension}``.

    Raises:
        UnsafePathError: If ``mime_type`` is set but is not a type the store
            accepts. There is no ``.pdf`` fallback for an unknown type.
    """
    # #EDGE: Security - an unknown MIME type must not be mapped to a default
    # extension and then served inline under the row's own Content-Type.
    # #VERIFY: tests/unit/test_document_store.py covers an unknown type.
    extension = EXTENSION_BY_MIME.get(mime_type or DEFAULT_MIME)
    if extension is None:
        msg = "stored MIME type is not supported"
        raise UnsafePathError(msg)
    return f"{document_id}{extension}"


def resolve_stored_file(root: Path, document_id: UUID, mime_type: str | None) -> Path:
    """Return the resolved path of a document's stored file, safely.

    Args:
        root (Path): Documents root directory.
        document_id (UUID): Document ID.
        mime_type (str | None): Stored MIME type.

    Returns:
        Path: Absolute, resolved path of an existing regular file under root.

    Raises:
        UnsafePathError: If the path escapes the root, is not a regular
            file, cannot be read, or the MIME type is unsupported. The
            message never contains the path.
    """
    # #CRITICAL: Security - path traversal. Resolve symlinks, then require the
    # result to stay under the resolved root.
    # #VERIFY: tests/unit/test_document_store.py covers a symlink that points
    # outside the root and a directory in place of a file.
    name = stored_name(document_id, mime_type)
    try:
        resolved_root = root.resolve()
        candidate = (resolved_root / name).resolve()
        if not candidate.is_relative_to(resolved_root):
            msg = "stored file is outside the documents root"
            raise UnsafePathError(msg)
        if not candidate.is_file():
            msg = "stored file is missing or not a regular file"
            raise UnsafePathError(msg)
    except (OSError, RuntimeError):
        # A symlink loop (RuntimeError before Python 3.13) or a permission error must read as "not available",
        # never as a 500 whose traceback names the path.
        msg = "stored file cannot be read"
        raise UnsafePathError(msg) from None
    return candidate
