"""Tiered HTTP fetcher with automatic anti-bot escalation.

``HTTPSource`` provides three tiers of HTTP fetching:

1. **httpx** — fast, HTTP/2, standard requests.
2. **curl-cffi** — Chrome TLS fingerprint impersonation for anti-bot bypass.
3. **Playwright** — full headless browser as last resort.

Each tier is tried in order. If a tier raises a retryable exception
(ConnectionError, TimeoutError, HTTP 403/429), the next tier is tried.
If all tiers fail, the last exception propagates.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from soc_db.common import CACHE_DIR, USER_AGENT, guard_path
from soc_db.scraping.rate_limit import PerSourceRateLimiter

logger = logging.getLogger(__name__)

# Optional dependency guards
try:
    import curl_cffi.requests  # noqa: F401

    _HAS_CURL = True
except ImportError:
    _HAS_CURL = False

try:
    from playwright.sync_api import sync_playwright  # noqa: F401

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


class HTTPSource:
    """Tiered HTTP fetcher: httpx → curl-cffi → Playwright.

    Each tier is tried in order. If a tier raises a retryable exception
    (ConnectionError, TimeoutError, HTTP 403/429), the next tier is tried.
    If all tiers fail, the last exception propagates.

    Args:
        rate_limiter: Optional per-source rate limiter.
        default_headers: Custom HTTP headers (merged with defaults).
        timeout: Request timeout in seconds.
        follow_redirects: Whether to follow HTTP redirects.
        cache_ttl: Cache TTL in seconds (default 86400 = 24h).
    """

    def __init__(
        self,
        rate_limiter: PerSourceRateLimiter | None = None,
        default_headers: dict[str, str] | None = None,
        timeout: float = 30.0,
        follow_redirects: bool = True,
        cache_ttl: int = 86400,
    ) -> None:
        self._rate_limiter = rate_limiter
        self._timeout = timeout
        self._follow_redirects = follow_redirects
        self._cache_ttl = cache_ttl
        self._logger = logging.getLogger(__name__)
        self._default_headers = dict(default_headers or {})

    # ── public API ──────────────────────────────────────────────────────

    def fetch(self, url: str, user_agent: str | None = None) -> str:
        """Fetch a URL through the tiered escalation chain.

        Checks disk cache first (if within TTL).  Tries each tier in
        order and escalates on 403/429/connection errors.

        Args:
            url: The URL to fetch.
            user_agent: Optional User-Agent override.

        Returns:
            The response body as a UTF-8 string.

        Raises:
            RuntimeError: If all tiers fail or Playwright is unavailable.
        """
        ua = user_agent or USER_AGENT

        # Check cache first
        cached = self._check_cache(url, ua)
        if cached is not None:
            return cached

        # Acquire rate limiter if configured
        if self._rate_limiter is not None:
            self._rate_limiter.acquire()

        # Build base headers
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        headers.update(self._default_headers)

        # Tier 1: httpx
        try:
            content = self._fetch_httpx(url, headers)
            self._write_cache(url, ua, content)
            if self._rate_limiter is not None:
                self._rate_limiter.record_success()
            return content
        except (ConnectionError, TimeoutError, OSError) as exc:
            self._logger.info(
                "[HTTPSource] httpx failed for %s: %s — escalating to curl-cffi", url, exc
            )

        # Tier 2: curl-cffi
        if _HAS_CURL:
            try:
                content = self._fetch_curl(url, headers)
                self._write_cache(url, ua, content)
                if self._rate_limiter is not None:
                    self._rate_limiter.record_success()
                return content
            except (ConnectionError, TimeoutError, OSError) as exc:
                self._logger.info(
                    "[HTTPSource] curl-cffi failed for %s: %s — escalating to Playwright", url, exc
                )
        else:
            self._logger.info("[HTTPSource] curl-cffi not installed — skipping tier 2")

        # Tier 3: Playwright
        if _HAS_PLAYWRIGHT:
            try:
                content = self._fetch_playwright(url, ua)
                self._write_cache(url, ua, content)
                if self._rate_limiter is not None:
                    self._rate_limiter.record_success()
                return content
            except Exception as exc:
                self._logger.error(
                    "[HTTPSource] Playwright failed for %s: %s — all tiers exhausted", url, exc
                )
                if self._rate_limiter is not None:
                    self._rate_limiter.record_failure()
                raise
        else:
            if self._rate_limiter is not None:
                self._rate_limiter.record_failure()
            raise RuntimeError(
                f"Playwright not installed. Run: pip install playwright && playwright install chromium"
            )

    # ── tier 1: httpx ───────────────────────────────────────────────────

    def _fetch_httpx(self, url: str, headers: dict[str, str]) -> str:
        """Fetch via httpx.  Raises on 403/429/connection errors."""
        import httpx

        with httpx.Client(
            follow_redirects=self._follow_redirects,
            timeout=self._timeout,
        ) as client:
            resp = client.get(url, headers=headers)

            if self._should_escalate(resp.status_code):
                raise ConnectionError(
                    f"HTTP {resp.status_code} for {url} (retryable — escalate)"
                )

            resp.raise_for_status()
            return resp.text

    # ── tier 2: curl-cffi ───────────────────────────────────────────────

    def _fetch_curl(self, url: str, headers: dict[str, str]) -> str:
        """Fetch via curl-cffi with Chrome TLS impersonation."""
        import curl_cffi.requests

        session = curl_cffi.requests.Session(impersonate="chrome120")
        resp = session.get(url, headers=headers, timeout=self._timeout)

        if self._should_escalate(resp.status_code):
            raise ConnectionError(
                f"HTTP {resp.status_code} for {url} (retryable — escalate)"
            )

        resp.raise_for_status()
        return resp.text

    # ── tier 3: Playwright ──────────────────────────────────────────────

    def _fetch_playwright(self, url: str, user_agent: str) -> str:
        """Fetch via Playwright headless Chromium."""
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(user_agent=user_agent)
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded")
            content = page.content()
            browser.close()
            return content

    # ── helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _should_escalate(status_code: int) -> bool:
        """Return ``True`` if the status code indicates anti-bot blocking."""
        return status_code in (403, 429, 503)

    # ── caching ─────────────────────────────────────────────────────────

    def _check_cache(self, url: str, user_agent: str) -> str | None:
        """Return cached content if fresh, or ``None``."""
        key = hashlib.md5(url.encode(), usedforsecurity=False).hexdigest()
        cache_file = CACHE_DIR / key
        if cache_file.exists():
            age = time.time() - cache_file.stat().st_mtime
            if age < self._cache_ttl:
                try:
                    meta = json.loads(cache_file.read_text("utf-8"))
                    if isinstance(meta, dict) and meta.get("user_agent") == user_agent:
                        self._logger.debug("[HTTPSource] Cache HIT for %s", url)
                        return meta.get("content", "")
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
        return None

    def _write_cache(self, url: str, user_agent: str, content: str) -> None:
        """Write content to disk cache."""
        key = hashlib.md5(url.encode(), usedforsecurity=False).hexdigest()
        cache_file = CACHE_DIR / key
        meta = {
            "url": url,
            "user_agent": user_agent,
            "content": content,
            "cached_at": time.time(),
        }
        try:
            guard_path(cache_file)
            cache_file.write_text(json.dumps(meta, ensure_ascii=False), "utf-8")
        except (PermissionError, OSError) as exc:
            self._logger.warning("[HTTPSource] Cache write failed: %s", exc)
