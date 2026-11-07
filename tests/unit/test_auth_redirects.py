"""Tests for post-login redirect validation."""

from __future__ import annotations

import pytest

from llc_manager.auth.redirects import DEFAULT_NEXT, safe_next

pytestmark = [pytest.mark.unit, pytest.mark.security]


@pytest.mark.parametrize(
    "value",
    [
        "/entities",
        "/entities/123/edit",
        "/entities?q=acme&page=2",
        "/",
    ],
)
def test_safe_paths_are_kept(value: str) -> None:
    """In-site relative paths are returned unchanged."""
    assert safe_next(value) == value


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "entities",
        "//evil.example/path",
        "///evil.example",
        "/\\evil.example",
        "/entities\\..\\x",
        "https://evil.example/",
        "http:/evil.example",
        "javascript:alert(1)",
        "/entities\r\nSet-Cookie: x=1",
        "/entities\x00",
        "/entities\t",
        "/entities\x7f",
        "/auth/login",
        "/auth/callback?code=1",
        "/auth",
        "evil.example",
    ],
)
def test_unsafe_values_fall_back_to_default(value: str | None) -> None:
    """Anything a browser could treat as off-site or login-looping is rejected."""
    assert safe_next(value) == DEFAULT_NEXT


def test_lookalike_auth_prefix_is_allowed() -> None:
    """A path that merely starts with the letters ``auth`` is a normal page."""
    assert safe_next("/authors") == "/authors"


@pytest.mark.parametrize(
    "value",
    [
        "/entities/../auth/callback",
        "/entities/%2e%2e/auth/login",
        "/entities/%2E%2E/auth/login",
        "/entities/..%2fauth/login",
        "/entities/%2e%2e%2fauth/login",
        "/./auth/login",
        "/entities/./../auth",
        "/entities/%252e%252e/auth/login",
        "/a/b/../../auth/login?x=1",
        "/entities/..%5cauth",
    ],
)
def test_paths_that_resolve_into_auth_are_rejected(value: str) -> None:
    """Dot segments, plain or percent-encoded, cannot reach the /auth prefix."""
    assert safe_next(value) == DEFAULT_NEXT


@pytest.mark.parametrize(
    "value",
    ["/entities/../other", "/a/b/../c?x=1", "/entities/%2e%2e/other"],
)
def test_dot_segments_that_stay_out_of_auth_are_kept(value: str) -> None:
    """Only the resolved destination matters; the value is returned unchanged."""
    assert safe_next(value) == value


def test_a_value_at_the_length_limit_is_kept() -> None:
    value = "/" + "a" * 511

    assert len(value) == 512
    assert safe_next(value) == value


def test_a_value_over_the_length_limit_is_rejected() -> None:
    """A long ``next`` could overflow the 4 KB session cookie."""
    assert safe_next("/" + "a" * 512) == DEFAULT_NEXT
