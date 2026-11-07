"""Shared test credentials and session helpers. All values are synthetic."""

import json
import time
from base64 import b64decode, b64encode
from typing import Any

import itsdangerous

TEST_API_KEY = "test-only-api-key-0123456789abcdef"  # pragma: allowlist secret
AUTH_HEADERS = {"X-API-Key": TEST_API_KEY}
TEST_CSRF_TOKEN = "test-only-csrf-token-0123456789"  # pragma: allowlist secret


def session_cookie_value(secret_key: str, session: dict[str, Any]) -> str:
    """Encode ``session`` exactly as Starlette's SessionMiddleware does.

    Args:
        secret_key: The application secret key.
        session: The session payload.

    Returns:
        The signed cookie value.
    """
    data = b64encode(json.dumps(session).encode("utf-8"))
    signer = itsdangerous.TimestampSigner(secret_key)
    return signer.sign(data).decode("utf-8")


def decode_session_cookie(secret_key: str, value: str) -> dict[str, Any]:
    """Decode and verify a session cookie value.

    Args:
        secret_key: The application secret key.
        value: The cookie value.

    Returns:
        The session payload.
    """
    signer = itsdangerous.TimestampSigner(secret_key)
    return json.loads(b64decode(signer.unsign(value)))


def user_session(
    role: str = "admin", *, exp_in: float = 3600, csrf: str = TEST_CSRF_TOKEN
) -> dict[str, Any]:
    """Build a session payload for a signed-in user.

    Args:
        role: ``"admin"`` or ``"viewer"``.
        exp_in: Seconds until the session expires (negative for expired).
        csrf: The CSRF token stored in the session.

    Returns:
        The session mapping.
    """
    return {
        "user": {
            "sub": f"test-{role}",
            "email": f"{role}@example.test",
            "name": f"Test {role.title()}",
            "role": role,
            "auth_method": "oidc",
            "exp": time.time() + exp_in,
        },
        "csrf": csrf,
    }
