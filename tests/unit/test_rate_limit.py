"""Unit tests for soc_db.rate_limit — in-memory, Redis, and factory."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from soc_db.rate_limit import (
    InMemoryRateLimiter,
    RedisRateLimiter,
    create_rate_limiter,
)


def _make_redis_mock(ping_ok: bool = True, pipe_result: list | None = None) -> MagicMock:
    """Build a mock Redis client with async ping and pipeline."""
    redis_mock = MagicMock()
    redis_mock.ping = AsyncMock(return_value=ping_ok)
    redis_mock.aclose = AsyncMock()

    # Use MagicMock for pipe to avoid coroutine warnings on un-awaited pipeline calls
    pipe = MagicMock()
    pipe.execute = AsyncMock(return_value=pipe_result if pipe_result is not None else [0, 2])
    redis_mock.pipeline.return_value = pipe
    return redis_mock


# ===========================================================================
# InMemoryRateLimiter
# ===========================================================================


class TestInMemoryRateLimiter:
    """Sliding-window correctness for the in-memory implementation."""

    async def test_allows_within_limit(self) -> None:
        limiter = InMemoryRateLimiter(limit=3, window=60)
        r1 = await limiter.check("ip1")
        assert r1 == (True, 3, 2, r1[3])
        assert r1[3] > 0

        r2 = await limiter.check("ip1")
        assert r2 == (True, 3, 1, r2[3])

        r3 = await limiter.check("ip1")
        assert r3 == (True, 3, 0, r3[3])

    async def test_blocks_when_exceeded(self) -> None:
        limiter = InMemoryRateLimiter(limit=3, window=60)
        for _ in range(3):
            await limiter.check("ip1")
        r4 = await limiter.check("ip1")
        assert r4 == (False, 3, 0, r4[3])
        assert r4[3] > 0

    async def test_window_slides(self) -> None:
        limiter = InMemoryRateLimiter(limit=1, window=0.1)
        r1 = await limiter.check("ip1")
        assert r1[0] is True
        await asyncio.sleep(0.15)
        r2 = await limiter.check("ip1")
        assert r2[0] is True  # old entry expired

    async def test_multiple_keys_independent(self) -> None:
        limiter = InMemoryRateLimiter(limit=2, window=60)
        # Exhaust ip1
        await limiter.check("ip1")
        await limiter.check("ip1")
        r1_3 = await limiter.check("ip1")
        assert r1_3[0] is False

        # ip2 should still have capacity
        r2_1 = await limiter.check("ip2")
        assert r2_1[0] is True
        r2_2 = await limiter.check("ip2")
        assert r2_2[0] is True
        r2_3 = await limiter.check("ip2")
        assert r2_3[0] is False

    async def test_remaining_decrements_correctly(self) -> None:
        limiter = InMemoryRateLimiter(limit=5, window=60)
        r1 = await limiter.check("ip1")
        assert r1[2] == 4
        r2 = await limiter.check("ip1")
        assert r2[2] == 3
        r3 = await limiter.check("ip1")
        assert r3[2] == 2

    async def test_is_redis_connected_returns_false(self) -> None:
        limiter = InMemoryRateLimiter(limit=5, window=60)
        assert limiter.is_redis_connected is False

    async def test_active_clients_tracks_keys(self) -> None:
        limiter = InMemoryRateLimiter(limit=5, window=60)
        assert limiter.active_clients == 0
        await limiter.check("ip1")
        await limiter.check("ip2")
        assert limiter.active_clients == 2


# ===========================================================================
# RedisRateLimiter (mocked)
# ===========================================================================


class TestRedisRateLimiter:
    """Behaviour of the Redis-backed limiter using mocked connections."""

    @patch("redis.asyncio.from_url")
    async def test_check_allowed(self, mock_from_url: MagicMock) -> None:
        redis_mock = _make_redis_mock(pipe_result=[0, 2])  # count=2 < limit=5
        mock_from_url.return_value = redis_mock

        limiter = RedisRateLimiter("redis://localhost:6379/0", limit=5, window=60)
        await limiter._ensure_connected()
        allowed, limit, remaining, reset = await limiter.check("ip1")

        assert allowed is True
        assert limit == 5
        assert remaining == 2  # 5 - 2 - 1 = 2
        assert reset > 0

        # Second pipeline (zadd + expire) should have been called
        pipe = redis_mock.pipeline.return_value
        assert pipe.zadd.called
        assert pipe.expire.called

    @patch("redis.asyncio.from_url")
    async def test_check_blocked(self, mock_from_url: MagicMock) -> None:
        redis_mock = _make_redis_mock(pipe_result=[0, 5])  # count=5 >= limit=5
        mock_from_url.return_value = redis_mock

        limiter = RedisRateLimiter("redis://localhost:6379/0", limit=5, window=60)
        await limiter._ensure_connected()
        allowed, limit, remaining, reset = await limiter.check("ip1")

        assert allowed is False
        assert limit == 5
        assert remaining == 0
        assert reset > 0

        # Record pipeline (zadd) should NOT have been called
        pipe = redis_mock.pipeline.return_value
        assert not pipe.zadd.called

    @patch("redis.asyncio.from_url")
    async def test_connection_error_raises(self, mock_from_url: MagicMock) -> None:
        mock_from_url.side_effect = ConnectionError("Connection refused")

        limiter = RedisRateLimiter("redis://localhost:6379/0", limit=5, window=60)
        with pytest.raises(ConnectionError):
            await limiter._ensure_connected()

    @patch("redis.asyncio.from_url")
    async def test_is_redis_connected(self, mock_from_url: MagicMock) -> None:
        redis_mock = _make_redis_mock()
        mock_from_url.return_value = redis_mock

        limiter = RedisRateLimiter("redis://localhost:6379/0", limit=5, window=60)

        # Before connect
        assert limiter.is_redis_connected is False

        # After successful connect
        await limiter._ensure_connected()
        assert limiter.is_redis_connected is True

        # After close
        await limiter.close()
        assert limiter.is_redis_connected is False

    @patch("redis.asyncio.from_url")
    async def test_reconnect_on_failure(self, mock_from_url: MagicMock) -> None:
        redis_mock = _make_redis_mock()
        mock_from_url.return_value = redis_mock

        limiter = RedisRateLimiter("redis://localhost:6379/0", limit=5, window=60)
        await limiter._ensure_connected()

        # Simulate pipeline failure on check
        pipe = redis_mock.pipeline.return_value
        pipe.execute.side_effect = ConnectionError("Lost connection")

        with pytest.raises(ConnectionError):
            await limiter.check("ip1")

        # _redis should be None after failure
        assert limiter._redis is None
        assert limiter.is_redis_connected is False


# ===========================================================================
# Factory
# ===========================================================================


class TestCreateRateLimiter:
    """Factory function fallback logic."""

    async def test_redis_url_none_returns_in_memory(self) -> None:
        limiter = await create_rate_limiter(redis_url=None, limit=100, window=60)
        assert isinstance(limiter, InMemoryRateLimiter)

    async def test_empty_redis_url_returns_in_memory(self) -> None:
        limiter = await create_rate_limiter(redis_url="", limit=100, window=60)
        assert isinstance(limiter, InMemoryRateLimiter)

    @patch("redis.asyncio.from_url")
    async def test_invalid_redis_url_falls_back(
        self, mock_from_url: MagicMock
    ) -> None:
        mock_from_url.side_effect = ConnectionError("Connection refused")

        limiter = await create_rate_limiter(
            redis_url="redis://invalid:6379", limit=100, window=60
        )
        assert isinstance(limiter, InMemoryRateLimiter)

    @patch("redis.asyncio.from_url")
    async def test_valid_redis_url_returns_redis(
        self, mock_from_url: MagicMock
    ) -> None:
        redis_mock = _make_redis_mock()
        mock_from_url.return_value = redis_mock

        limiter = await create_rate_limiter(
            redis_url="redis://localhost:6379", limit=100, window=60
        )
        assert isinstance(limiter, RedisRateLimiter)
        await limiter.close()
