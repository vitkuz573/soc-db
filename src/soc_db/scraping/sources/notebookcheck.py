"""NotebookCheckScraper — BaseScraper implementation for NotebookCheck benchmarks.

NotebookCheck provides 20+ benchmark scores per chip including Cinebench R23,
Geekbench 6, x265, Blender, 7-Zip, and AI NPU TOPS. The benchmark database
is a static HTML table with per-processor rows.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from soc_db.common import extract_int, slug
from soc_db.scraping.base import BaseScraper, ChipScrapeResult
from soc_db.scraping.drift import SchemaDriftDetector
from soc_db.scraping.source import HTTPSource

logger = logging.getLogger(__name__)

NBC_URL = "https://www.notebookcheck.net/Mobile-Processors-Benchmark-List.2436.0.html"

# Column name patterns for benchmark matching
BENCHMARK_COLUMNS: dict[str, re.Pattern] = {
    "cinebench_r23_mt": re.compile(r"cinebench.*r23.*multi", re.IGNORECASE),
    "cinebench_r23_st": re.compile(r"cinebench.*r23.*single", re.IGNORECASE),
    "geekbench_6_mt": re.compile(r"geekbench.*6.*multi", re.IGNORECASE),
    "geekbench_6_st": re.compile(r"geekbench.*6.*single", re.IGNORECASE),
    "geekbench_5_mt": re.compile(r"geekbench.*5.*multi", re.IGNORECASE),
    "geekbench_5_st": re.compile(r"geekbench.*5.*single", re.IGNORECASE),
    "x265": re.compile(r"x265", re.IGNORECASE),
    "blender": re.compile(r"blender", re.IGNORECASE),
    "7zip": re.compile(r"7.?zip", re.IGNORECASE),
    "ai_tops_npu": re.compile(r"ai.*(?:tops|npu|performance)", re.IGNORECASE),
}

# Vendor detection for NotebookCheck (same as TechPowerUp but NotebookCheck
# also lists "Intel" / "AMD" explicitly in processor names)
VENDOR_PREFIXES: dict[str, list[str]] = {
    "Intel": ["intel", "core", "xeon", "pentium", "celeron", "atom"],
    "AMD": ["amd", "ryzen", "epyc", "threadripper", "athlon", "sempron"],
    "Qualcomm": ["qualcomm", "snapdragon", "qcs", "sc8"],
    "Apple": ["apple", "m1", "m2", "m3", "m4"],
    "Samsung": ["samsung", "exynos"],
    "MediaTek": ["mediatek", "dimensity", "helio", "kompanio"],
    "HiSilicon": ["hisilicon", "kirin"],
    "Nvidia": ["nvidia", "tegra"],
    "Rockchip": ["rockchip", "rk"],
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
    """Extract a model identifier from a CPU name (e.g. 'Core i7-13700H' → 'i7-13700H')."""
    m = re.search(r"[A-Za-z]+[- ]?\d{3,}[A-Za-z0-9]*", name)
    if m:
        return m.group(0)
    return None


def parse_benchmark_value(text: str) -> int | float | None:
    """Parse a benchmark score from cell text, returning int or float.

    Handles commas as thousand separators and 'N/A' / '-' / '' entries.
    """
    text = text.strip()
    if not text or text in ("—", "-", "N/A", "n/a", ""):
        return None
    # Remove thousand separators
    cleaned = text.replace(",", "").replace(" ", "")
    try:
        if "." in cleaned:
            return float(cleaned)
        return int(cleaned)
    except (ValueError, TypeError):
        return None


class NotebookCheckScraper(BaseScraper):
    """Scraper for NotebookCheck mobile processor benchmark database.

    Fetches the benchmark list page and parses the HTML table, extracting
    benchmark scores and basic spec data per processor.
    """

    SOURCE_ID = "notebookcheck"
    VENDORS = [
        "Intel", "AMD", "Qualcomm", "Apple", "Samsung", "MediaTek",
        "HiSilicon", "Nvidia", "Rockchip",
    ]
    PRIORITY = 25

    RATE_LIMIT_CONFIG: dict[str, float | int] = {
        "requests_per_sec": 0.5,
        "burst": 2,
        "backoff_factor": 2.0,
        "max_retries": 3,
        "min_wait": 2.0,
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
        self._column_map: dict[int, str] = {}

    # ── expected fields ─────────────────────────────────────────────────

    @staticmethod
    def expected_fields() -> set[str]:
        return {
            "id", "name", "vendor", "model",
            "cores", "clock",
            "cinebench_r23_mt", "cinebench_r23_st",
            "geekbench_6_mt", "geekbench_6_st",
            "geekbench_5_mt", "geekbench_5_st",
            "x265", "blender", "7zip",
            "ai_tops_npu", "tdp",
        }

    # ── fetch ───────────────────────────────────────────────────────────

    def fetch(self) -> str:
        """Fetch the NotebookCheck mobile processor benchmark list.

        Returns:
            Raw HTML string of the benchmark list page.
        """
        logger.info("[NotebookCheckScraper] Fetching %s", NBC_URL)
        self.check_robots(NBC_URL)
        html = self._http.fetch(NBC_URL, user_agent=self.user_agent)
        return html

    # ── parse ───────────────────────────────────────────────────────────

    def parse(self, raw: str) -> list[ChipScrapeResult]:
        """Parse the NotebookCheck benchmark HTML into ChipScrapeResults.

        Args:
            raw: HTML string from fetch().

        Returns:
            List of parsed chip results.
        """
        soup = BeautifulSoup(raw, "html.parser")
        results: list[ChipScrapeResult] = []
        seen_ids: set[str] = set()

        # Find the benchmark table — usually the main <table> on the page
        # NotebookCheck uses <table class="..."> with processor rows
        tables = soup.find_all("table")
        target_table: Any = None

        for tbl in tables:
            # Look for a table that has processor-like headers
            header_text = tbl.get_text(" ", strip=True)[:200].lower()
            if "processor" in header_text or "cinebench" in header_text:
                target_table = tbl
                break

        if target_table is None and tables:
            # Fallback: use the largest table
            target_table = max(tables, key=lambda t: len(t.find_all("tr")))

        if target_table is None:
            logger.warning("[NotebookCheckScraper] No benchmark table found")
            return results

        # Build column map from header row
        rows = target_table.find_all("tr")
        if not rows:
            return results

        header_cells = rows[0].find_all(["th", "td"])
        self._column_map = self._build_column_map(header_cells)

        # Parse data rows
        data_rows = rows[1:] if len(rows) > 1 else []
        for row in data_rows:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue

            chip = self._parse_row(cells)
            if chip is None:
                continue

            chip_id = chip.get("id", "")
            if chip_id and chip_id not in seen_ids:
                seen_ids.add(chip_id)
                results.append(
                    ChipScrapeResult(
                        name=chip.get("name", ""),
                        vendor=chip.get("vendor", "Unknown"),
                        model=chip.get("model"),
                        fields=dict(chip),
                        source_id=self.SOURCE_ID,
                    )
                )

        logger.info(
            "[NotebookCheckScraper] Parsed %d chip(s) from %d data row(s)",
            len(results),
            len(data_rows),
        )
        return results

    # ── row parsing ─────────────────────────────────────────────────────

    def _build_column_map(self, header_cells: list[Any]) -> dict[int, str]:
        """Map column indices to benchmark field names based on header text."""
        col_map: dict[int, str] = {}
        for idx, cell in enumerate(header_cells):
            text = cell.get_text(" ", strip=True)
            if not text:
                continue

            # Check against known benchmark patterns
            for field, pattern in BENCHMARK_COLUMNS.items():
                if pattern.search(text):
                    col_map[idx] = field
                    break

            # Basic spec columns
            text_lower = text.lower()
            if "processor" in text_lower or "name" in text_lower or "model" in text_lower:
                col_map[idx] = "name"
            elif "core" in text_lower and "thread" not in text_lower and "clock" not in text_lower:
                col_map[idx] = "cores"
            elif "clock" in text_lower or "speed" in text_lower:
                col_map[idx] = "clock"
            elif "tdp" in text_lower or "power" in text_lower:
                col_map[idx] = "tdp"

        return col_map

    def _parse_row(self, cells: list[Any]) -> dict[str, Any] | None:
        """Parse a single HTML table row into a chip dict."""
        chip: dict[str, Any] = {}
        name_found = False

        for idx, cell in enumerate(cells):
            field = self._column_map.get(idx)
            if field is None:
                continue

            text = cell.get_text(" ", strip=True)

            if field == "name":
                # Extract processor name from cell (possibly with link)
                link = cell.find("a")
                if link:
                    text = link.get_text(strip=True) or text
                if not text:
                    continue
                chip["name"] = text
                chip["vendor"] = detect_vendor(text)
                model = extract_model(text)
                if model:
                    chip["model"] = model
                chip["id"] = slug(text, model or "")
                name_found = True

            elif field in ("cores",):
                val = extract_int(text)
                if val is not None:
                    chip[field] = val

            elif field in ("clock",):
                m = re.search(r"([\d.]+)\s*(?:GHz|MHz)", text, re.IGNORECASE)
                if m:
                    clock_val = float(m.group(1))
                    if "MHz" in text.upper():
                        clock_val /= 1000.0  # Convert MHz to GHz
                    chip["clock"] = round(clock_val, 2)

            elif field in ("tdp",):
                val = parse_benchmark_value(text)
                if val is not None and isinstance(val, (int, float)):
                    chip["tdp"] = int(val)

            elif field in BENCHMARK_COLUMNS:
                val = parse_benchmark_value(text)
                if val is not None:
                    chip[field] = val

        if not name_found:
            return None

        return chip

    # ── run (lifecycle with drift check) ────────────────────────────────

    def run(self) -> list[ChipScrapeResult]:
        """Execute full scrape lifecycle with drift detection."""
        logger.info("[NotebookCheckScraper] Starting scrape")
        raw = self.fetch()
        results = self.parse(raw)
        logger.info("[NotebookCheckScraper] Parsed %d chip(s)", len(results))

        deduped = self.dedup(results)
        if len(deduped) < len(results):
            logger.info(
                "[NotebookCheckScraper] Dedup removed %d duplicate(s)",
                len(results) - len(deduped),
            )

        report = self._drift.check(self.SOURCE_ID, deduped)
        if report.drift_detected:
            logger.warning(
                "[NotebookCheckScraper] Drift: %s", report.message
            )

        self.write(deduped)
        logger.info("[NotebookCheckScraper] Complete — %d chip(s) written", len(deduped))
        return deduped
