"""Generate a Postman Collection v2.1 from ``docs/api/openapi.json``.

Run from the repo root::

    uv run python scripts/generate_postman_collection.py

The output is written to ``docs/api/postman-collection.json``. Each request:

- Uses the ``{{baseUrl}}`` variable (default ``http://localhost:8000``).
- Sends ``X-API-Key: {{apiKey}}`` so callers can populate auth via a Postman
  environment without committing secrets.
- Has a ``test`` script that asserts the documented success status code and,
  when the success response is JSON, parses the body and asserts it is an
  object or array.

Requests are grouped into folders by the first OpenAPI tag.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
OPENAPI_PATH = REPO_ROOT / "docs" / "api" / "openapi.json"
COLLECTION_PATH = REPO_ROOT / "docs" / "api" / "postman-collection.json"

SUCCESS_STATUS_BY_METHOD = {
    "get": 200,
    "post": 201,
    "patch": 200,
    "put": 200,
    "delete": 204,
}


def _resolve_ref(spec: dict[str, Any], ref: str) -> dict[str, Any]:
    """Resolve a local ``$ref`` against the OpenAPI document.

    Args:
        spec: The full OpenAPI document.
        ref: A JSON-pointer ref like ``#/components/schemas/Entity``.

    Returns:
        The referenced schema dict, or ``{}`` if not found.
    """
    if not ref.startswith("#/"):
        return {}
    node: Any = spec
    for part in ref[2:].split("/"):
        if not isinstance(node, dict) or part not in node:
            return {}
        node = node[part]
    return node if isinstance(node, dict) else {}


def _example_for_schema(
    schema: dict[str, Any], spec: dict[str, Any], depth: int = 0
) -> Any:
    """Produce a small example value for a JSON schema fragment."""
    if depth > 4 or not isinstance(schema, dict):
        return None

    if "$ref" in schema:
        return _example_for_schema(_resolve_ref(spec, schema["$ref"]), spec, depth + 1)

    for combinator in ("anyOf", "oneOf"):
        if combinator in schema:
            for option in schema[combinator]:
                if option.get("type") != "null":
                    return _example_for_schema(option, spec, depth + 1)
            return None
    if "allOf" in schema:
        merged: dict[str, Any] = {}
        for option in schema["allOf"]:
            resolved = (
                _resolve_ref(spec, option["$ref"]) if "$ref" in option else option
            )
            merged.update(resolved)
        return _example_for_schema(merged, spec, depth + 1)

    if "example" in schema:
        return schema["example"]
    if "default" in schema:
        return schema["default"]
    enum = schema.get("enum")
    if enum:
        return enum[0]

    schema_type = schema.get("type")
    if schema_type == "object" or "properties" in schema:
        result: dict[str, Any] = {}
        required = set(schema.get("required", []))
        for name, prop in (schema.get("properties") or {}).items():
            if not required or name in required:
                result[name] = _example_for_schema(prop, spec, depth + 1)
        return result
    if schema_type == "array":
        item_example = _example_for_schema(schema.get("items", {}), spec, depth + 1)
        return [item_example] if item_example is not None else []
    if schema_type == "string":
        fmt = schema.get("format")
        if fmt == "uuid":
            return "00000000-0000-0000-0000-000000000000"
        if fmt == "date":
            return "2026-01-01"
        if fmt == "date-time":
            return "2026-01-01T00:00:00Z"
        if fmt == "email":
            return "user@example.com"
        return schema.get("title", "string")
    if schema_type == "integer":
        return 0
    if schema_type == "number":
        return 0.0
    if schema_type == "boolean":
        return False
    return None


def _sanitize_name(name: str) -> str:
    """Make ``name`` safe-ish for a Postman item title."""
    return re.sub(r"\s+", " ", name).strip() or "Request"


def _path_to_postman(path: str) -> tuple[str, list[str]]:
    """Convert an OpenAPI path to Postman raw URL + path segments."""
    segments: list[str] = []
    for part in path.strip("/").split("/"):
        if part.startswith("{") and part.endswith("}"):
            segments.append(":" + part[1:-1])
        else:
            segments.append(part)
    raw = "{{baseUrl}}/" + "/".join(segments)
    return raw, segments


def _build_query(parameters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate OpenAPI query params into Postman query entries (disabled)."""
    query: list[dict[str, Any]] = []
    for param in parameters:
        if param.get("in") != "query":
            continue
        schema = param.get("schema", {})
        default = schema.get("default")
        value = "" if default is None else str(default)
        query.append(
            {
                "key": param["name"],
                "value": value,
                "description": param.get("description", ""),
                "disabled": True,
            }
        )
    return query


