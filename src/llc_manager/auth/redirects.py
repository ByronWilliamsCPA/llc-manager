"""Validation of post-login redirect targets."""

from urllib.parse import urlsplit

DEFAULT_NEXT = "/entities"


def safe_next(value: str | None) -> str:
    """Return ``value`` if it is a safe in-site path, else the default.

    A safe target is a relative path that starts with a single ``/``. Anything
    that a browser could treat as another origin (a leading double slash, a
    backslash, a scheme, control characters) is rejected, as are paths under
    ``/auth`` so a login can never bounce back into the login flow.

    Args:
        value (str | None): The untrusted ``next`` value.

    Returns:
        str: The original value when safe, otherwise ``DEFAULT_NEXT``.
    """
    # #EDGE: open redirect - an attacker-supplied `next` must never leave the site.
    # #VERIFY: tests/unit/test_auth_redirects.py covers //, backslash, scheme,
    # control characters, and the /auth prefix.
    if not value or not value.startswith("/") or value.startswith("//"):
        return DEFAULT_NEXT
    if "\\" in value or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        return DEFAULT_NEXT
    parts = urlsplit(value)
    if parts.scheme or parts.netloc:
        return DEFAULT_NEXT
    if parts.path == "/auth" or parts.path.startswith("/auth/"):
        return DEFAULT_NEXT
    return value
