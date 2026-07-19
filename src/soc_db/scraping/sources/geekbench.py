"""GeekbenchScraper — BaseScraper implementation for Geekbench Browser.

Geekbench Browser provides CPU single-core, multi-core, and GPU compute
benchmark scores for thousands of processors. The site returns 403 on
basic httpx requests, so this scraper relies on the curl-cffi tier of
HTTPSource for Chrome TLS impersonation bypass.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from soc_db.common import slug
from soc_db.scraping.base import BaseScraper, ChipScrapeResult
from soc_db.scraping.drift import SchemaDriftDetector
from soc_db.scraping.source import HTTPSource

logger = logging.getLogger(__name__)

GB_BASE = "https://browser.geekbench.com"

# Vendor prefixes (subset — Geekbench mainly has Intel, AMD, Apple, Qualcomm)
VENDOR_PREFIXES: dict[str, list[str]] = {
    "Intel": ["intel", "core", "xeon", "pentium", "celeron", "atom"],
    "AMD": ["amd", "ryzen", "epyc", "threadripper", "athlon", "fx-"],
    "Apple": ["apple", "m1", "m2", "m3", "m4"],
    "Qualcomm": ["qualcomm", "snapdragon", "qcs", "sc8"],
    "Samsung": ["samsung", "exynos"],
    "MediaTek": ["mediatek", "dimensity", "helio"],
    "HiSilicon": ["hisilicon", "kirin"],
}


def detect_vendor(name: str) -> str:
    """Detect vendor from processor name using known prefixes."""
    name_lower = name.lower().strip()
    for vendor, prefixes in VENDOR_PREFIXES.items():
        for prefix in prefixes:
            if name_lower.startswith(prefix):
                return vendor
    return "Unknown"


def extract_model(name: str) -> str | None:
    """Extract a model identifier from a processor name."""
    m = re.search(r"[A-Za-z]+[- ]?\d{3,}[A-Za-z0-9]*", name)
    if m:
        return m.group(0)
    return None


def parse_score(text: str) -> int | None:
    """Parse an integer benchmark score from text."""
    text = text.strip()
    if not text or text in ("—", "-", "N/A", ""):
        return None
    cleaned = text.replace(",", "").replace(" ", "")
    try:
        return int(float(cleaned))
    except (ValueError, TypeError):
        return None


class GeekbenchScraper(BaseScraper):
    """Scraper for Geekbench Browser CPU/GPU benchmark scores.

    Searches Geekbench Browser by processor name and extracts single-core,
    multi-core CPU scores and GPU compute scores from the result pages.

    NOTE: Geekbench Browser returns 403 on standard httpx requests. This
    scraper relies on HTTPSource's curl-cffi tier (Chrome TLS impersonation)
    to bypass. If curl-cffi is not installed, the request will escalate to
    Playwright. For best results, install curl-cffi:
        pip install curl-cffi
    """

    SOURCE_ID = "geekbench"
    VENDORS = [
        "Intel", "AMD", "Apple", "Qualcomm", "Samsung",
        "MediaTek", "HiSilicon",
    ]
    PRIORITY = 35

    RATE_LIMIT_CONFIG: dict[str, float | int] = {
        "requests_per_sec": 0.3,
        "burst": 1,
        "backoff_factor": 2.0,
        "max_retries": 3,
        "min_wait": 3.0,
        "max_wait": 60.0,
        "jitter": True,
    }

    def __init__(
        self,
        robots_checker=None,
        rate_limiter=None,
    ) -> None:
        super().__init__(robots_checker, rate_limiter)
        self._http = HTTPSource(rate_limiter=self._rate_limiter, cache_ttl=86400 * 7)
        self._drift = SchemaDriftDetector(threshold=0.7)
        self._drift.register_expected(self.SOURCE_ID, self.expected_fields())

    # ── expected fields ─────────────────────────────────────────────────

    @staticmethod
    def expected_fields() -> set[str]:
        return {
            "id", "name", "vendor", "model",
            "single_core_score", "multi_core_score", "gpu_compute_score",
        }

    # ── fetch ───────────────────────────────────────────────────────────

    def fetch(self) -> str:
        """Fetch the Geekbench Browser search results page.

        Returns:
            Raw HTML string of the search results (JSON-LD embedded).
        """
        # Geekbench Browser shows a listing of recent results at the base URL
        url = f"{GB_BASE}/v6/cpu/search"
        logger.info("[GeekbenchScraper] Fetching %s", url)
        self.check_robots(url)
        html = self._http.fetch(url, user_agent=self.user_agent)
        return html

    # ── parse ───────────────────────────────────────────────────────────

    def parse(self, raw: str) -> list[ChipScrapeResult]:
        """Parse Geekbench Browser HTML into ChipScrapeResults.

        Extracts benchmark data from the search results page. The page may
        contain results as HTML table rows or embedded JSON-LD script tags.

        Args:
            raw: HTML string from fetch().

        Returns:
            List of parsed chip results.
        """
        soup = BeautifulSoup(raw, "html.parser")
        results: list[ChipScrapeResult] = []
        seen_ids: set[str] = set()

        # Strategy 1: Look for JSON-LD script tags (structured data)
        jsonld_results = self._parse_jsonld(soup)
        for chip in jsonld_results:
            chip_id = chip.fields.get("id", "")
            if chip_id and chip_id not in seen_ids:
                seen_ids.add(chip_id)
                results.append(chip)

        # Strategy 2: Parse HTML result rows
        if not results:
            html_results = self._parse_html_table(soup)
            for chip in html_results:
                chip_id = chip.fields.get("id", "")
                if chip_id and chip_id not in seen_ids:
                    seen_ids.add(chip_id)
                    results.append(chip)

        logger.info(
            "[GeekbenchScraper] Parsed %d benchmark result(s)",
            len(results),
        )
        return results

    # ── parsing strategies ──────────────────────────────────────────────

    def _parse_jsonld(self, soup: BeautifulSoup) -> list[ChipScrapeResult]:
        """Extract benchmark results from JSON-LD script tags."""
        results: list[ChipScrapeResult] = []
        scripts = soup.find_all("script", type="application/ld+json")

        for script in scripts:
            try:
                data = json.loads(script.string)
            except (json.JSONDecodeError, TypeError):
                continue

            # Normalize to a flat list of items
            # Handle: array, ItemList with itemListElement, or single item
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                # Check if this is an ItemList wrapper
                item_list = data.get("itemListElement")
                if isinstance(item_list, list):
                    items = item_list
                else:
                    items = [data]
            else:
                continue

            for item in items:
                if not isinstance(item, dict):
                    continue
                chip = self._extract_from_jsonld(item)
                if chip:
                    results.append(chip)

        return results

    def _extract_from_jsonld(self, item: dict[str, Any]) -> ChipScrapeResult | None:
        """Extract a single chip result from a JSON-LD item."""
        # Geekbench JSON-LD typically has "name" with processor name
        # and "description" or custom fields with scores
        name = item.get("name", "").strip()
        if not name:
            return None

        # Filter out non-processor entries
        if not any(kw in name.lower() for kw in ("cpu", "processor", "core", "m1", "m2", "m3", "m4", "ryzen", "intel", "xeon", "snapdragon", "exynos", "dimensity", "apple")):
            return None

        chip: dict[str, Any] = {}
        chip["name"] = name
        chip["vendor"] = detect_vendor(name)
        model = extract_model(name)
        if model:
            chip["model"] = model
        chip["id"] = slug(name, model or "")

        # Extract scores from description or custom fields
        description = item.get("description", "")
        if isinstance(description, str):
            scores = re.findall(r"(\d{3,})", description)
            if len(scores) >= 2:
                chip["single_core_score"] = int(scores[0])
                chip["multi_core_score"] = int(scores[1])
            if len(scores) >= 3:
                chip["gpu_compute_score"] = int(scores[2])

        # Extract scores from additional properties if available
        for key in ("singleCoreScore", "multiCoreScore", "gpuComputeScore", "score"):
            val = item.get(key)
            if val is not None:
                try:
                    val = int(val)
                    if "singleCoreScore" in key or key == "score":
                        chip["single_core_score"] = val
                    elif "multiCoreScore" in key:
                        chip["multi_core_score"] = val
                    elif "gpuComputeScore" in key:
                        chip["gpu_compute_score"] = val
                except (ValueError, TypeError):
                    pass

        return ChipScrapeResult(
            name=chip["name"],
            vendor=chip["vendor"],
            model=chip.get("model"),
            fields=dict(chip),
            source_id=self.SOURCE_ID,
        )

    def _parse_html_table(self, soup: BeautifulSoup) -> list[ChipScrapeResult]:
        """Fallback: extract benchmark results from HTML result rows."""
        results: list[ChipScrapeResult] = []

        # Look for result rows in Geekbench's search/result page structure
        rows = soup.find_all("div", class_=re.compile(r"result|benchmark|row|entry", re.IGNORECASE))
        if not rows:
            # Try table rows as another fallback
            rows = soup.find_all("tr")

        for row in rows:
            chip = self._parse_html_row(row)
            if chip is not None:
                results.append(chip)

        return results

    def _parse_html_row(self, row: Any) -> ChipScrapeResult | None:
        """Parse a single HTML result row into a ChipScrapeResult."""
        text = row.get_text(" ", strip=True)
        if not text:
            return None

        # Look for processor name patterns
        name_link = row.find("a")
        if not name_link:
            return None

        name = name_link.get_text(strip=True)
        if not name:
            return None

        # Skip non-processor entries
        if not any(kw in name.lower() for kw in
                   ("core", "xeon", "ryzen", "epyc", "m1", "m2", "m3", "m4",
                    "snapdragon", "exynos", "dimensity", "apple", "pentium",
                    "celeron", "atom", "threadripper", "athlon")):
            return None

        chip: dict[str, Any] = {}
        chip["name"] = name
        chip["vendor"] = detect_vendor(name)
        model = extract_model(name)
        if model:
            chip["model"] = model
        chip["id"] = slug(name, model or "")

        # Extract scores from cell text
        cells = row.find_all(["td", "span"])
        scores: list[int] = []
        for cell in cells:
            cell_text = cell.get_text(strip=True)
            score = parse_score(cell_text)
            if score is not None and score > 100:
                scores.append(score)

        if len(scores) >= 1:
            chip["single_core_score"] = scores[0]
        if len(scores) >= 2:
            chip["multi_core_score"] = scores[1]
        if len(scores) >= 3:
            chip["gpu_compute_score"] = scores[2]

        if "single_core_score" not in chip and "multi_core_score" not in chip:
            return None

        return ChipScrapeResult(
            name=chip["name"],
            vendor=chip["vendor"],
            model=chip.get("model"),
            fields=dict(chip),
            source_id=self.SOURCE_ID,
        )

    # ── run (lifecycle with drift check) ────────────────────────────────

    def run(self) -> list[ChipScrapeResult]:
        """Execute full scrape lifecycle with drift detection."""
        logger.info("[GeekbenchScraper] Starting scrape")
        raw = self.fetch()
        results = self.parse(raw)
        logger.info("[GeekbenchScraper] Parsed %d result(s)", len(results))

        deduped = self.dedup(results)
        if len(deduped) < len(results):
            logger.info(
                "[GeekbenchScraper] Dedup removed %d duplicate(s)",
                len(results) - len(deduped),
            )

        report = self._drift.check(self.SOURCE_ID, deduped)
        if report.drift_detected:
            logger.warning(
                "[GeekbenchScraper] Drift: %s", report.message
            )

        self.write(deduped)
        logger.info("[GeekbenchScraper] Complete — %d result(s) written", len(deduped))
        return deduped
