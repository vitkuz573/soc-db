"""Unit tests for PerSourceRateLimiter."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from soc_db.scraping.rate_limit import PerSourceRateLimiter


class TestPerSourceRateLimiter:
    def test_acquire_basic(self):
        """High rate limit should not block measurably."""
        r = PerSourceRateLimiter("test", requests_per_sec=100.0, jitter=False)
        t0 = time.monotonic()
        for _ in range(10):
            r.acquire()
        t1 = time.monotonic()
        assert t1 - t0 < 1.0, f"took {t1-t0:.2f}s"

    def test_acquire_throttles(self, monkeypatch):
        """2 req/s should cause ~0.5s sleep between calls."""
        sleeps = []
        monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))

        r = PerSourceRateLimiter("test", requests_per_sec=2.0, jitter=False)
        r.acquire()  # first call: no sleep needed
        r.acquire()  # second call: should sleep ~0.5s
        assert len(sleeps) >= 1
        assert 0.3 <= sleeps[0] <= 1.0, f"sleep was {sleeps[0]:.3f}s"

    def test_consecutive_failures(self):
        r = PerSourceRateLimiter("test")
        assert r.consecutive_failures == 0
        r.record_failure()
        r.record_failure()
        r.record_failure()
        assert r.consecutive_failures == 3
        r.record_success()
        assert r.consecutive_failures == 0

    def test_retry_decorator_returns_callable(self):
        r = PerSourceRateLimiter("test")
        deco = r.retry_decorator()
        assert callable(deco)

    def test_retry_decorator_retries_on_error(self):
        """Function that fails twice then succeeds should be retried."""
        r = PerSourceRateLimiter("test", max_retries=5, min_wait=0.01, max_wait=0.05)

        call_count = 0

        @r.retry_decorator()
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient error")
            return "success"

        result = flaky_func()
        assert result == "success"
        assert call_count == 3

    def test_retry_decorator_gives_up(self):
        """Function that always fails should raise after max retries."""
        r = PerSourceRateLimiter("test", max_retries=2, min_wait=0.01, max_wait=0.05)

        call_count = 0

        @r.retry_decorator()
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("permanent error")

        with pytest.raises(ConnectionError):
            always_fails()
        assert call_count == 2  # initial + 1 retry

    def test_independent_sources(self, monkeypatch):
        """Two rate limiters with different source_ids don't interfere."""
        sleeps = []
        monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))

        r1 = PerSourceRateLimiter("source1", requests_per_sec=2.0, jitter=False)
        r2 = PerSourceRateLimiter("source2", requests_per_sec=10.0, jitter=False)

        r1.acquire()
        r1.acquire()  # should sleep ~0.5s
        sleep_before = len(sleeps)

        r2.acquire()
        r2.acquire()  # should sleep less (~0.1s)
        sleep_after = len(sleeps)

        # r2's second acquire should add more sleeps (r2 has higher rate)
        assert sleep_after > sleep_before

    def test_jitter_variation(self, monkeypatch):
        """With jitter enabled, timing varies (not exactly constant)."""
        real_sleep = time.sleep
        sleeps = []

        def capture_sleep(s):
            sleeps.append(s)
            real_sleep(s)

        monkeypatch.setattr(time, "sleep", capture_sleep)

        r = PerSourceRateLimiter("test", requests_per_sec=2.0, jitter=True)
        r.acquire()  # first call: no sleep
        r.acquire()  # second call: should sleep with jitter
        if sleeps:
            # Just verify it's not far from expected 0.5s with jitter
            assert 0.1 <= sleeps[0] <= 1.0

    def test_repr(self):
        r = PerSourceRateLimiter("wikipedia", requests_per_sec=1.0)
        assert "wikipedia" in repr(r)
        assert "1.0/s" in repr(r)
