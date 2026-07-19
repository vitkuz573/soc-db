"""Per-domain robots.txt caching and compliance checking.

The RobotsChecker caches parsed robots.txt per domain with a configurable
TTL (default 24h) and exposes ``can_fetch(url, user_agent)``.  If a
domain's robots.txt is unreachable, fetching is allowed by default
(fail-open for resilience).
"""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

logger = logging.getLogger(__name__)

_DEFAULT_TTL = 86400  # 24 hours


class RobotsChecker:
    """Cached robots.txt checker per domain."""

    def __init__(self, ttl: int = _DEFAULT_TTL) -> None:
        self._ttl = ttl
        self._parsers: dict[str, tuple[float, RobotFileParser]] = {}

    def can_fetch(self, url: str, user_agent: str) -> bool:
        """Check if *url* is allowed for *user_agent* per robots.txt.

        Returns ``True`` if the domain's robots.txt allows the request,
        or if the robots.txt cannot be read (fail-open).

        Args:
            url: The full URL to check.
            user_agent: The User-Agent string to check against.

        Returns:
            ``True`` if allowed, ``False`` if disallowed.
        """
        parsed = urlparse(url)
        domain = parsed.netloc
        if not domain:
            return True  # No domain to check

        now = time.time()
        rp = self._get_parser(domain, now)
        if rp is None:
            logger.debug("No robots.txt for %s — allowing by default", domain)
            return True
        return rp.can_fetch(user_agent, url)

    def _get_parser(self, domain: str, now: float) -> RobotFileParser | None:
        """Return a cached (or freshly-fetched) RobotFileParser for *domain*.

        Returns None if the robots.txt could not be fetched.
        """
        if domain in self._parsers:
            cached_at, rp = self._parsers[domain]
            if now - cached_at < self._ttl:
                return rp
        rp = RobotFileParser()
        rp.set_url(f"https://{domain}/robots.txt")
        try:
            rp.read()
        except Exception:
            logger.warning(
                "Could not fetch robots.txt for %s — allowing by default", domain
            )
            self._parsers[domain] = (now, rp)
            # Return None to signal fail-open: we don't know the rules, so allow
            return None
        self._parsers[domain] = (now, rp)
        return rp

    def clear_cache(self) -> None:
        """Clear all cached robots.txt data."""
        self._parsers.clear()
