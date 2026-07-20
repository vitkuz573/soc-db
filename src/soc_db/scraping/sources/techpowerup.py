"""TechPowerUpScraper — BaseScraper implementation for TechPowerUp CPU specs.

TechPowerUp CPU Database covers 4398 CPUs with 30+ fields per entry, including
core count, clock speeds, process node, TDP, cache, memory support, and
integrated graphics. The spec listing is static HTML with a searchable table.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from bs4 import BeautifulSoup

from soc_db.common import extract_int, slug
from soc_db.scraping.base import BaseScraper, ChipScrapeResult
from soc_db.scraping.drift import SchemaDriftDetector
from soc_db.scraping.source import HTTPSource

logger = logging.getLogger(__name__)

TPU_CPU_URL = "https://www.techpowerup.com/cpu-specs/"

# Vendor detection from CPU name prefixes
VENDOR_PREFIXES: dict[str, list[str]] = {
    "Intel": ["intel", "core", "xeon", "pentium", "celeron", "atom", "xeon phi"],
    "AMD": ["amd", "ryzen", "epyc", "threadripper", "athlon", "sempron", "a-series", "fx-"],
    "Qualcomm": ["qualcomm", "snapdragon"],
    "Apple": ["apple", "m1", "m2", "m3", "m4", "a14", "a15", "a16", "a17", "a18", "a19"],
    "Samsung": ["samsung", "exynos"],
    "MediaTek": ["mediatek", "dimensity", "helio", "kompanio", "pentonic"],
    "HiSilicon": ["hisilicon", "kirin"],
    "Nvidia": ["nvidia", "tegra"],
    "Rockchip": ["rockchip", "rk"],
    "Allwinner": ["allwinner"],
    "Amlogic": ["amlogic"],
}


def detect_vendor(name: str) -> str:
    """Detect vendor from CPU name string using known prefixes."""
    name_lower = name.lower().strip()
    for vendor, prefixes in VENDOR_PREFIXES.items():
        for prefix in prefixes:
            if name_lower.startswith(prefix):
                return vendor
    return "Unknown"


def extract_model(name: str) -> str | None:
    """Extract a model-like identifier from a CPU name."""
    m = re.search(r"[A-Za-z]+[- ]?\d{3,}[A-Za-z0-9]*", name)
    if m:
        return m.group(0)
    return None


def parse_tdp(text: str) -> int | None:
    """Parse TDP value from text like '65 W' or '15W'."""
    m = re.search(r"(\d+)\s*W", text, re.IGNORECASE)
    return int(m.group(1)) if m else None


def parse_cache_size(text: str) -> str | None:
    """Parse cache size from text like '1 MB (per core)' or '32 MB'."""
    m = re.search(r"(\d+)\s*(MB|KB|GB)", text, re.IGNORECASE)
    if m:
        size = m.group(1)
        unit = m.group(2).upper()
        return f"{size} {unit}"
    return None


def parse_memory_max(text: str) -> str | None:
    """Parse memory max from text like '128 GB' or 'Up to 128 GB'."""
    m = re.search(r"(?:Up to\s+)?(\d+)\s*(GB|TB)", text, re.IGNORECASE)
    if m:
        return f"{m.group(1)} {m.group(2).upper()}"
    return None


def parse_clock(text: str) -> tuple[float | None, float | None]:
    """Parse base clock and boost clock from text like '3.2 GHz / 4.8 GHz'."""
    base, boost = None, None
    nums = re.findall(r"([\d.]+)\s*GHz", text, re.IGNORECASE)
    if nums:
        base = float(nums[0])
        if len(nums) > 1:
            boost = float(nums[1])
    return base, boost


def parse_core_thread(text: str) -> tuple[int | None, int | None]:
    """Parse cores and threads from text like '8 / 16' or '8'."""
    parts = re.findall(r"\d+", text)
    cores = int(parts[0]) if parts else None
    threads = int(parts[1]) if len(parts) > 1 else cores
    return cores, threads


def parse_process_node(text: str) -> int | None:
    """Parse process node from text like '7 nm'."""
    m = re.search(r"(\d+)\s*nm", text, re.IGNORECASE)
    return int(m.group(1)) if m else None


class TechPowerUpScraper(BaseScraper):
    """Scraper for TechPowerUp CPU specs database.

    Fetches the CPU specs listing page and parses the HTML table into
    structured chip records with 16+ fields per chip.
    """

    SOURCE_ID = "techpowerup"
    VENDORS = [
        "Intel", "AMD", "Qualcomm", "Apple", "Samsung", "MediaTek",
        "HiSilicon", "Nvidia", "Rockchip", "Allwinner", "Amlogic",
    ]
    PRIORITY = 20  # High priority — dense spec data

    RATE_LIMIT_CONFIG: dict[str, float | int] = {
        "requests_per_sec": max(1.0, os.cpu_count() or 4 // 4),
        "burst": 3,
        "backoff_factor": 2.0,
        "max_retries": 3,
        "min_wait": 1.0,
        "max_wait": 30.0,
        "jitter": True,
    }

    def __init__(
        self,
        robots_checker=None,
        rate_limiter=None,
    ) -> None:
        super().__init__(robots_checker, rate_limiter)
        self._http = HTTPSource(rate_limiter=self._rate_limiter, cache_ttl=86400)
        self._drift = SchemaDriftDetector(threshold=0.8)
        self._drift.register_expected(self.SOURCE_ID, self.expected_fields())

    # ── expected fields ─────────────────────────────────────────────────

    @staticmethod
    def expected_fields() -> set[str]:
        return {
            "id", "name", "vendor", "model",
            "cores", "threads", "clock", "boost",
            "process_nm", "tdp", "memory_type", "memory_max",
            "l2_cache", "l3_cache", "gpu", "year", "socket",
        }

    # ── fetch ───────────────────────────────────────────────────────────

    def fetch(self) -> str:
        """Fetch ALL pages of TechPowerUp CPU specs (paginated).

        Returns:
            Combined HTML string of all CPU specs pages.
        """
        from bs4 import BeautifulSoup as _Soup

        all_html_parts: list[str] = []
        page = 1
        while True:
            url = f"{TPU_CPU_URL}?page={page}" if page > 1 else TPU_CPU_URL
            logger.info("[TechPowerUpScraper] Fetching page %d: %s", page, url)
            if page == 1:
                self.check_robots(url)
            html = self._http.fetch(url, user_agent=self.user_agent)
            all_html_parts.append(html)
            soup = _Soup(html, "html.parser")
            next_link = soup.find("a", string=re.compile(r"Next|›|»|next"))
            if not next_link or not next_link.get("href"):
                break
            page += 1

        logger.info("[TechPowerUpScraper] Fetched %d page(s)", page)
        return "\n".join(all_html_parts)

    # ── parse ───────────────────────────────────────────────────────────

    def parse(self, raw: str) -> list[ChipScrapeResult]:
        """Parse the TechPowerUp CPU specs HTML into ChipScrapeResults.

        Args:
            raw: HTML string from fetch().

        Returns:
            List of parsed chip results.
        """
        soup = BeautifulSoup(raw, "html.parser")
        results: list[ChipScrapeResult] = []
        seen_ids: set[str] = set()

        # TechPowerUp uses a <table> with class "processors" or similar
        table = soup.find("table")
        if not table:
            logger.warning("[TechPowerUpScraper] No table found in HTML")
            return results

        rows = table.find_all("tr")
        # Skip header row
        data_rows = rows[1:] if rows else []

        for row in data_rows:
            cells = row.find_all("td")
            if len(cells) < 6:
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
            "[TechPowerUpScraper] Parsed %d chip(s) from %d data row(s)",
            len(results),
            len(data_rows),
        )
        return results

    # ── row parsing ─────────────────────────────────────────────────────

    def _parse_row(self, cells: list[Any]) -> dict[str, Any] | None:
        """Parse a single HTML table row into a chip dict."""
        chip: dict[str, Any] = {}
        col_index = 0

        # Column 0: CPU name (anchor text)
        name_link = cells[col_index].find("a")
        if not name_link:
            return None
        name = name_link.get_text(strip=True)
        if not name:
            return None

        chip["name"] = name
        chip["vendor"] = detect_vendor(name)
        model = extract_model(name)
        if model:
            chip["model"] = model
        chip["id"] = slug(name, model or "")
        col_index += 1

        # Column 1: Cores / Threads (e.g., "8 / 16")
        if col_index < len(cells):
            ct_text = cells[col_index].get_text(" ", strip=True)
            cores, threads = parse_core_thread(ct_text)
            if cores is not None:
                chip["cores"] = cores
            if threads is not None:
                chip["threads"] = threads
            col_index += 1

        # Column 2: Clock / Boost (e.g., "3.2 GHz / 4.8 GHz")
        if col_index < len(cells):
            clock_text = cells[col_index].get_text(" ", strip=True)
            base, boost = parse_clock(clock_text)
            if base is not None:
                chip["clock"] = base
            if boost is not None:
                chip["boost"] = boost
            col_index += 1

        # Column 3: Process node (e.g., "7 nm")
        if col_index < len(cells):
            proc_text = cells[col_index].get_text(" ", strip=True)
            proc_nm = parse_process_node(proc_text)
            if proc_nm is not None:
                chip["process_nm"] = proc_nm
            col_index += 1

        # Column 4: TDP (e.g., "65 W")
        if col_index < len(cells):
            tdp_text = cells[col_index].get_text(" ", strip=True)
            tdp = parse_tdp(tdp_text)
            if tdp is not None:
                chip["tdp"] = tdp
            col_index += 1

        # Column 5+: Memory type, memory max, cache, GPU, socket, year
        remaining = cells[col_index:]
        for cell in remaining:
            text = cell.get_text(" ", strip=True)
            if not text or text in ("—", "-", "", "N/A"):
                continue

            # Memory type detection (DDR4, DDR5, LPDDR4, LPDDR5, etc.)
            if re.search(r"(?:LPDDR|DDR)\d", text, re.IGNORECASE) and "memory_type" not in chip:
                mt = re.search(r"((?:LPDDR|DDR)\d[X]?)", text, re.IGNORECASE)
                if mt:
                    chip["memory_type"] = mt.group(1).upper()
                mem_max = parse_memory_max(text)
                if mem_max:
                    chip["memory_max"] = mem_max
                continue

            # Cache (L2 or L3)
            if re.search(r"(L2|L3)", text, re.IGNORECASE) and "l2_cache" not in chip:
                cache_val = parse_cache_size(text)
                if cache_val:
                    if "L2" in text.upper():
                        chip["l2_cache"] = cache_val
                    elif "L3" in text.upper():
                        chip["l3_cache"] = cache_val
                continue

            # GPU detection
            if re.search(r"(Intel|AMD|Radeon|Iris|UHD|Graphics|Adreno|Mali)", text, re.IGNORECASE) and "gpu" not in chip:
                chip["gpu"] = text
                continue

            # Socket detection
            if re.search(r"(LGA|Socket|AM\d|BGA|sTR|SP\d)", text, re.IGNORECASE) and "socket" not in chip:
                chip["socket"] = text
                continue

            # Year detection
            year = extract_int(text)
            if year and 2000 <= year <= 2026 and "year" not in chip:
                chip["year"] = year
                continue

            # Generic cache fallback
            if re.search(r"\d+\s*(MB|KB)", text, re.IGNORECASE):
                cache_val = parse_cache_size(text)
                if cache_val and "l3_cache" not in chip:
                    chip["l3_cache"] = cache_val
                elif cache_val and "l2_cache" not in chip:
                    chip["l2_cache"] = cache_val

        return chip

    # ── run (lifecycle with drift check) ────────────────────────────────

    def run(self) -> list[ChipScrapeResult]:
        """Execute full scrape lifecycle with drift detection."""
        logger.info("[TechPowerUpScraper] Starting scrape")
        raw = self.fetch()
        results = self.parse(raw)
        logger.info("[TechPowerUpScraper] Parsed %d chip(s)", len(results))

        deduped = self.dedup(results)
        if len(deduped) < len(results):
            logger.info(
                "[TechPowerUpScraper] Dedup removed %d duplicate(s)",
                len(results) - len(deduped),
            )

        report = self._drift.check(self.SOURCE_ID, deduped)
        if report.drift_detected:
            logger.warning(
                "[TechPowerUpScraper] Drift: %s", report.message
            )

        self.write(deduped)
        logger.info("[TechPowerUpScraper] Complete — %d chip(s) written", len(deduped))
        return deduped
