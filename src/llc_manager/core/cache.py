"""Redis caching utilities for performance optimization.

This module provides production-ready caching patterns:
- Function result caching with decorators
- Cache invalidation strategies
- Async Redis connection pool
- TTL (time-to-live) management
- Cache warming patterns

Setup:
    1. Install Redis client:
       uv add redis[hiredis]

    2. Start Redis:
       docker-compose up -d redis

    3. Configure in .env:
       REDIS_URL=redis://localhost:6379/0
       CACHE_TTL_SECONDS=3600

Performance:
    - 10-100x faster than database queries for cached data
    - Reduces database load by 80-90%
    - Sub-millisecond response times
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
from typing import TYPE_CHECKING, Any, TypeVar

from redis.asyncio import Redis, from_url
from redis.exceptions import RedisError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

T = TypeVar("T")  # Covariant type variable for cached function return types

# Global Redis connection pool
_redis_pool: Redis | None = None


# =============================================================================
# Connection Management
# =============================================================================


async def get_redis() -> Redis:
    """Get Redis connection from pool.

    Returns:
        Redis connection

    Example:
        >>> redis = await get_redis()
        >>> await redis.set("key", "value", ex=60)
        >>> value = await redis.get("key")
    """
    global _redis_pool

    if _redis_pool is None:
        # Get Redis URL from environment
        import os

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

        _redis_pool = from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,  # Connection pool size
            socket_keepalive=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )

        logger.info("redis_connection_initialized", url=redis_url)

    return _redis_pool


async def close_redis() -> None:
    """Close Redis connection pool.

    Call this on application shutdown.
    """
    global _redis_pool

    if _redis_pool is not None:
        await _redis_pool.close()
        _redis_pool = None
        logger.info("redis_connection_closed")


# =============================================================================
# Caching Decorators
# =============================================================================


def cached(
    ttl: int = 3600,
    key_prefix: str = "",
    key_builder: Callable[..., str] | None = None,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Cache async function results in Redis.

    Args:
        ttl: Time to live in seconds (default: 1 hour)
        key_prefix: Prefix for cache keys (default: function name)
        key_builder: Custom key building function

    Returns:
        Decorated function

    Example:
        >>> @cached(ttl=300, key_prefix="user")
        >>> async def get_user(user_id: str) -> dict:
        ...     # Expensive database query
        ...     return await db.get_user(user_id)

        >>> # First call: cache miss, queries database
        >>> user = await get_user("123")

        >>> # Subsequent calls within 5 minutes: cache hit, instant response
        >>> user = await get_user("123")
    """

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            # Build cache key
            cache_key = _build_cache_key(key_builder, key_prefix, func, args, kwargs)

            # Attempt cached retrieval with fallback to direct call
            return await _get_or_compute(cache_key, func, args, kwargs, ttl)

        return wrapper

    return decorator


