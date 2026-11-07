"""Shared Jinja2Templates instance for HTML page rendering."""

from pathlib import Path

from fastapi.templating import Jinja2Templates

from llc_manager.auth.templating import install_auth_globals

templates = install_auth_globals(
    Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
)
