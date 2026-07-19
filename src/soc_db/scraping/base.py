"""BaseScraper ABC and ChipScrapeResult dataclass for the scraper framework.

Every scraper source subclasses BaseScraper and implements ``fetch()`` and
``parse()``.  The ``run()`` lifecycle method orchestrates fetch → parse →
dedup → write in order, with robots.txt checking and per-source rate
limiting built in.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from soc_db.common import USER_AGENT, write_vendor_file
from soc_db.robots import RobotsChecker
from soc_db.scraping.rate_limit import PerSourceRateLimiter

logger = logging.getLogger(__name__)

# Per-source User-Agent overrides — merged from soc_db.common.SCRAPER_USER_AGENTS
SCRAPER_USER_AGENTS: dict[str, str] = {
    "wikipedia": "SOC-DB-Wikipedia/1.0 (+https://github.com/vitkuz573/soc-db)",
    "wikidata": "SOC-DB-Wikidata/1.0 (+https://github.com/vitkuz573/soc-db)",
    "apple": "SOC-DB-Apple/1.0 (+https://github.com/vitkuz573/soc-db)",
    "linux_dt": "SOC-DB-DeviceTree/1.0 (+https://github.com/vitkuz573/soc-db)",
    "techpowerup": "SOC-DB-TPU/1.0 (+https://github.com/vitkuz573/soc-db)",
    "notebookcheck": "SOC-DB-NBC/1.0 (+https://github.com/vitkuz573/soc-db)",
    "geekbench": "SOC-DB-GB/1.0 (+https://github.com/vitkuz573/soc-db)",
    "qualcomm": "SOC-DB-Qualcomm/1.0 (+https://github.com/vitkuz573/soc-db)",
    "mediatek": "SOC-DB-MediaTek/1.0 (+https://github.com/vitkuz573/soc-db)",
    "intel": "SOC-DB-Intel/1.0 (+https://github.com/vitkuz573/soc-db)",
    "amd": "SOC-DB-AMD/1.0 (+https://github.com/vitkuz573/soc-db)",
}


@dataclass
class ChipScrapeResult:
    """Normalised result from a single chip row parsed by a scraper."""

    name: str
    vendor: str
    model: str | None = None
    fields: dict[str, Any] = field(default_factory=dict)
    source_id: str = ""
    raw_html: str | None = None


class BaseScraper(ABC):
    """Abstract base class for all SoC scraper sources.

    Subclasses must define:

    * ``SOURCE_ID`` — a unique string identifier (e.g. ``"wikipedia"``).
    * ``VENDORS`` — list of vendor names this scraper handles.
    * ``fetch()`` — returns raw data (HTML string, parsed DOM, etc.).
    * ``parse()`` — converts raw data into ``list[ChipScrapeResult]``.

    The ``run()`` method orchestrates the full lifecycle:

    ``check_robots → fetch → parse → dedup → write``
    """

    SOURCE_ID: ClassVar[str] = ""
    VENDORS: ClassVar[list[str]] = []
    PRIORITY: ClassVar[int] = 50
    RATE_LIMIT_CONFIG: ClassVar[dict | None] = None

    def __init__(
        self,
        robots_checker: RobotsChecker | None = None,
        rate_limiter: PerSourceRateLimiter | None = None,
    ) -> None:
        if rate_limiter is not None:
            self._rate_limiter = rate_limiter
        else:
            config = self.RATE_LIMIT_CONFIG or {}
            self._rate_limiter = PerSourceRateLimiter(
                source_id=self.SOURCE_ID,
                requests_per_sec=config.get("requests_per_sec", 1.0),
                burst=config.get("burst", 3),
                backoff_factor=config.get("backoff_factor", 2.0),
                max_retries=config.get("max_retries", 5),
                min_wait=config.get("min_wait", 0.5),
                max_wait=config.get("max_wait", 60.0),
                jitter=config.get("jitter", True),
            )

        self._robots_checker = robots_checker or RobotsChecker()

    # ── properties ──────────────────────────────────────────────────────

    @property
    def rate_limiter(self) -> PerSourceRateLimiter:
        return self._rate_limiter

    @rate_limiter.setter
    def rate_limiter(self, value: PerSourceRateLimiter) -> None:
        self._rate_limiter = value

    @property
    def source_name(self) -> str:
        return self.SOURCE_ID

    @property
    def user_agent(self) -> str:
        return SCRAPER_USER_AGENTS.get(self.SOURCE_ID, USER_AGENT)

    # ── lifecycle helpers ───────────────────────────────────────────────

    def check_robots(self, url: str) -> bool:
        """Check robots.txt for *url* and raise if disallowed.

        Returns ``True`` if allowed.

        Raises:
            PermissionError: If robots.txt disallows the URL.
        """
        if not self._robots_checker.can_fetch(url, self.user_agent):
            raise PermissionError(f"robots.txt disallows {url}")
        return True

    # ── subclass hooks ──────────────────────────────────────────────────

    @abstractmethod
    def fetch(self) -> Any:
        """Fetch raw data from the source.

        Returns:
            Raw HTML string, parsed DOM, or any intermediate representation.
        """
        ...

    @abstractmethod
    def parse(self, raw: Any) -> list[ChipScrapeResult]:
        """Convert raw fetch output into normalised chip results.

        Args:
            raw: The value returned by ``fetch()``.

        Returns:
            A list of ``ChipScrapeResult`` instances.
        """
        ...

    # ── overridable steps ───────────────────────────────────────────────

    def dedup(self, results: list[ChipScrapeResult]) -> list[ChipScrapeResult]:
        """Remove duplicate results based on ``(vendor, model, name)``.

        Args:
            results: Parsed chip results, potentially with duplicates.

        Returns:
            Deduplicated list preserving insertion order.
        """
        seen: set[tuple[str, str | None, str]] = set()
        out: list[ChipScrapeResult] = []
        for r in results:
            key = (r.vendor, r.model, r.name)
            if key not in seen:
                seen.add(key)
                out.append(r)
        return out

    def write(self, results: list[ChipScrapeResult]) -> None:
        """Write scraped results to vendor files.

        Groups results by vendor, converts each to a plain dict, and
        delegates to ``common.write_vendor_file``.

        Args:
            results: Deduplicated chip results to persist.
        """
        by_vendor: dict[str, list[dict[str, Any]]] = {}
        for r in results:
            by_vendor.setdefault(r.vendor, []).append(dict(r.fields))
        for vendor, chips in by_vendor.items():
            write_vendor_file(vendor, chips)

    # ── lifecycle orchestrator ──────────────────────────────────────────

    def run(self) -> list[ChipScrapeResult]:
        """Execute the full scrape lifecycle.

        Steps:
        1. Fetch raw data from the source (via ``fetch()``).
        2. Parse raw data into ``ChipScrapeResult`` list (via ``parse()``).
        3. Deduplicate results (via ``dedup()``).
        4. Persist results (via ``write()``).

        Returns:
            The final deduplicated list of chip results.
        """
        logger.info("[%s] Starting scrape run", self.SOURCE_ID)
        raw = self.fetch()
        results = self.parse(raw)
        logger.info("[%s] Parsed %d chip(s)", self.SOURCE_ID, len(results))
        deduped = self.dedup(results)
        if len(deduped) < len(results):
            logger.info(
                "[%s] Dedup removed %d duplicate(s)",
                self.SOURCE_ID,
                len(results) - len(deduped),
            )
        self.write(deduped)
        logger.info("[%s] Scrape run complete — %d chip(s) written", self.SOURCE_ID, len(deduped))
        return deduped
