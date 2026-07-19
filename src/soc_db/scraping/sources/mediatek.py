"""MediaTekScraper — BaseScraper implementation for MediaTek Dimensity/Helio chips.

Targets MediaTek official product pages (mediatek.com/products) for
Dimensity, Helio, Kompanio, and Pentonic SoC specifications.

Extracts model number (MT prefix), name, process node, CPU core config,
GPU, APU/NPU, memory support, display, connectivity, modem, and year.

Respects robots.txt and uses per-source rate limiting.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from soc_db.common import extract_int, slug
from soc_db.parsers import (
    parse_cpu,
    parse_gpu,
    parse_memory,
    parse_modem,
    parse_connectivity,
    parse_display,
    parse_process,
)
from soc_db.scraping.base import BaseScraper, ChipScrapeResult
from soc_db.scraping.source import HTTPSource

logger = logging.getLogger(__name__)

# MediaTek product listing pages
MTK_PRODUCT_URLS = [
    "https://www.mediatek.com/products/smartphones/dimensity-5g",
    "https://www.mediatek.com/products/smartphones/helio",
    "https://www.mediatek.com/products/chromebooks/kompanio",
    "https://www.mediatek.com/products/smarttvs/pentonic",
]

# MediaTek model number pattern
MTK_MODEL_RE = re.compile(r"\b(MT\d{4,})\b", re.IGNORECASE)

# MediaTek product line names
MTK_LINE_RE = re.compile(
    r"(Dimensity\s+\d{3,}|Helio\s+\w+\s*\d{3,}|Kompanio\s+\d{3,}|Pentonic\s+\d{3,})",
    re.IGNORECASE,
)


def parse_npu(text: str) -> str | None:
    """Extract NPU/APU information from text."""
    if re.search(r"(APU|NPU|AI\s+Processing\s+Unit|MediaTek\s+NPU)", text, re.IGNORECASE):
        return text.strip()[:80]
    return None


def parse_ai_ops(text: str) -> str | None:
    """Extract AI TOPS value from text."""
    m = re.search(r"(\d+)\s*(TOPS)", text, re.IGNORECASE)
    if m:
        return f"{m.group(1)} TOPS"
    return None


class MediaTekScraper(BaseScraper):
    """Scraper for MediaTek SoC product specifications.

    Fetches MediaTek product listing pages and parses chip specs into
    structured records.
    """

    SOURCE_ID = "mediatek"
    VENDORS = ["MediaTek"]
    PRIORITY = 30

    RATE_LIMIT_CONFIG: dict[str, float | int] = {
        "requests_per_sec": 0.5,
        "burst": 2,
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

    # ── fetch ───────────────────────────────────────────────────────────

    def fetch(self) -> dict[str, str]:
        """Fetch MediaTek product listing pages.

        Returns:
            Dict mapping page URL to its HTML content.
        """
        pages: dict[str, str] = {}
        for url in MTK_PRODUCT_URLS:
            logger.info("[MediaTekScraper] Fetching %s", url)
            self.check_robots(url)
            html = self._http.fetch(url, user_agent=self.user_agent)
            pages[url] = html
        return pages

    # ── parse ───────────────────────────────────────────────────────────

    def parse(self, raw: dict[str, str]) -> list[ChipScrapeResult]:
        """Parse MediaTek product HTML into ChipScrapeResults.

        Args:
            raw: Dict mapping page URLs to their HTML strings.

        Returns:
            List of parsed chip results.
        """
        results: list[ChipScrapeResult] = []
        seen_ids: set[str] = set()

        for url, html in raw.items():
            soup = BeautifulSoup(html, "html.parser")
            chips_on_page = self._parse_page(soup)
            for chip in chips_on_page:
                chip_id = chip.get("id", "")
                if chip_id and chip_id not in seen_ids:
                    seen_ids.add(chip_id)
                    results.append(
                        ChipScrapeResult(
                            name=chip.get("name", ""),
                            vendor="MediaTek",
                            model=chip.get("model"),
                            fields=dict(chip),
                            source_id=self.SOURCE_ID,
                        )
                    )

        logger.info(
            "[MediaTekScraper] Parsed %d chip(s) from %d page(s)",
            len(results),
            len(raw),
        )
        return results

    # ── internal helpers ─────────────────────────────────────────────────

    def _parse_page(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        """Parse a single MediaTek product page for chip data."""
        chips: list[dict[str, Any]] = []

        # Try product cards / chip items
        for article in soup.find_all(
            ["article", "div", "section", "li"],
            class_=re.compile(r"(product|chip|item|card|tile|processor)", re.I),
        ):
            chip = self._parse_article(article)
            if chip:
                chips.append(chip)

        # Try spec tables
        for table in soup.find_all("table"):
            chip = self._parse_spec_table(table)
            if chip:
                chips.append(chip)

        return chips

    def _parse_article(self, article: Any) -> dict[str, Any] | None:
        """Parse a product article element for chip specs."""
        text = article.get_text(" ", strip=True)
        if not text:
            return None

        # Must contain a MediaTek chip line name
        line_match = MTK_LINE_RE.search(text)
        if not line_match:
            return None

        name = line_match.group(1).strip()
        model_match = MTK_MODEL_RE.search(text)
        model = model_match.group(1).upper() if model_match else None

        chip: dict[str, Any] = {
            "name": name,
            "vendor": "MediaTek",
            "model": model or name,
            "id": slug(name, model or ""),
        }

        # Process node
        proc_match = re.search(r"(\d+)\s*nm", text, re.IGNORECASE)
        if proc_match:
            chip["process_nm"] = int(proc_match.group(1))

        # CPU description — look for cluster patterns
        cpu_text = self._extract_near_text(article, r"(CPU|Processor|core)", text)
        if cpu_text:
            chip.update(parse_cpu(cpu_text))
        else:
            cores_match = re.search(r"(\d+)\s*(?:-core|cores?)", text, re.IGNORECASE)
            if cores_match:
                chip["cores"] = int(cores_match.group(1))
            clock_match = re.search(r"up to\s*([\d.]+)\s*GHz", text, re.IGNORECASE)
            if clock_match:
                chip["clock_max"] = int(float(clock_match.group(1)) * 1000)

        # Target ARM architecture
        if "ARMv9" in text:
            chip["architecture"] = "ARMv9-A"
        elif "ARMv8" in text:
            chip["architecture"] = "ARMv8.2-A"
        else:
            chip["architecture"] = "ARMv8.2-A"

        # GPU
        gpu_match = re.search(
            r"(Immortalis-G\d{3}|Mali-G\d{3,}|Mali-G\d{2}|Arm\s+(Immortalis|Mali))",
            text,
            re.IGNORECASE,
        )
        if gpu_match:
            chip["gpu"] = gpu_match.group(0).strip()

        # NPU / APU
        npu_text = self._extract_near_text(article, r"(APU|NPU|AI)", text)
        if npu_text:
            npu = parse_npu(npu_text)
            if npu:
                chip["npu"] = npu
            ai_ops = parse_ai_ops(npu_text)
            if ai_ops:
                chip["ai_ops"] = ai_ops

        # Memory
        mem_match = re.search(r"(LPDDR\d[X]?)", text, re.IGNORECASE)
        if mem_match:
            chip["memory_type"] = mem_match.group(1).upper()
        mem_size_match = re.search(r"(?:up to\s+)?(\d+)\s*GB", text, re.IGNORECASE)
        if mem_size_match:
            chip["memory_max"] = int(mem_size_match.group(1))

        # Display
        disp_match = re.search(r"(4K|8K|WQHD\+?|FHD\+?)", text, re.IGNORECASE)
        if disp_match:
            chip["display_max"] = disp_match.group(0)

        # Connectivity
        wifi_match = re.search(r"(Wi-?Fi\s*\d+|802\.11\w*)", text, re.IGNORECASE)
        if wifi_match:
            chip["wifi"] = wifi_match.group(1)
        bt_match = re.search(r"Bluetooth\s*([\d.]+)", text, re.IGNORECASE)
        if bt_match:
            chip["bluetooth"] = bt_match.group(1)

        # Modem
        modem_match = re.search(r"(5G|LTE|4G|3G)\s*(modem|NR|cellular)", text, re.IGNORECASE)
        if modem_match:
            chip["modem"] = modem_match.group(0).strip()
        dl_match = re.search(r"(?:download|DL)\s*(?:up to\s+)?([\d.]+)\s*Gbps", text, re.IGNORECASE)
        if dl_match:
            chip["modem_dl"] = int(float(dl_match.group(1)) * 1000)

        # Year
        year = self._detect_year(text)
        if year:
            chip["year"] = year

        return chip

    def _parse_spec_table(self, table: Any) -> dict[str, Any] | None:
        """Parse a spec table element for chip data."""
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

            if any(kw in key for kw in ("name", "chip", "model", "product")):
                line_match = MTK_LINE_RE.search(val)
                if line_match:
                    name = line_match.group(1).strip()
                    model_match = MTK_MODEL_RE.search(val)
                    model = model_match.group(1).upper() if model_match else None
                    chip["name"] = name
                    chip["vendor"] = "MediaTek"
                    chip["model"] = model or name
                    chip["id"] = slug(name, model or "")
                    name_found = True

            if not name_found:
                continue

            self._apply_spec_key(chip, key, val)

        if not name_found:
            return None

        if not chip.get("architecture"):
            chip["architecture"] = "ARMv8.2-A"

        return chip

    def _apply_spec_key(self, chip: dict[str, Any], key: str, val: str) -> None:
        """Apply a spec table key-value pair to a chip dict."""
        if "cpu" in key or "core" in key:
            if "cores" not in chip:
                cores_match = re.search(r"(\d+)\s*(?:-core|cores?)", val, re.IGNORECASE)
                if cores_match:
                    chip["cores"] = int(cores_match.group(1))
            if "clock_max" not in chip:
                clock_match = re.search(r"([\d.]+)\s*GHz", val, re.IGNORECASE)
                if clock_match:
                    chip["clock_max"] = int(float(clock_match.group(1)) * 1000)
            # Architecture detection
            if "armv9" in val.lower():
                chip["architecture"] = "ARMv9-A"
            elif "armv8" in val.lower():
                chip["architecture"] = "ARMv8.2-A"

        elif "gpu" in key or "graphics" in key:
            chip.update(parse_gpu(val))

        elif "apu" in key or "npu" in key or "ai" in key:
            npu = parse_npu(val)
            if npu:
                chip["npu"] = npu
            ai_ops = parse_ai_ops(val)
            if ai_ops:
                chip["ai_ops"] = ai_ops

        elif "memory" in key or "ram" in key:
            chip.update(parse_memory(val))

        elif "display" in key or "screen" in key:
            chip.update(parse_display(val))

        elif "process" in key or "node" in key or "fab" in key:
            chip.update(parse_process(val))

        elif "modem" in key or "cellular" in key:
            chip.update(parse_modem(val))

        elif "wifi" in key or "bluetooth" in key:
            chip.update(parse_connectivity(val))

        elif "year" in key or "release" in key or "announced" in key:
            year = extract_int(val)
            if year and 2005 <= year <= 2030:
                chip["year"] = year

    @staticmethod
    def _extract_near_text(article: Any, pattern: str, fallback_text: str) -> str:
        """Extract text from a nearby element matching a pattern."""
        for elem in article.find_all(["div", "p", "span", "section"], class_=re.compile(pattern, re.I)):
            text = elem.get_text(" ", strip=True)
            if text:
                return text
        # Fallback: search for a sibling after heading
        heading = article.find(["h2", "h3", "h4", "h5", "strong"], string=re.compile(pattern, re.I))
        if heading:
            sibling = heading.find_next_sibling(["p", "div", "span"])
            if sibling:
                return sibling.get_text(" ", strip=True)
        return ""

    @staticmethod
    def _detect_year(text: str) -> int | None:
        """Detect a 4-digit year from text."""
        years = re.findall(r"\b(20\d{2})\b", text)
        valid = [int(y) for y in years if 2005 <= int(y) <= 2030]
        return valid[0] if valid else None
