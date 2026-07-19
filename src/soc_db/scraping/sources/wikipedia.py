"""WikipediaScraper — BaseScraper implementation for Wikipedia SoC tables.

Reuses the battle-tested parsing logic from the legacy
``soc_db.scraper_wikipedia`` module while leveraging the new framework's
rate limiting, HTTP escalation, and drift detection.
"""

from __future__ import annotations

import logging
from typing import Any

from bs4 import BeautifulSoup

from soc_db.common import write_vendor_file
from soc_db.scraper_wikipedia import (
    WIKI_PAGES,
    _is_transposed_table,
    parse_standard_table,
    parse_transposed_table,
)
from soc_db.scraping.base import BaseScraper, ChipScrapeResult
from soc_db.scraping.drift import SchemaDriftDetector
from soc_db.scraping.source import HTTPSource

logger = logging.getLogger(__name__)

SKIP_SECTIONS = [
    "features of",
    "comparison",
    "acronym",
    "bluetooth",
    "qcc",
    "finances",
    "acquisitions",
    "products",
    "history",
]


class WikipediaScraper(BaseScraper):
    """Scraper for Wikipedia SoC/processor tables.

    Fetches all vendor pages from ``WIKI_PAGES``, parses wiki tables,
    deduplicates results, checks for schema drift, and writes per-vendor
    chip files.
    """

    SOURCE_ID = "wikipedia"
    VENDORS = [
        "Qualcomm", "MediaTek", "Samsung", "HiSilicon", "Google",
        "Apple", "Rockchip", "Allwinner", "Amlogic", "Nvidia",
        "TI OMAP", "Intel Atom", "Ingenic", "NXP i.MX",
    ]
    PRIORITY = 30

    RATE_LIMIT_CONFIG = {
        "requests_per_sec": 1.0,
        "burst": 2,
        "backoff_factor": 2.0,
        "max_retries": 3,
    }

    def __init__(
        self,
        robots_checker=None,
        rate_limiter=None,
    ) -> None:
        super().__init__(robots_checker, rate_limiter)
        self._http = HTTPSource(rate_limiter=self._rate_limiter)
        self._drift = SchemaDriftDetector(threshold=0.8)
        self._drift.register_expected(self.SOURCE_ID, self.expected_fields())
        self._raw_pages: dict[str, str] = {}

    # ── expected fields ─────────────────────────────────────────────────

    @staticmethod
    def expected_fields() -> set[str]:
        return {
            "id", "name", "vendor",
            "cores", "architecture", "gpu", "process_nm", "year",
            "model", "codename", "npu", "memory_type", "memory_clock",
            "memory_bus", "modem", "connectivity_wifi", "connectivity_bluetooth",
            "display_max", "charging", "storage_type",
        }

    # ── fetch ───────────────────────────────────────────────────────────

    def fetch(self) -> dict[str, str]:
        """Fetch all vendor Wikipedia pages.

        Returns:
            Dict mapping vendor names to their HTML content.
        """
        self._raw_pages = {}
        active_vendors = [v for v in self.VENDORS if v in WIKI_PAGES and WIKI_PAGES[v]]

        for vendor in active_vendors:
            url = WIKI_PAGES[vendor]
            if not url:
                continue

            logger.info("[WikipediaScraper] Fetching %s: %s", vendor, url)
            self.check_robots(url)
            html = self._http.fetch(url, user_agent=self.user_agent)
            self._raw_pages[vendor] = html

        return self._raw_pages

    # ── parse ───────────────────────────────────────────────────────────

    def parse(self, raw: dict[str, str]) -> list[ChipScrapeResult]:
        """Parse raw HTML pages into ChipScrapeResults.

        Args:
            raw: Dict mapping vendor names to HTML strings.

        Returns:
            List of parsed chip results.
        """
        results: list[ChipScrapeResult] = []

        for vendor, html in raw.items():
            soup = BeautifulSoup(html, "html.parser")

            tables = soup.find_all("table", class_="wikitable")
            if not tables:
                tables = soup.find_all("table")
                tables = [t for t in tables if t.find("th")]

            seen_ids: set[str] = set()
            is_amlogic = vendor == "Amlogic"

            for tbl in tables:
                prev = tbl.find_previous(["h2", "h3", "h4"])
                heading = prev.get_text(" ", strip=True) if prev else ""
                hl = heading.lower()
                if any(kw in hl for kw in SKIP_SECTIONS):
                    continue

                chip_override = self._get_chip_override(vendor, heading)

                if is_amlogic or _is_transposed_table(tbl):
                    chips = parse_transposed_table(tbl, heading, vendor)
                else:
                    chips = parse_standard_table(tbl, heading, chip_name_override=chip_override or "")

                for chip in chips:
                    chip["vendor"] = vendor
                    if chip["id"] not in seen_ids:
                        seen_ids.add(chip["id"])
                        results.append(
                            ChipScrapeResult(
                                name=chip.get("name", ""),
                                vendor=vendor,
                                model=chip.get("model"),
                                fields=dict(chip),
                                source_id=self.SOURCE_ID,
                            )
                        )

        return results

    # ── run (lifecycle override) ────────────────────────────────────────

    def run(self) -> list[ChipScrapeResult]:
        """Execute the full Wikipedia scrape lifecycle.

        1. Fetch all vendor pages.
        2. Parse pages into ChipScrapeResults.
        3. Deduplicate.
        4. Check schema drift per vendor.
        5. Write results to vendor files.
        """
        logger.info("[WikipediaScraper] Starting scrape — %d vendor(s)", len(self.VENDORS))
        raw_pages = self.fetch()
        results = self.parse(raw_pages)
        logger.info("[WikipediaScraper] Parsed %d chip(s)", len(results))

        deduped = self.dedup(results)
        if len(deduped) < len(results):
            logger.info(
                "[WikipediaScraper] Dedup removed %d duplicate(s)",
                len(results) - len(deduped),
            )

        # Drift check per vendor
        for vendor in raw_pages:
            vendor_results = [r for r in deduped if r.vendor == vendor]
            report = self._drift.check(self.SOURCE_ID, vendor_results)
            if report.drift_detected:
                logger.warning(
                    "[WikipediaScraper] Drift for %s: %s", vendor, report.message
                )

        self.write(deduped)
        logger.info("[WikipediaScraper] Complete — %d chip(s) written", len(deduped))
        return deduped

    # ── write ───────────────────────────────────────────────────────────

    def write(self, results: list[ChipScrapeResult]) -> None:
        """Write results per vendor using the standard write_vendor_file."""
        by_vendor: dict[str, list[dict[str, Any]]] = {}
        for r in results:
            by_vendor.setdefault(r.vendor, []).append(dict(r.fields))
        for vendor, chips in by_vendor.items():
            write_vendor_file(vendor, chips)

    # ── helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _get_chip_override(vendor: str, heading: str) -> str | None:
        """Determine chip name override for vendors with section-based naming."""
        import re

        if vendor == "Nvidia":
            m = re.search(r"(Tegra\s+\d+\w*)", heading, re.IGNORECASE)
            if m:
                return m.group(1)
        elif vendor == "NXP i.MX":
            m = re.search(r"(i\.MX[\s-]*\d[\w]*)", heading, re.IGNORECASE)
            if m:
                return m.group(1).replace("-", " ")
        elif vendor == "Intel Atom":
            m = re.search(r"Atom\s+\w+", heading)
            if m:
                return f"Atom {m.group(0)}"
        return None
