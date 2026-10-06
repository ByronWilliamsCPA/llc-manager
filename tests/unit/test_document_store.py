"""Stored-file location rules and path-traversal guard."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from llc_manager.services.document_store import (
    UnsafePathError,
    mime_for_source,
    resolve_stored_file,
    stored_name,
)

pytestmark = [pytest.mark.unit, pytest.mark.security]


def test_stored_name_uses_id_and_mime_extension() -> None:
    doc_id = uuid4()
    assert stored_name(doc_id, "application/pdf") == f"{doc_id}.pdf"
    assert stored_name(doc_id, None) == f"{doc_id}.pdf"
    assert stored_name(doc_id, "image/png") == f"{doc_id}.png"


def test_stored_name_refuses_an_unknown_mime_type() -> None:
    with pytest.raises(UnsafePathError, match="not supported"):
        stored_name(uuid4(), "application/x-unknown")


@pytest.mark.parametrize(
    ("name", "mime"),
    [("a.PDF", "application/pdf"), ("b.jpeg", "image/jpeg"), ("c.tiff", "image/tiff")],
)
def test_mime_for_source(name: str, mime: str) -> None:
    assert mime_for_source(Path(name)) == mime


def test_unsupported_source_extension() -> None:
    assert mime_for_source(Path("x.exe")) is None


def test_resolves_existing_file(tmp_path: Path) -> None:
    doc_id = uuid4()
    (tmp_path / f"{doc_id}.pdf").write_bytes(b"%PDF-1.4")
    assert (
        resolve_stored_file(tmp_path, doc_id, "application/pdf")
        == (tmp_path / f"{doc_id}.pdf").resolve()
    )


def test_missing_file_is_refused_without_path_in_message(tmp_path: Path) -> None:
    with pytest.raises(UnsafePathError) as exc:
        resolve_stored_file(tmp_path, uuid4(), "application/pdf")
    assert str(tmp_path) not in str(exc.value)


def test_symlink_escaping_root_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    outside = tmp_path / "secret.pdf"
    outside.write_bytes(b"outside")
    doc_id = uuid4()
    (root / f"{doc_id}.pdf").symlink_to(outside)
    with pytest.raises(UnsafePathError, match="outside the documents root"):
        resolve_stored_file(root, doc_id, "application/pdf")


def test_symlink_inside_root_is_allowed(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    (root / "sub").mkdir(parents=True)
    target = root / "sub" / "real.pdf"
    target.write_bytes(b"inside")
    doc_id = uuid4()
    (root / f"{doc_id}.pdf").symlink_to(target)
    assert resolve_stored_file(root, doc_id, None) == target.resolve()


def test_directory_in_place_of_file_is_refused(tmp_path: Path) -> None:
    doc_id = uuid4()
    (tmp_path / f"{doc_id}.pdf").mkdir()
    with pytest.raises(UnsafePathError, match="not a regular file"):
        resolve_stored_file(tmp_path, doc_id, "application/pdf")


def test_symlinked_root_is_followed(tmp_path: Path) -> None:
    real_root = tmp_path / "real"
    real_root.mkdir()
    link_root = tmp_path / "link"
    link_root.symlink_to(real_root)
    doc_id = uuid4()
    (real_root / f"{doc_id}.pdf").write_bytes(b"x")
    assert resolve_stored_file(link_root, doc_id, None).parent == real_root.resolve()


def test_unreadable_stored_file_is_refused_without_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc_id = uuid4()
    (tmp_path / f"{doc_id}.pdf").write_bytes(b"%PDF-1.4")

    def boom(_self: Path, *_a: object, **_k: object) -> Path:
        msg = f"{tmp_path}: symlink loop"
        raise RuntimeError(msg)

    monkeypatch.setattr(Path, "resolve", boom)
    with pytest.raises(UnsafePathError) as exc:
        resolve_stored_file(tmp_path, doc_id, "application/pdf")
    assert str(tmp_path) not in str(exc.value)
