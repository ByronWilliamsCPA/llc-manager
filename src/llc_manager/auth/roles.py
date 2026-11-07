"""Mapping of Authentik group claims to application roles."""

from collections.abc import Mapping
from enum import StrEnum
from typing import cast


class Role(StrEnum):
    """Application roles, from most to least privileged."""

    ADMIN = "admin"
    VIEWER = "viewer"


def resolve_role(
    claims: Mapping[str, object],
    *,
    groups_claim: str,
    admin_group: str,
    viewer_group: str,
) -> Role | None:
    """Pick the highest role granted by the groups claim.

    Args:
        claims (Mapping[str, object]): Verified ID token claims.
        groups_claim (str): Name of the claim that lists group names.
        admin_group (str): Group that grants ``Role.ADMIN``.
        viewer_group (str): Group that grants ``Role.VIEWER``.

    Returns:
        Role | None: ``Role.ADMIN`` if the admin group is present (it outranks
        viewer), ``Role.VIEWER`` if only the viewer group is present, else
        ``None``.
    """
    # #CRITICAL: authorization - no matching group must mean no access, and
    # matching must be exact so a look-alike group never grants a role.
    # #VERIFY: tests/unit/test_auth_roles.py covers case, prefix, and bad shapes.
    raw = claims.get(groups_claim)
    if isinstance(raw, str):
        groups = {raw}
    elif isinstance(raw, list):
        items = cast("list[object]", raw)
        groups = {item for item in items if isinstance(item, str)}
    else:
        return None
    if admin_group in groups:
        return Role.ADMIN
    if viewer_group in groups:
        return Role.VIEWER
    return None
