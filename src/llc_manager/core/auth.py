"""Inbound service authentication for ``/api/v1``.

Callers send a shared key in the ``X-API-Key`` header. The key is compared in
constant time with :func:`hmac.compare_digest`. When no key is configured the
API refuses every request (503) instead of falling back to open access.

This is the interim service-to-service check; per-user OIDC remains the
long-term design (see ``SECURITY-FINDINGS.md``). It covers ``/api/v1`` only;
the server-rendered HTML pages are not behind this key.
"""

import hmac
from typing import Annotated

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from llc_manager.core.config import settings
from llc_manager.utils.logging import get_logger

logger = get_logger(__name__)

API_KEY_HEADER_NAME = "X-API-Key"  # pragma: allowlist secret (header name)

_api_key_header = APIKeyHeader(
    name=API_KEY_HEADER_NAME,
    auto_error=False,
    description="Shared service key for /api/v1.",
)

APIKeyHeaderValue = Annotated[str | None, Security(_api_key_header)]


def keys_match(supplied: str, expected: str) -> bool:
    """Compare two keys in constant time.

    Both values are encoded to UTF-8 bytes first, because
    :func:`hmac.compare_digest` rejects non-ASCII ``str`` input.

    Args:
        supplied (str): Key sent by the caller.
        expected (str): Configured key.

    Returns:
        bool: True when the keys are equal.
    """
    return hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))


async def require_api_key(
    api_key: APIKeyHeaderValue,
) -> None:
    """Reject the request unless it carries the configured API key.

    Args:
        api_key (APIKeyHeaderValue): Value of the ``X-API-Key`` header, if any.

    Raises:
        HTTPException: 503 when no key is configured; 401 when the header is
            missing or does not match.
    """
    # #CRITICAL: Security - fail closed. An unset key must never mean "open".
    # #VERIFY: tests/unit/test_api_key_auth.py covers unset, empty, missing,
    # wrong, and correct keys.
    configured = settings.api_key
    expected = configured.get_secret_value() if configured is not None else ""
    if not expected:
        # The missing key is logged once at startup (see ``main.lifespan``),
        # not on every request.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API authentication is not configured",
        )
    if api_key is None or not keys_match(api_key, expected):
        # Value-free: never log the supplied key.
        logger.warning(
            "api_key_rejected", reason="missing" if api_key is None else "mismatch"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
