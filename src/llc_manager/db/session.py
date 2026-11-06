"""Database session and engine configuration."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from llc_manager.core.config import settings
from llc_manager.utils.logging import get_logger

logger = get_logger(__name__)

# #CRITICAL: Concurrency - database pool size (`database_pool_size` + `max_overflow`)
# caps simultaneous in-flight queries. Exceeding the cap serializes requests and
# can trigger timeouts under load spikes.
# #VERIFY: Load-test at >= 2x expected peak RPS before production; alert if
# `sqlalchemy.pool.QueuePool.checkedout()` approaches `pool_size + max_overflow`.
# #ASSUME: External resource - `pool_pre_ping=True` guarantees the connection
# is live before handing it to a request, at the cost of one round-trip per checkout.
# #VERIFY: If p95 latency regresses, profile with `pool_pre_ping=False` to confirm
# this is not the bottleneck.
# #CRITICAL: Security - hide_parameters keeps bound values (names, EINs, Xero
# tenant IDs) out of SQLAlchemy exception messages and echo logs, so a failed
# statement logged by get_async_session or a CLI never prints row data.
# #VERIFY: tests/unit/test_seed_entities_cli.py asserts a database error
# prints no seed values; keep hide_parameters=True when changing this call.
async_engine = create_async_engine(
    settings.database_url,
    echo=settings.database_echo,
    hide_parameters=True,
    pool_pre_ping=True,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides an async database session.

    Yields:
        AsyncSession: An async database session.

    Raises:
        Exception: Re-raises any exception from the endpoint after rolling back the session.
    """
    # #CRITICAL: Data integrity - `yield` commits only if the endpoint returns
    # cleanly; any exception rolls back. FastAPI dependencies called mid-request
    # must not swallow exceptions, or data will commit in an unexpected state.
    # #VERIFY (pending): integration test that asserts session rollback on
    # HTTPException raised by endpoint code after session mutation. This test
    # does not yet exist; tracked for the Phase 1 test uplift.
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            # logger.exception preserves the traceback so rollbacks are not
            # invisible when the endpoint handler itself does not log. The
            # exception is re-raised; FastAPI still maps it to a response.
            logger.exception("db_session_rollback")
            await session.rollback()
            raise
        finally:
            await session.close()
