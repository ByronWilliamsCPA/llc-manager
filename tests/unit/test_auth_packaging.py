"""The libraries browser login needs are declared for the shipped image."""

from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.version import Version

pytestmark = pytest.mark.unit

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"
AUTH_PACKAGES = {"authlib", "itsdangerous", "argon2-cffi", "httpx", "anyio"}


def test_auth_packages_are_in_the_api_extra() -> None:
    """The Dockerfile installs ``--extra api``, so the packages must be there."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    api_extra = data["project"]["optional-dependencies"]["api"]
    declared = {Requirement(entry).name for entry in api_extra}
    assert declared >= AUTH_PACKAGES


def test_uvicorn_floor_supports_cidr_trusted_proxies() -> None:
    """``trusted_proxy_ips`` accepts networks, which uvicorn learned in 0.31.0."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    api_extra = data["project"]["optional-dependencies"]["api"]
    (uvicorn,) = (
        requirement
        for requirement in map(Requirement, api_extra)
        if requirement.name == "uvicorn"
    )
    assert Version("0.30.6") not in uvicorn.specifier
    assert Version("0.31.0") in uvicorn.specifier


@pytest.mark.parametrize(
    "module",
    [
        "authlib.integrations.starlette_client",
        "itsdangerous",
        "argon2",
        "httpx",
        "anyio",
    ],
)
def test_auth_modules_import(module: str) -> None:
    assert importlib.import_module(module) is not None