def _build_path_variables(parameters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate OpenAPI path params into Postman path variables."""
    variables: list[dict[str, Any]] = []
    for param in parameters:
        if param.get("in") != "path":
            continue
        schema = param.get("schema", {})
        example = _example_for_schema(schema, {"components": {"schemas": {}}}) or ""
        variables.append(
            {
                "key": param["name"],
                "value": str(example),
                "description": param.get("description", ""),
            }
        )
    return variables


def _success_status(operation: dict[str, Any], method: str) -> int:
    """Pick the documented success status code for an operation."""
    responses = operation.get("responses", {})
    for code in responses:
        try:
            code_int = int(code)
        except (TypeError, ValueError):
            continue
        if 200 <= code_int < 300:
            return code_int
    return SUCCESS_STATUS_BY_METHOD.get(method, 200)


def _success_is_json(operation: dict[str, Any], status_code: int) -> bool:
    """Whether the documented success response advertises a JSON body."""
    if status_code == 204:
        return False
    response = operation.get("responses", {}).get(str(status_code), {})
    content = response.get("content", {})
    return any(ct.startswith("application/json") for ct in content)


def _test_script(name: str, expected_status: int, expect_json: bool) -> list[str]:
    """Build a Postman ``test`` script asserting status and JSON body."""
    lines = [
        f'pm.test("{name} returns {expected_status}", function () {{',
        f"    pm.response.to.have.status({expected_status});",
        "});",
    ]
    if expect_json:
        lines.extend(
            [
                "",
                f'pm.test("{name} returns a JSON body", function () {{',
                "    pm.response.to.be.withBody;",
                "    pm.response.to.be.json;",
                "    var body = pm.response.json();",
                '    pm.expect(body, "JSON body").to.satisfy(function (value) {',
                '        return value !== null && (typeof value === "object" || Array.isArray(value));',
                "    });",
                "});",
            ]
        )
    else:
        lines.extend(
            [
                "",
                f'pm.test("{name} returns an empty body", function () {{',
                '    pm.expect(pm.response.text() || "").to.have.lengthOf.at.most(2);',
                "});",
            ]
        )
    return lines


def _build_request_body(
    operation: dict[str, Any], spec: dict[str, Any]
) -> dict[str, Any] | None:
    """Build a Postman ``body`` block from a JSON request schema."""
    request_body = operation.get("requestBody")
    if not request_body:
        return None
    content = request_body.get("content", {})
    json_content = content.get("application/json")
    if not json_content:
        return None
    schema = json_content.get("schema", {})
    example = _example_for_schema(schema, spec)
    return {
        "mode": "raw",
        "raw": json.dumps(example, indent=2, sort_keys=True),
        "options": {"raw": {"language": "json"}},
    }


def _build_item(
    path: str,
    method: str,
    operation: dict[str, Any],
    spec: dict[str, Any],
) -> dict[str, Any]:
    """Build a single Postman request item."""
    parameters = operation.get("parameters", [])
    raw_url, segments = _path_to_postman(path)
    query = _build_query(parameters)
    path_vars = _build_path_variables(parameters)

    expected_status = _success_status(operation, method)
    expect_json = _success_is_json(operation, expected_status)

    name = _sanitize_name(operation.get("summary") or f"{method.upper()} {path}")

    headers = [
        {
            "key": "Accept",
            "value": "application/json",
            "type": "text",
        },
        {
            "key": "X-API-Key",
            "value": "{{apiKey}}",
            "type": "text",
            "description": "Supplied via Postman environment variable.",
        },
    ]

    body = _build_request_body(operation, spec)
    if body is not None:
        headers.append(
            {"key": "Content-Type", "value": "application/json", "type": "text"}
        )

    request: dict[str, Any] = {
        "method": method.upper(),
        "header": headers,
        "url": {
            "raw": raw_url + ("" if not query else "?"),
            "host": ["{{baseUrl}}"],
            "path": segments,
            "query": query,
            "variable": path_vars,
        },
        "description": operation.get("description") or operation.get("summary") or "",
    }
    if body is not None:
        request["body"] = body

    return {
        "name": name,
        "request": request,
        "response": [],
        "event": [
            {
                "listen": "test",
                "script": {
                    "type": "text/javascript",
                    "exec": _test_script(name, expected_status, expect_json),
                },
            }
        ],
    }


def build_collection(spec: dict[str, Any]) -> dict[str, Any]:
    """Build a Postman Collection v2.1 document from an OpenAPI spec."""
    info = spec.get("info", {})
    folders: dict[str, list[dict[str, Any]]] = {}

    for path, methods in spec.get("paths", {}).items():
        for method, operation in methods.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            tag = (operation.get("tags") or ["default"])[0]
            folders.setdefault(tag, []).append(
                _build_item(path, method.lower(), operation, spec)
            )

    items = [{"name": tag, "item": folders[tag]} for tag in sorted(folders.keys())]

    return {
        "info": {
            "name": info.get("title", "API") + " (Postman)",
            "description": info.get("description", ""),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            "_postman_id": "llc-manager-api-collection",
            "version": {"major": 1, "minor": 0, "patch": 0},
        },
        "item": items,
        "variable": [
            {
                "key": "baseUrl",
                "value": "http://localhost:8000",
                "type": "string",
                "description": "Base URL of the LLC Manager API.",
            },
            {
                "key": "apiKey",
                "value": "",
                "type": "string",
                "description": "API key sent as the X-API-Key header.",
            },
        ],
    }


def main() -> int:
    """Generate ``docs/api/postman-collection.json`` from the OpenAPI spec."""
    if not OPENAPI_PATH.exists():
        raise SystemExit(
            f"OpenAPI spec not found at {OPENAPI_PATH}. "
            "Run `uv run python scripts/export_openapi.py` first."
        )

    with OPENAPI_PATH.open(encoding="utf-8") as fh:
        spec = json.load(fh)

    collection = build_collection(spec)

    COLLECTION_PATH.parent.mkdir(parents=True, exist_ok=True)
    with COLLECTION_PATH.open("w", encoding="utf-8") as fh:
        json.dump(collection, fh, indent=2, sort_keys=True)
        fh.write("\n")

    request_count = sum(len(folder["item"]) for folder in collection["item"])
    print(
        f"Wrote Postman collection ({request_count} requests, "
        f"{len(collection['item'])} folders) to {COLLECTION_PATH}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
