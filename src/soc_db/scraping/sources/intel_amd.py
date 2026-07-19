"""IntelAMDScraper — BaseScraper implementation for Intel ARK and AMD specs.

Targets Intel ARK (ark.intel.com) and AMD official product pages for
desktop/server/notebook processor specifications.

Extracts cores, threads, clock, boost, cache, TDP, memory, graphics,
socket, process node, and year.

Shared parsing utilities are provided for both Intel and AMD data.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from soc_db.common import extract_int, slug
from soc_db.scraping.base import BaseScraper, ChipScrapeResult
from soc_db.scraping.source import HTTPSource

logger = logging.getLogger(__name__)

# Intel ARK listing and AMD product pages
INTEL_ARK_URL = "https://ark.intel.com/content/www/us/en/ark.html"
AMD_PRODUCTS_URL = "https://www.amd.com/en/products/specifications"

# Vendor detection from processor name
INTEL_PREFIXES = ["intel", "core", "xeon", "pentium", "celeron", "atom", "xeon phi", "core ultra"]
AMD_PREFIXES = ["amd", "ryzen", "epyc", "threadripper", "athlon", "sempron", "fx-", "a-series"]


# ── Shared parsing utilities ────────────────────────────────────────────────


def detect_vendor(name: str) -> str:
    """Detect vendor (Intel or AMD) from CPU name string.

    Args:
        name: The processor name string.

    Returns:
        ``"Intel"``, ``"AMD"``, or ``"Unknown"``.
    """
    name_lower = name.lower().strip()
    for prefix in INTEL_PREFIXES:
        if name_lower.startswith(prefix):
            return "Intel"
    for prefix in AMD_PREFIXES:
        if name_lower.startswith(prefix):
            return "AMD"
    return "Unknown"


def parse_core_thread(text: str) -> tuple[int | None, int | None]:
    """Parse cores and threads from text like '8 / 16' or '8'.

    Args:
        text: Text containing core/thread counts.

    Returns:
        ``(cores, threads)`` tuple.
    """
    parts = re.findall(r"\d+", text)
    if not parts:
        return None, None
    cores = int(parts[0])
    threads = int(parts[1]) if len(parts) > 1 else cores
    return cores, threads


def parse_clock(text: str) -> tuple[float | None, float | None]:
    """Parse base clock and boost clock from text like '3.4 GHz / 5.4 GHz'.

    Args:
        text: Text containing clock frequencies.

    Returns:
        ``(base_ghz, boost_ghz)`` tuple.
    """
    nums = re.findall(r"([\d.]+)\s*GHz", text, re.IGNORECASE)
    if not nums:
        return None, None
    base = float(nums[0])
    boost = float(nums[1]) if len(nums) > 1 else None
    return base, boost


def parse_tdp(text: str) -> int | None:
    """Parse TDP value from text like '65 W' or '15W'.

    Args:
        text: Text containing power rating.

    Returns:
        TDP in watts, or ``None``.
    """
    m = re.search(r"(\d+)\s*W", text, re.IGNORECASE)
    return int(m.group(1)) if m else None


def parse_cache_size(text: str) -> str | None:
    """Parse cache size from text like '30 MB' or '1 MB (per core)'.

    Args:
        text: Text containing cache information.

    Returns:
        Cache string like '30 MB', or ``None``.
    """
    m = re.search(r"(\d+)\s*(MB|KB|GB)", text, re.IGNORECASE)
    if m:
        return f"{m.group(1)} {m.group(2).upper()}"
    return None


def parse_memory_max(text: str) -> str | None:
    """Parse memory max from text like '128 GB' or 'Up to 128 GB'.

    Args:
        text: Text containing memory capacity.

    Returns:
        Memory maximum string, or ``None``.
    """
    m = re.search(r"(?:Up to\s+)?(\d+)\s*(GB|TB)", text, re.IGNORECASE)
    if m:
        return f"{m.group(1)} {m.group(2).upper()}"
    return None


def parse_process_node(text: str) -> int | None:
    """Parse process node from text like '7 nm' or 'Intel 7'.

    Args:
        text: Text containing process node information.

    Returns:
        Process node in nanometers, or ``None``.
    """
    # Direct nm match
    m = re.search(r"(\d+)\s*nm", text, re.IGNORECASE)
    if m:
        return int(m.group(1))

    # Intel process naming: "Intel 7" → 10nm, "Intel 4" → 7nm, "Intel 3" → 3nm
    m = re.search(r"Intel\s+(\d+)", text, re.IGNORECASE)
    if m:
        val = int(m.group(1))
        mapping = {7: 10, 4: 7, 3: 5, 20: 14, 22: 14}  # Intel 7=10nm, Intel 4=7nm etc
        return mapping.get(val)

    return None


# ── Scraper class ───────────────────────────────────────────────────────────


class IntelAMDScraper(BaseScraper):
    """Scraper for Intel ARK and AMD processor specifications.

    Fetches Intel ARK and AMD product pages and parses spec data into
    structured chip records.
    """

    SOURCE_ID = "intel_amd"
    VENDORS = ["Intel", "AMD"]
    PRIORITY = 30

    RATE_LIMIT_CONFIG: dict[str, float | int] = {
        "requests_per_sec": 1.0,
        "burst": 3,
        "backoff_factor": 2.0,
        "max_retries": 3,
        "min_wait": 0.5,
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

    # ── fetch ───────────────────────────────────────────────────────────

    def fetch(self) -> dict[str, str]:
        """Fetch Intel ARK and AMD product pages.

        Returns:
            Dict mapping source label to HTML content.
        """
        pages: dict[str, str] = {}

        logger.info("[IntelAMDScraper] Fetching Intel ARK...")
        self.check_robots(INTEL_ARK_URL)
        pages["intel"] = self._http.fetch(INTEL_ARK_URL, user_agent=self.user_agent)

        logger.info("[IntelAMDScraper] Fetching AMD products...")
        self.check_robots(AMD_PRODUCTS_URL)
        pages["amd"] = self._http.fetch(AMD_PRODUCTS_URL, user_agent=self.user_agent)

        return pages

    # ── parse ───────────────────────────────────────────────────────────

    def parse(self, raw: dict[str, str]) -> list[ChipScrapeResult]:
        """Parse fetched HTML into ChipScrapeResults.

        Args:
            raw: Dict mapping source labels (``"intel"``, ``"amd"``) to HTML strings.

        Returns:
            List of parsed chip results.
        """
        results: list[ChipScrapeResult] = []
        seen_ids: set[str] = set()

        for source_label, html in raw.items():
            soup = BeautifulSoup(html, "html.parser")
            chips_on_page = self._parse_page(soup, source_label)
            for chip in chips_on_page:
                chip_id = chip.get("id", "")
                if chip_id and chip_id not in seen_ids:
                    seen_ids.add(chip_id)
                    vendor = detect_vendor(chip.get("name", ""))
                    results.append(
                        ChipScrapeResult(
                            name=chip.get("name", ""),
                            vendor=vendor,
                            model=chip.get("model"),
                            fields=dict(chip),
                            source_id=self.SOURCE_ID,
                        )
                    )

        logger.info(
            "[IntelAMDScraper] Parsed %d chip(s) from %d page(s)",
            len(results),
            len(raw),
        )
        return results

    # ── internal helpers ─────────────────────────────────────────────────

    def _parse_page(self, soup: BeautifulSoup, source_label: str) -> list[dict[str, Any]]:
        """Parse a single page for processor chip data."""
        chips: list[dict[str, Any]] = []

        # Try spec tables
        for table in soup.find_all("table"):
            chip = self._parse_spec_table(table, source_label)
            if chip:
                chips.append(chip)

        # Try product cards/lists
        for article in soup.find_all(
            ["article", "div", "section", "li"],
            class_=re.compile(r"(product|processor|chip|card|item)", re.I),
        ):
            chip = self._parse_article(article, source_label)
            if chip:
                chips.append(chip)

        return chips

    def _parse_spec_table(self, table: Any, source_label: str) -> dict[str, Any] | None:
        """Parse a spec table for processor data."""
        rows = table.find_all("tr")
        chip: dict[str, Any] = {}
        name_found = False

        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            key = cells[0].get_text(" ", strip=True).lower()
            val = cells[1].get_text(" ", strip=True)

            if not key or not val or val in ("—", "-", "", "N/A"):
                continue

            if any(kw in key for kw in ("processor", "name", "product", "model")):
                name = val.strip()
                model = self._extract_model(name)
                chip["name"] = name
                chip["vendor"] = detect_vendor(name)
                chip["model"] = model or name
                chip["id"] = slug(name, model or "")
                name_found = True

            if not name_found:
                continue

            self._apply_spec_key(chip, key, val, source_label)

        if not name_found:
            return None

        return chip

    def _parse_article(self, article: Any, source_label: str) -> dict[str, Any] | None:
        """Parse a product article for processor data."""
        text = article.get_text(" ", strip=True)
        if not text:
            return None

        # Find processor name
        name = self._find_processor_name(text)
        if not name:
            return None

        model = self._extract_model(name)
        chip: dict[str, Any] = {
            "name": name,
            "vendor": detect_vendor(name),
            "model": model or name,
            "id": slug(name, model or ""),
        }

        # Cores / threads — handle both "X / Y cores" and "Cores: X / Y" patterns
        ct_match = re.search(
            r"(?:cores?|threads?)\s*:?\s*(\d+)\s*/\s*(\d+)|(\d+)\s*/\s*(\d+)\s*(?:cores?|threads?)",
            text, re.IGNORECASE,
        )
        if ct_match:
            chip["cores"] = int(ct_match.group(1) or ct_match.group(3))
            chip["threads"] = int(ct_match.group(2) or ct_match.group(4))
        elif not ct_match:
            cores_match = re.search(r"(\d+)\s*(?:-core|cores?)", text, re.IGNORECASE)
            if cores_match:
                chip["cores"] = int(cores_match.group(1))

        # Clock frequencies
        base, boost = parse_clock(text)
        if base is not None:
            chip["clock"] = base
        if boost is not None:
            chip["boost"] = boost

        # TDP
        tdp = parse_tdp(text)
        if tdp is not None:
            chip["tdp"] = tdp

        # Process node
        proc_nm = parse_process_node(text)
        if proc_nm is not None:
            chip["process_nm"] = proc_nm

        # Cache
        l2 = re.search(r"L2\s*(?:cache\s+)?(\d+\s*(?:MB|KB))", text, re.IGNORECASE)
        if l2:
            chip["l2_cache"] = l2.group(1)
        l3 = re.search(r"L3\s*(?:cache\s+)?(\d+\s*(?:MB|KB))", text, re.IGNORECASE)
        if l3:
            chip["l3_cache"] = l3.group(1)

        # Memory type
        mem_match = re.search(r"(DDR\d|LPDDR\d)", text, re.IGNORECASE)
        if mem_match:
            chip["memory_type"] = mem_match.group(1).upper()
        mem_max = parse_memory_max(text)
        if mem_max:
            chip["memory_max"] = mem_max

        # Integrated graphics (Intel UHD, Iris, AMD Radeon Graphics)
        gpu_match = re.search(
            r"(Intel\s+(UHD|Iris|Arc)\s+Graphics[\s\w]*|AMD\s+Radeon\s+(Graphics|HD)\s?[\w]*)",
            text,
            re.IGNORECASE,
        )
        if gpu_match:
            chip["gpu"] = gpu_match.group(0).strip()

        # Socket
        socket_match = re.search(r"(LGA\s*\d{3,}|Socket\s+\w+|AM\d|sTR\d|SP\d)", text, re.IGNORECASE)
        if socket_match:
            chip["socket"] = socket_match.group(0).strip()

        # Year
        year = extract_int(text)
        if year and 2000 <= year <= 2026:
            chip["year"] = year

        return chip

    def _apply_spec_key(self, chip: dict[str, Any], key: str, val: str, source_label: str) -> None:
        """Apply a spec table key-value pair."""
        # Cores
        if "core" in key and "thread" not in key:
            c, t = parse_core_thread(val)
            if c is not None and "cores" not in chip:
                chip["cores"] = c
            if t is not None and "threads" not in chip:
                chip["threads"] = t

        # Threads
        if "thread" in key:
            ct, _ = parse_core_thread(val)
            if ct is not None:
                chip["threads"] = ct

        # Clock
        if "clock" in key or "frequency" in key or "speed" in key:
            base, boost = parse_clock(val)
            if base is not None and "clock" not in chip:
                chip["clock"] = base
            if boost is not None and "boost" not in chip:
                chip["boost"] = boost

        # TDP / Power
        if "tdp" in key or "power" in key:
            tdp = parse_tdp(val)
            if tdp is not None:
                chip["tdp"] = tdp

        # Cache
        if "cache" in key:
            if "l2" in key or "level 2" in key:
                cs = parse_cache_size(val)
                if cs:
                    chip["l2_cache"] = cs
            elif "l3" in key or "level 3" in key:
                cs = parse_cache_size(val)
                if cs:
                    chip["l3_cache"] = cs
            elif "l2_cache" not in chip and "l3_cache" not in chip:
                cs = parse_cache_size(val)
                if cs:
                    chip.setdefault("l3_cache", cs)

        # Process / Lithography
        if "process" in key or "lithography" in key:
            proc_nm = parse_process_node(val)
            if proc_nm is not None:
                chip["process_nm"] = proc_nm

        # Memory
        if "memory" in key or "ram" in key:
            mem_match = re.search(r"(DDR\d|LPDDR\d)", val, re.IGNORECASE)
            if mem_match and "memory_type" not in chip:
                chip["memory_type"] = mem_match.group(1).upper()
            mem_max = parse_memory_max(val)
            if mem_max and "memory_max" not in chip:
                chip["memory_max"] = mem_max

        # Graphics
        if "graphics" in key or "gpu" in key:
            if val and val not in ("—", "-", "", "N/A") and "gpu" not in chip:
                chip["gpu"] = val.strip()

        # Socket
        if "socket" in key:
            if val and val not in ("—", "-", "", "N/A") and "socket" not in chip:
                chip["socket"] = val.strip()

        # Year
        if "year" in key or "launch" in key or "introduced" in key:
            year = extract_int(val)
            if year and 2000 <= year <= 2026 and "year" not in chip:
                chip["year"] = year

    @staticmethod
    def _extract_model(name: str) -> str | None:
        """Extract a model identifier from a processor name."""
        # Intel: Core i7-13700K → "Core i7-13700K" (full), or 13700K
        name_clean = name.strip()
        # Try to extract just the model number+SKU suffix
        m = re.search(r"[- ]?\d{3,}[A-Za-z0-9]*$", name_clean)
        if m:
            result = m.group(0).strip().lstrip("- ")
            if result:
                return result
        # Fallback: last word with digits
        words = name_clean.split()
        for word in reversed(words):
            if re.search(r"\d{3,}", word):
                return word.strip()
        return None

    @staticmethod
    def _find_processor_name(text: str) -> str | None:
        """Find a plausible processor name in text."""
        # Intel pattern: "Intel Core i7-13700K", "Intel Core Ultra 9 285K", "Intel Xeon"
        intel_match = re.search(
            r"Intel\s+(Core\s+(?:Ultra\s+\d+\s+)?\w+\s*[-]?\d{3,}|Xeon\s+\w+\s*\d{3,}|Pentium|Celeron|Atom\s+\w+)",
            text,
            re.IGNORECASE,
        )
        if intel_match:
            return intel_match.group(0).strip()

        # AMD pattern: "AMD Ryzen 9 7950X", "AMD EPYC 9654"
        amd_match = re.search(
            r"AMD\s+(Ryzen\s+(?:\w+\s+)?\d{3,}|EPYC\s+\d{3,}|Threadripper|Athlon\s+\w+\s*\d{3,})",
            text,
            re.IGNORECASE,
        )
        if amd_match:
            return amd_match.group(0).strip()

        # Fallback: generic processor pattern
        generic = re.search(r"\b(?:Core|Ryzen)\s+\w+\s*\d{3,}", text, re.IGNORECASE)
        if generic:
            return generic.group(0).strip()

        return None
