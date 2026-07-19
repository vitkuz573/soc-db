"""Rate limiter library with dual implementation.

Provides a ``RateLimiter`` protocol that both in-memory and Redis-backed
implementations satisfy.  The ``create_rate_limiter()`` factory tries Redis
first and falls back to in-memory when Redis is unavailable, so the
application always gets a working rate limiter.

Usage::

    from soc_db.rate_limit import create_rate_limiter

    limiter = await create_rate_limiter(
        redis_url="redis://localhost:6379/0",
        limit=100,
        window=60,
    )
    allowed, limit, remaining, reset = await limiter.check("client-ip")
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import Protocol, runtime_checkable

logger = logging.getLogger("soc_db.rate_limit")


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------
@runtime_checkable
class RateLimiter(Protocol):
    """Interface for sliding-window rate limiter implementations."""

    async def check(self, key: str) -> tuple[bool, int, int, float]:
        """Check whether *key* is allowed through the rate limit.

        Returns:
            ``(allowed, limit, remaining, reset_timestamp)`` where
            *reset_timestamp* is a Unix-epoch float representing when
            the current window expires.
        """
        ...

    @property
    def is_redis_connected(self) -> bool:
        """Whether Redis is currently connected (always ``False`` for in-memory)."""
        ...

    @property
    def active_clients(self) -> int:
        """Approximate count of distinct tracked keys."""
        ...


# ---------------------------------------------------------------------------
# In-memory implementation
# ---------------------------------------------------------------------------
class InMemoryRateLimiter:
    """Sliding-window rate limiter using an in-memory ``defaultdict[list[float]]``.

    Safe for single-worker deployments.  Uses an ``asyncio.Lock`` to prevent
    concurrent dictionary mutation races.
    """

    def __init__(self, limit: int, window: int) -> None:
        self._limit = limit
        self._window = window
        self._buckets: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> tuple[bool, int, int, float]:
        now = time.monotonic()
        cutoff = now - self._window
        async with self._lock:
            bucket = self._buckets[key]
            # Prune expired entries
            while bucket and bucket[0] < cutoff:
                bucket.pop(0)
            count = len(bucket)
            allowed = count < self._limit
            if allowed:
                bucket.append(now)
                remaining = max(0, self._limit - count - 1)
            else:
                remaining = 0
            reset_time = cutoff + self._window
        return (allowed, self._limit, remaining, reset_time)

    @property
    def is_redis_connected(self) -> bool:
        return False

    @property
    def active_clients(self) -> int:
        """Approximate count of distinct keys tracked.

        Note: may include entries whose timestamps have expired but whose
        dict keys have not yet been garbage-collected.
        """
        return len(self._buckets)


# ---------------------------------------------------------------------------
# Redis-backed implementation
# ---------------------------------------------------------------------------
class RedisRateLimiter:
    """Sliding-window rate limiter backed by Redis sorted sets.

    Uses ``ZREMRANGEBYSCORE`` + ``ZCARD`` (prune + count) in a pipeline,
    then ``ZADD`` + ``EXPIRE`` to record the request.  The key TTL is set to
    ``2 × window`` so the prune step eventually cleans up even if a key is
    never checked again.
    """

    def __init__(
        self,
        redis_url: str,
        limit: int,
        window: int,
        socket_connect_timeout: int = 2,
    ) -> None:
        self._redis_url = redis_url
        self._limit = limit
        self._window = window
        self._socket_connect_timeout = socket_connect_timeout
        self._redis: asyncio.redis.Redis | None = None  # type: ignore[name-defined]  # noqa: F821
        self._connected = False

    async def ensure_connected(self) -> None:
        """Lazy-connect to Redis with a short timeout."""
        if self._redis is not None:
            return
        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(
            self._redis_url,
            socket_connect_timeout=self._socket_connect_timeout,
            single_connection_client=True,
        )
        try:
            await self._redis.ping()
            self._connected = True
        except Exception:
            self._redis = None
            self._connected = False
            raise ConnectionError(f"Could not connect to Redis at {self._redis_url}") from None

    async def check(self, key: str) -> tuple[bool, int, int, float]:
        try:
            await self.ensure_connected()
        except ConnectionError:
            raise

        now = time.time()
        window_start = now - self._window
        redis_key = f"ratelimit:{key}"

        try:
            # Prune + count pipeline
            pipe = self._redis.pipeline()  # type: ignore[union-attr]
            pipe.zremrangebyscore(redis_key, 0, window_start)
            pipe.zcard(redis_key)
            results = await pipe.execute()
            count = results[1]

            if count >= self._limit:
                remaining = 0
                reset_time = now + self._window
                return (False, self._limit, remaining, reset_time)

            remaining = self._limit - count - 1

            # Record + TTL pipeline
            pipe = self._redis.pipeline()  # type: ignore[union-attr]
            pipe.zadd(redis_key, {str(now): now})
            pipe.expire(redis_key, self._window * 2)
            await pipe.execute()

            reset_time = now + self._window
            return (True, self._limit, remaining, reset_time)

        except Exception:
            self._redis = None
            self._connected = False
            logger.warning("Redis error during rate-limit check", exc_info=True)
            raise ConnectionError("Redis connection lost") from None

    @property
    def is_redis_connected(self) -> bool:
        return self._connected

    @property
    def active_clients(self) -> int:
        # Not meaningful for Redis — would require SCAN.
        return 0

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        self._connected = False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
async def create_rate_limiter(
    redis_url: str | None = None,
    limit: int = 100,
    window: int = 60,
    socket_connect_timeout: int = 2,
) -> RateLimiter:
    """Return a :class:`RateLimiter` — Redis-backed if possible, otherwise in-memory.

    When *redis_url* is ``None`` or empty, an :class:`InMemoryRateLimiter` is
    returned immediately.  When *redis_url* is set but unreachable, a warning
    is logged and the in-memory fallback is returned — the factory **never**
    raises or returns a broken limiter.
    """
    if not redis_url:
        logger.info("In-memory rate limiter active")
        return InMemoryRateLimiter(limit, window)

    limiter = RedisRateLimiter(
        redis_url,
        limit,
        window,
        socket_connect_timeout=socket_connect_timeout,
    )
    try:
        await limiter.ensure_connected()
        logger.info("Redis rate limiter active at %s", redis_url)
        return limiter
    except ConnectionError:
        logger.warning(
            "Redis unavailable at %s, falling back to in-memory rate limiter",
            redis_url,
        )
        return InMemoryRateLimiter(limit, window)
