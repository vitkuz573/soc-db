"""AppleScraper — BaseScraper implementation for Apple Silicon chips.

Reuses the APPLE_CHIPS dict and parse_tables() logic from the legacy
``soc_db.scraper_apple`` module within the new framework's fetch →
parse → dedup → write lifecycle.
"""

from __future__ import annotations

import logging
from typing import Any

from bs4 import BeautifulSoup

from soc_db.common import fetch, slug
from soc_db.parsers import parse_cpu, parse_gpu, parse_process
from soc_db.scraper_apple import APPLE_CHIPS
from soc_db.scraping.base import BaseScraper, ChipScrapeResult
from soc_db.scraping.source import HTTPSource

logger = logging.getLogger(__name__)

WIKI_A = "https://en.wikipedia.org/wiki/Apple_A_series"
WIKI_M = "https://en.wikipedia.org/wiki/Apple_M_series"


class AppleScraper(BaseScraper):
    """Scraper for Apple Silicon chips (A-series and M-series).

    Fetches Wikipedia tables for Apple A and M series, parses them
    using the existing ``parse_tables()`` logic, and writes per-vendor
    chip files.
    """

    SOURCE_ID = "apple"
    VENDORS = ["Apple"]
    PRIORITY = 40

    RATE_LIMIT_CONFIG: dict[str, float | int] = {
        "requests_per_sec": 1.0,
        "burst": 2,
        "backoff_factor": 2.0,
        "max_retries": 3,
    }

    def __init__(self, robots_checker=None, rate_limiter=None) -> None:
        super().__init__(robots_checker, rate_limiter)
        self._http = HTTPSource(rate_limiter=self._rate_limiter)
        self._raw_pages: dict[str, str] = {}

    # ── fetch ───────────────────────────────────────────────────────────

    def fetch(self) -> dict[str, str]:
        """Fetch Apple A-series and M-series Wikipedia pages.

        Returns:
            Dict mapping ``"A"`` and ``"M"`` to their HTML content.
        """
        self._raw_pages = {}

        logger.info("[AppleScraper] Fetching Apple A-series...")
        self.check_robots(WIKI_A)
        self._raw_pages["A"] = self._http.fetch(WIKI_A, user_agent=self.user_agent)

        logger.info("[AppleScraper] Fetching Apple M-series...")
        self.check_robots(WIKI_M)
        self._raw_pages["M"] = self._http.fetch(WIKI_M, user_agent=self.user_agent)

        return self._raw_pages

    # ── parse ───────────────────────────────────────────────────────────

    def parse(self, raw: dict[str, str]) -> list[ChipScrapeResult]:
        """Parse raw HTML pages into ChipScrapeResults.

        Args:
            raw: Dict mapping series (``"A"``, ``"M"``) to HTML strings.

        Returns:
            List of parsed chip results.
        """
        results: list[ChipScrapeResult] = []
        seen_ids: set[str] = set()

        for series, html in raw.items():
            chips = parse_tables(html, series)
            for chip in chips:
                chip["vendor"] = "Apple"
                if chip["id"] not in seen_ids:
                    seen_ids.add(chip["id"])
                    results.append(
                        ChipScrapeResult(
                            name=chip.get("name", ""),
                            vendor="Apple",
                            model=chip.get("model"),
                            fields=dict(chip),
                            source_id=self.SOURCE_ID,
                        )
                    )

        return results


# ── shared helper (reused from scripts/scraper_apple.py) ──────────────


def parse_tables(html: str, series: str) -> list[dict[str, Any]]:
    """Parse Apple chip tables from Wikipedia HTML.

    Args:
        html: The HTML content of a Wikipedia page.
        series: Series identifier (``"A"`` or ``"M"``).

    Returns:
        List of chip dicts parsed from the tables.
    """
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table", class_="wikitable")
    chips: list[dict[str, Any]] = []
    seen: set[str] = set()

    for tbl in tables:
        rows = tbl.find_all("tr")
        for tr in rows:
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue
            name_text = tds[0].get_text(" ", strip=True)
            model_text = tds[1].get_text(" ", strip=True) if len(tds) > 1 else ""
            clean_name = name_text.strip()
            clean_model = model_text.strip()
            keys = [f"{clean_name}_{clean_model}", clean_name, clean_model]
            chip_info = None
            for key in keys:
                if key in APPLE_CHIPS:
                    chip_info = APPLE_CHIPS[key]
                    break
            if not chip_info:
                continue
            name, model, year, proc, cpu_desc, gpu_desc = chip_info
            chip_id = slug(name, model)
            if chip_id in seen:
                continue
            seen.add(chip_id)
            chip: dict[str, Any] = {
                "id": chip_id,
                "name": name,
                "vendor": "Apple",
                "model": model or name,
                "year": year,
            }
            chip.update(parse_process(f"{proc}"))
            chip.update(parse_cpu(cpu_desc))
            chip.update(parse_gpu(gpu_desc))
            if not chip.get("architecture"):
                chip["architecture"] = "ARMv8.6-A"
            chips.append(chip)

    return chips
