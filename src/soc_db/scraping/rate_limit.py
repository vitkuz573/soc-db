"""Per-source rate limiter with tenacity-based exponential backoff + jitter.

Every scraper source gets an independent ``PerSourceRateLimiter`` that:

* Throttles request frequency to a configurable ``requests_per_sec``.
* Tracks consecutive failures for backoff.
* Provides a ``retry_decorator`` (via tenacity) that wraps network calls
  with exponential backoff, jitter, and configurable retry limits.

This is intentionally simpler than the sliding-window Redis-based limiter
in ``soc_db.rate_limit`` — that one protects API endpoints from client
abuse, while this one protects target websites from scraper abuse.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable

import tenacity
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


class PerSourceRateLimiter:
    """Per-source rate limiter with exponential backoff + jitter.

    Each scraper source should have its own instance.  The limiter controls
    request frequency via ``acquire()`` and tracks consecutive failures so
    that the backoff strategy can react to repeated errors.

    Args:
        source_id: Unique identifier for the source (e.g. ``"wikipedia"``).
        requests_per_sec: Max sustained requests per second.
        burst: Max burst count before throttling.
        backoff_factor: Multiplier for exponential backoff.
        max_retries: Max retries before giving up.
        min_wait: Minimum wait between retries (seconds).
        max_wait: Maximum wait between retries (seconds).
        jitter: Add random ±25 % jitter to wait times.
    """

    def __init__(
        self,
        source_id: str,
        requests_per_sec: float = 1.0,
        burst: int = 3,
        backoff_factor: float = 2.0,
        max_retries: int = 5,
        min_wait: float = 0.5,
        max_wait: float = 60.0,
        jitter: bool = True,
    ) -> None:
        self._source_id = source_id
        self._requests_per_sec = requests_per_sec
        self._burst = burst
        self._backoff_factor = backoff_factor
        self._max_retries = max_retries
        self._min_wait = min_wait
        self._max_wait = max_wait
        self._jitter = jitter
        self._last_request_time: float = 0.0
        self._consecutive_failures: int = 0
        self._lock = threading.Lock()

    # ── public API ──────────────────────────────────────────────────────

    def acquire(self) -> None:
        """Block until the next request is allowed (synchronous).

        If the time since the last request is less than ``1 / requests_per_sec``
        seconds, this method sleeps for the remainder.
        """
        min_interval = 1.0 / self._requests_per_sec if self._requests_per_sec > 0 else 0.0
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < min_interval:
                sleep_for = min_interval - elapsed
                if self._jitter:
                    sleep_for *= 0.75 + random.random() * 0.5  # ±25 %
                logger.debug(
                    "[%s] Rate limiter sleep: %.3fs", self._source_id, sleep_for
                )
                time.sleep(sleep_for)
            self._last_request_time = time.monotonic()

    def record_failure(self) -> None:
        """Increment the consecutive-failure counter."""
        with self._lock:
            self._consecutive_failures += 1
            logger.debug(
                "[%s] Consecutive failures: %d",
                self._source_id,
                self._consecutive_failures,
            )

    def record_success(self) -> None:
        """Reset the consecutive-failure counter to zero."""
        with self._lock:
            self._consecutive_failures = 0

    def retry_decorator(self) -> Callable:
        """Return a tenacity retry decorator for a fetch function.

        The decorator retries on ``ConnectionError``, ``TimeoutError``,
        and ``IOError`` with exponential backoff + optional jitter.

        The jitter is handled by a custom ``wait`` function that applies
        ±25 % random jitter to the exponential wait time.

        Returns:
            A ``tenacity.retry``-decorated wrapper ready to apply to a
            callable.
        """
        def _wait_with_jitter(retry_state: tenacity.RetryCallState) -> float:
            """Exponential wait with ±25 % jitter."""
            exp_wait = wait_exponential(
                multiplier=self._backoff_factor,
                min=self._min_wait,
                max=self._max_wait,
            )(retry_state)
            if self._jitter:
                exp_wait *= 0.75 + random.random() * 0.5
            return exp_wait

        return retry(
            retry=retry_if_exception_type(
                (ConnectionError, TimeoutError, IOError)
            ),
            stop=stop_after_attempt(self._max_retries),
            wait=_wait_with_jitter,
            before_sleep=before_sleep_log(
                logger, logging.WARNING
            ),
            reraise=True,
        )

    # ── helpers ─────────────────────────────────────────────────────────

    @property
    def consecutive_failures(self) -> int:
        with self._lock:
            return self._consecutive_failures

    def __repr__(self) -> str:
        return (
            f"PerSourceRateLimiter(source={self._source_id}, "
            f"rate={self._requests_per_sec}/s)"
        )
