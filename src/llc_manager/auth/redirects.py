"""Validation of post-login redirect targets."""

from urllib.parse import unquote, urlsplit

DEFAULT_NEXT = "/entities"
# The value is stored in the 4 KB session cookie while the login runs.
MAX_NEXT_LENGTH = 512
_MAX_DECODE_ROUNDS = 3


def _has_unsafe_character(value: str) -> bool:
    """Whether ``value`` holds a backslash or a control character.

    Args:
        value (str): Text to check.

    Returns:
        bool: ``True`` if a browser or server could misread the text.
    """
    return "\\" in value or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)


def _resolved_path(path: str) -> str | None:
    """Resolve percent-encoding and dot segments the way a server would.

    Args:
        path (str): The path part of an untrusted ``next`` value.

    Returns:
        str | None: The resolved absolute path, or ``None`` if decoding reveals
        a backslash or control character.
    """
    # #EDGE: `/x/%2e%2e/auth/login` and `/x/..%2fauth` reach /auth after the
    # server decodes and normalizes them, so the check runs on that form.
    # #VERIFY: tests/unit/test_auth_redirects.py dot-segment cases.
    decoded = path
    for _ in range(_MAX_DECODE_ROUNDS):
        once = unquote(decoded)
        if once == decoded:
            break
        decoded = once
    if _has_unsafe_character(decoded):
        return None
    stack: list[str] = []
    for segment in decoded.split("/")[1:]:
        if segment == "..":
            if stack:
                stack.pop()
        elif segment not in {"", "."}:
            stack.append(segment)
    return "/" + "/".join(stack)


def safe_next(value: str | None) -> str:
    """Return ``value`` if it is a safe in-site path, else the default.

    A safe target is a relative path that starts with a single ``/``. Anything
    that a browser could treat as another origin (a leading double slash, a
    backslash, a scheme, control characters) is rejected, as are paths under
    ``/auth`` so a login can never bounce back into the login flow. Paths are
    judged after percent-decoding and dot-segment resolution, and values longer
    than ``MAX_NEXT_LENGTH`` are rejected.

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
    if len(value) > MAX_NEXT_LENGTH or _has_unsafe_character(value):
        return DEFAULT_NEXT
    parts = urlsplit(value)
    if parts.scheme or parts.netloc:
        return DEFAULT_NEXT
    resolved = _resolved_path(parts.path)
    if resolved is None or resolved == "/auth" or resolved.startswith("/auth/"):
        return DEFAULT_NEXT
    return value
