"""Tests for group-claim to role mapping."""

from __future__ import annotations

import pytest

from llc_manager.auth.roles import Role, resolve_role

pytestmark = [pytest.mark.unit, pytest.mark.security]

ADMIN = "llc-manager-admins"
VIEWER = "llc-manager-viewers"


def _resolve(claims: dict[str, object], claim: str = "groups") -> Role | None:
    return resolve_role(
        claims, groups_claim=claim, admin_group=ADMIN, viewer_group=VIEWER
    )


@pytest.mark.parametrize(
    ("claims", "expected"),
    [
        ({"groups": [ADMIN]}, Role.ADMIN),
        ({"groups": [VIEWER]}, Role.VIEWER),
        ({"groups": [VIEWER, ADMIN]}, Role.ADMIN),
        ({"groups": ["other", VIEWER]}, Role.VIEWER),
        ({"groups": ADMIN}, Role.ADMIN),
        ({"groups": ["other"]}, None),
        ({"groups": []}, None),
        ({"groups": None}, None),
        ({"groups": {"nested": ADMIN}}, None),
        ({"groups": [1, None, VIEWER]}, Role.VIEWER),
        ({}, None),
    ],
)
def test_role_resolution(claims: dict[str, object], expected: Role | None) -> None:
    """Admin outranks viewer; anything else yields no role."""
    assert _resolve(claims) == expected


def test_custom_claim_name_is_honoured() -> None:
    """Only the configured claim is read."""
    assert _resolve({"roles": [ADMIN]}, claim="roles") is Role.ADMIN
    assert _resolve({"groups": [ADMIN]}, claim="roles") is None


def test_group_names_are_matched_exactly() -> None:
    """Matching is case-sensitive and not a prefix match."""
    assert _resolve({"groups": [ADMIN.upper()]}) is None
    assert _resolve({"groups": [f"{ADMIN}-extra"]}) is None