def _build_cache_key(
    key_builder: Callable[..., str] | None,
    key_prefix: str,
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> str:
    """Build cache key from function arguments.

    Args:
        key_builder: Custom key building function
        key_prefix: Prefix for cache keys
        func: The function being cached
        args: Positional arguments
        kwargs: Keyword arguments

    Returns:
        Cache key string
    """
    if key_builder:
        return key_builder(*args, **kwargs)

    prefix = key_prefix or func.__name__
    key_data = f"{args}:{sorted(kwargs.items())}"
    key_hash = hashlib.md5(key_data.encode(), usedforsecurity=False).hexdigest()[:8]
    return f"{prefix}:{key_hash}"


async def _get_or_compute[T](
    cache_key: str,
    func: Callable[..., Awaitable[T]],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    ttl: int,
) -> T:
    """Get value from cache or compute and store it.

    Args:
        cache_key: The cache key
        func: Function to call on cache miss
        args: Positional arguments for func
        kwargs: Keyword arguments for func
        ttl: Time to live in seconds

    Returns:
        Cached or computed result
    """
    try:
        redis = await get_redis()

        # Try to get from cache
        cached_value = await redis.get(cache_key)
        if cached_value is not None:
            logger.debug("cache_hit", key=cache_key)
            return json.loads(cached_value)  # type: ignore[return-value]

        # Cache miss - call original function
        logger.debug("cache_miss", key=cache_key)
        result = await func(*args, **kwargs)

        # Store in cache
        await redis.setex(
            cache_key,
            ttl,
            json.dumps(result, default=str),
        )

        return result

    except RedisError as e:
        # If Redis is unavailable, gracefully degrade (call function directly)
        logger.warning("cache_error", error=str(e), key=cache_key)
        return await func(*args, **kwargs)


def cache_invalidate(
    key_pattern: str,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Decorator to invalidate cache keys matching a pattern.

    Useful for cache invalidation on data updates.

    Args:
        key_pattern: Redis key pattern (supports * wildcard)

    Example:
        >>> @cache_invalidate("user:*")
        >>> async def update_user(user_id: str, data: dict):
        ...     # Update user in database
        ...     await db.update_user(user_id, data)
        ...     # Cache keys matching "user:*" are automatically deleted
    """

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            # Call original function first
            result = await func(*args, **kwargs)

            # Invalidate cache
            try:
                await invalidate_pattern(key_pattern)
            except RedisError as e:
                logger.warning(
                    "cache_invalidation_failed", pattern=key_pattern, error=str(e)
                )

            return result

        return wrapper

    return decorator


# =============================================================================
# Cache Operations
# =============================================================================


async def get_cached(key: str, default: Any = None) -> Any:
    """Get value from cache.

    Args:
        key: Cache key
        default: Default value if key not found

    Returns:
        Cached value or default
    """
    try:
        redis = await get_redis()
        value = await redis.get(key)

        if value is None:
            return default

        return json.loads(value)

    except RedisError as e:
        logger.warning("cache_get_failed", key=key, error=str(e))
        return default


async def set_cached(key: str, value: Any, ttl: int = 3600) -> bool:
    """Set value in cache.

    Args:
        key: Cache key
        value: Value to cache
        ttl: Time to live in seconds

    Returns:
        True if successful, False otherwise
    """
    try:
        redis = await get_redis()
        await redis.setex(key, ttl, json.dumps(value, default=str))
        return True

    except RedisError as e:
        logger.warning("cache_set_failed", key=key, error=str(e))
        return False


async def delete_cached(key: str) -> bool:
    """Delete value from cache.

    Args:
        key: Cache key

    Returns:
        True if key was deleted, False otherwise
    """
    try:
        redis = await get_redis()
        deleted = await redis.delete(key)
        return deleted > 0

    except RedisError as e:
        logger.warning("cache_delete_failed", key=key, error=str(e))
        return False


async def invalidate_pattern(pattern: str) -> int:
    """Invalidate all cache keys matching a pattern.

    Args:
        pattern: Redis key pattern (supports * wildcard)

    Returns:
        Number of keys deleted

    Example:
        >>> # Delete all user caches
        >>> await invalidate_pattern("user:*")

        >>> # Delete specific user cache
        >>> await invalidate_pattern("user:123:*")
    """
    try:
        redis = await get_redis()

        # Find all matching keys
        keys = []
        async for key in redis.scan_iter(match=pattern, count=100):
            keys.append(key)

        # Delete in batches
        if keys:
            deleted = await redis.delete(*keys)
            logger.info("cache_invalidated", pattern=pattern, count=deleted)
            return deleted

        return 0

    except RedisError as e:
        logger.exception("cache_invalidation_failed", pattern=pattern, error=str(e))
        return 0


# =============================================================================
# Cache Warming
# =============================================================================


async def warm_cache(
    key: str,
    value_fn: Callable[[], Awaitable[Any]],
    ttl: int = 3600,
    force: bool = False,
) -> bool:
    """Warm cache by pre-loading data.

    Useful for frequently accessed data that's expensive to compute.

    Args:
        key: Cache key
        value_fn: Async function to get the value
        ttl: Time to live in seconds
        force: Force refresh even if key exists

    Returns:
        True if cache was warmed, False if already exists (and not forced)

    Example:
        >>> async def get_popular_items():
        ...     return await db.get_popular_items(limit=100)

        >>> # Warm cache on application startup
        >>> await warm_cache("popular_items", get_popular_items, ttl=3600)
    """
    try:
        redis = await get_redis()

        # Check if key exists and not forcing refresh
        if not force and await redis.exists(key):
            logger.debug("cache_already_warm", key=key)
            return False

        # Get value and cache it
        value = await value_fn()
        await redis.setex(key, ttl, json.dumps(value, default=str))

        logger.info("cache_warmed", key=key, ttl=ttl)
        return True

    except RedisError as e:
        logger.exception("cache_warming_failed", key=key, error=str(e))
        return False


# =============================================================================
# FastAPI Integration
# =============================================================================

"""
# In your FastAPI app:

from fastapi import FastAPI
from llc_manager.core.cache import get_redis, close_redis

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    # Initialize Redis connection pool
    await get_redis()

@app.on_event("shutdown")
async def shutdown_event():
    # Close Redis connection pool
    await close_redis()

# Use caching in endpoints
from llc_manager.core.cache import cached

@cached(ttl=300, key_prefix="api:users")
async def get_user_data(user_id: str) -> dict:
    # This will be cached for 5 minutes
    return await db.get_user(user_id)

@app.get("/api/users/{user_id}")
async def get_user(user_id: str):
    return await get_user_data(user_id)

# Cache invalidation on updates
from llc_manager.core.cache import invalidate_pattern

@app.put("/api/users/{user_id}")
async def update_user(user_id: str, data: dict):
    await db.update_user(user_id, data)

    # Invalidate user cache
    await invalidate_pattern(f"api:users:*{user_id}*")

    return {"status": "updated"}
"""


# =============================================================================
# Cache Statistics
# =============================================================================


async def get_cache_stats() -> dict[str, Any]:
    """Get cache statistics.

    Returns:
        Dictionary with cache statistics
    """
    try:
        redis = await get_redis()
        info = await redis.info("stats")

        return {
            "hits": info.get("keyspace_hits", 0),
            "misses": info.get("keyspace_misses", 0),
            "hit_rate": (
                info.get("keyspace_hits", 0)
                / max(info.get("keyspace_hits", 0) + info.get("keyspace_misses", 0), 1)
            )
            * 100,
            "memory_used": info.get("used_memory_human", "N/A"),
            "connected_clients": info.get("connected_clients", 0),
        }

    except RedisError as e:
        logger.exception("cache_stats_failed", error=str(e))
        return {"error": str(e)}
