"""The compose files forward and require the settings the app validates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from ruamel.yaml import YAML

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_IN_PRODUCTION = ("LLC_MANAGER_SECRET_KEY", "LLC_MANAGER_API_KEY")


def _app_environment(name: str) -> dict[str, Any]:
    """Load the ``app`` service environment mapping from a compose file.

    Args:
        name (str): File name relative to the repository root.

    Returns:
        dict[str, Any]: The ``environment`` mapping of the ``app`` service.
    """
    data = YAML(typ="safe").load((ROOT / name).read_text(encoding="utf-8"))
    environment = data["services"]["app"]["environment"]
    assert isinstance(environment, dict)
    return environment


@pytest.mark.parametrize("key", REQUIRED_IN_PRODUCTION)
def test_base_compose_passes_the_key_through(key: str) -> None:
    """A value-less entry forwards the host value only when it is set."""
    environment = _app_environment("docker-compose.yml")
    assert key in environment
    assert environment[key] is None


@pytest.mark.parametrize("key", REQUIRED_IN_PRODUCTION)
def test_prod_compose_requires_the_key(key: str) -> None:
    """Compose refuses to start the production stack without the key."""
    value = _app_environment("docker-compose.prod.yml")[key]
    assert isinstance(value, str)
    assert value.startswith(f"${{{key}:?")
    assert value.endswith("}")


def test_prod_compose_names_the_environment_with_both_spellings() -> None:
    """The app reads the prefixed name first, so set it as well as the bare one."""
    environment = _app_environment("docker-compose.prod.yml")
    assert environment["ENVIRONMENT"] == "production"
    assert environment["LLC_MANAGER_ENVIRONMENT"] == "production"
