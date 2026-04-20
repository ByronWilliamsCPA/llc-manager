"""Main FastAPI application for LLC Manager."""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from llc_manager.api.health import router as health_router
from llc_manager.api.v1 import router as v1_router
from llc_manager.core.config import settings
from llc_manager.middleware.correlation import CorrelationIdMiddleware
from llc_manager.middleware.security import SSRFProtectionMiddleware


@asynccontextmanager
async def lifespan(_app: FastAPI) -> Any:
    """Application lifespan handler for startup and shutdown events.

    Args:
        _app: The FastAPI application instance (unused; required by FastAPI signature).

    Yields:
        None during the lifespan of the application.
    """
    # Startup
    yield
    # Shutdown


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        description="API for managing LLC entities, compliance dates, and documentation",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add custom middleware
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(SSRFProtectionMiddleware)

    # Include routers
    app.include_router(health_router, prefix="/api", tags=["Health"])
    app.include_router(v1_router, prefix="/api/v1")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "llc_manager.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
        workers=settings.api_workers,
    )
