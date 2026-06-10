"""Main FastAPI application for LLC Manager."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from llc_manager.api.health import router as health_router
from llc_manager.api.ui import router as ui_router
from llc_manager.api.v1 import router as v1_router
from llc_manager.core.config import settings
from llc_manager.middleware.correlation import CorrelationMiddleware
from llc_manager.middleware.security import (
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    SSRFPreventionMiddleware,
)
from llc_manager.web import router as web_router

_HERE = Path(__file__).parent


@asynccontextmanager  # pyright: ignore[reportDeprecated]  # typeshed flags this overload as deprecated, but FastAPI's `lifespan=` parameter still expects a contextlib-style async context manager; revisit when FastAPI ships a replacement
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler for startup and shutdown events.

    Args:
        _app (FastAPI): The FastAPI application instance (unused; required by FastAPI signature).

    Yields:
        None: During the lifespan of the application.
    """
    # Startup
    yield
    # Shutdown


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        FastAPI: Configured FastAPI application instance.
    """
    app = FastAPI(
        title=settings.api_title,
        version="1.0.0",
        description=(
            "REST API for managing LLC entities, ownership structures, "
            "compliance dates, bank accounts, tax filings, and associated "
            "documentation.\n\n"
            "All resource endpoints are namespaced under `/api/v1/` to match "
            "the API version `1.0.0`. Health probe endpoints are exposed "
            "under `/api/health/` and follow Kubernetes probe conventions."
        ),
        contact={
            "name": "Byron Williams",
            "email": "byron@williamscpa.com",
            "url": "https://github.com/ByronWilliamsCPA/llc-manager",
        },
        license_info={
            "name": "MIT",
            "url": "https://github.com/ByronWilliamsCPA/llc-manager/blob/main/LICENSE",
        },
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # Add CORS middleware
    # Methods/headers are allowlisted (no wildcards) because allow_credentials=True
    # combined with wildcard methods/headers broadens the cross-origin contract
    # beyond what the API actually accepts. See SECURITY-FINDINGS.md A05-1.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Correlation-ID",
            "X-Request-ID",
        ],
        expose_headers=["X-Correlation-ID", "X-Request-ID"],
        max_age=3600,
    )

    # Add custom middleware (order matters: CorrelationMiddleware must run first
    # so correlation IDs are present in logs emitted by the later middleware).
    app.add_middleware(CorrelationMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(SSRFPreventionMiddleware)

    # Include routers
    app.include_router(health_router, prefix="/api", tags=["Health"])
    app.include_router(v1_router, prefix="/api/v1")
    app.include_router(ui_router)
    app.include_router(web_router)

    # Serve static assets (CSS, JS)
    app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")

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
