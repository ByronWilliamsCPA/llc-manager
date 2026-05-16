"""Export the FastAPI OpenAPI schema to ``docs/api/openapi.json``.

Run from the repo root::

    uv run python scripts/export_openapi.py

The script imports the FastAPI app, calls ``app.openapi()``, and writes the
result to disk without starting an HTTP server. It is intended to be invoked
locally and in CI so the committed ``docs/api/openapi.json`` always reflects
the current route handlers.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    """Write the current OpenAPI spec to ``docs/api/openapi.json``.

    Returns:
        Process exit code (``0`` on success).
    """
    repo_root = Path(__file__).resolve().parent.parent
    src_dir = repo_root / "src"
    if src_dir.exists() and str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    # Import is deferred so sys.path is patched first when the script is run directly.
    from llc_manager.main import app  # noqa: PLC0415

    output_dir = repo_root / "docs" / "api"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "openapi.json"

    spec = app.openapi()

    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(spec, fh, indent=2, sort_keys=True)
        fh.write("\n")

    print(f"Wrote OpenAPI spec ({len(spec.get('paths', {}))} paths) to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
