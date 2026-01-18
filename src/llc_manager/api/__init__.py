"""API package for LLC Manager.

This package contains FastAPI routers and API-related functionality.
"""

from __future__ import annotations

from llc_manager.api.health import router as health_router

__all__ = ["health_router"]
