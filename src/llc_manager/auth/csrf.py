"""CSRF protection for cookie-authenticated, state-changing requests."""

import hmac

from fastapi import HTTPException, Request, status

from llc_manager.auth.session import expected_csrf_token

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
CSRF_HEADER = "X-CSRF-Token"
CSRF_FORM_FIELD = "csrf_token"


async def verify_csrf(request: Request) -> None:
    """Reject non-safe requests that lack the session's CSRF token.

    The token may arrive in the ``X-CSRF-Token`` header (HTMX) or the
    ``csrf_token`` form field (plain forms). Comparison is constant time.

    Args:
        request (Request): The incoming request.

    Raises:
        HTTPException: 403 when the token is missing or does not match.
    """
    # #CRITICAL: cookie-authenticated writes are forgeable without this check.
    # #VERIFY: every non-safe web route carries it (attached in the gating PR;
    # tests/unit/test_auth_gates.py covers the check itself).
    if request.method in SAFE_METHODS:
        return
    expected = expected_csrf_token(request.session)
    supplied = request.headers.get(CSRF_HEADER)
    if supplied is None:
        content_type = request.headers.get("content-type", "")
        if content_type.startswith(
            ("application/x-www-form-urlencoded", "multipart/form-data")
        ):
            field = (await request.form()).get(CSRF_FORM_FIELD)
            supplied = field if isinstance(field, str) else None
    if (
        expected is None
        or supplied is None
        or not hmac.compare_digest(expected.encode(), supplied.encode())
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token missing or invalid",
        )
