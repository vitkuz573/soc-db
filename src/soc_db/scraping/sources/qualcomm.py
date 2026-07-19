"""QualcommScraper — BaseScraper implementation for Qualcomm Snapdragon chips.

Targets Qualcomm Developer Network and product pages for Snapdragon SoC
specifications.  Extracts model number, name, process node, CPU cores/clock,
GPU, NPU, modem, memory, Wi-Fi, Bluetooth, year, display, camera, video,
and charging information.

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
    parse_process,
    parse_camera,
    parse_display,
    parse_video,
    parse_connectivity,
)
from soc_db.scraping.base import BaseScraper, ChipScrapeResult
from soc_db.scraping.source import HTTPSource

logger = logging.getLogger(__name__)

# Qualcomm product listing pages
QDN_LISTINGS = [
    "https://www.qualcomm.com/products/application/smartphones/snapdragon-8-series",
    "https://www.qualcomm.com/products/application/smartphones/snapdragon-7-series",
    "https://www.qualcomm.com/products/application/smartphones/snapdragon-6-series",
    "https://www.qualcomm.com/products/application/smartphones/snapdragon-4-series",
]

# Standard Qualcomm naming patterns for model detection
QUALCOMM_MODEL_RE = re.compile(r"\b(SM\d{4}|SDM\d{3,}|MSM\d{4,}|APQ\d{4,}|SC\d{4}|QCS\d{3,}|QCM\d{3,})\b", re.IGNORECASE)
QUALCOMM_NAME_RE = re.compile(r"Snapdragon\s+\d[\s\w/+]*", re.IGNORECASE)


def parse_charging(text: str) -> str | None:
    """Parse charging / quick charge info from text."""
    m = re.search(r"(Quick\s*Charge\s*[\d+.]+|QC\s*[\d+.]*)", text, re.IGNORECASE)
    if m:
        return m.group(1)
    if re.search(r"charging|fast\s*charge", text, re.IGNORECASE):
        return text.strip()[:60]
    return None


class QualcommScraper(BaseScraper):
    """Scraper for Qualcomm Snapdragon product specifications.

    Fetches Qualcomm product listing pages and parses spec tables into
    structured chip records.
    """

    SOURCE_ID = "qualcomm"
    VENDORS = ["Qualcomm"]
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
        """Fetch Qualcomm product listing pages.

        Returns:
            Dict mapping page URL to its HTML content.
        """
        pages: dict[str, str] = {}
        for url in QDN_LISTINGS:
            logger.info("[QualcommScraper] Fetching %s", url)
            self.check_robots(url)
            html = self._http.fetch(url, user_agent=self.user_agent)
            pages[url] = html
        return pages

    # ── parse ───────────────────────────────────────────────────────────

    def parse(self, raw: dict[str, str]) -> list[ChipScrapeResult]:
        """Parse Qualcomm product HTML into ChipScrapeResults.

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
                            vendor="Qualcomm",
                            model=chip.get("model"),
                            fields=dict(chip),
                            source_id=self.SOURCE_ID,
                        )
                    )

        logger.info(
            "[QualcommScraper] Parsed %d chip(s) from %d page(s)",
            len(results),
            len(raw),
        )
        return results

    # ── internal helpers ─────────────────────────────────────────────────

    def _parse_page(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        """Parse a single Qualcomm product page for chip data.

        Looks for product cards, spec tables, and structured chip data
        in the page HTML.
        """
        chips: list[dict[str, Any]] = []

        # Try finding chip data in structured sections / product cards
        for article in soup.find_all(["article", "div", "section"], class_=re.compile(r"(product|chip|card|tile|item)", re.I)):
            chip = self._parse_article(article)
            if chip:
                chips.append(chip)

        # Try finding chip data in spec tables
        for table in soup.find_all("table"):
            chip = self._parse_spec_table(table)
            if chip:
                chips.append(chip)

        return chips

    def _parse_article(self, article: Any) -> dict[str, Any] | None:
        """Parse a product article/card element for chip specs."""
        text = article.get_text(" ", strip=True)
        if not text:
            return None

        # Must contain a Qualcomm chip name
        name_match = QUALCOMM_NAME_RE.search(text)
        if not name_match:
            return None

        name = name_match.group(0).strip()
        model_match = QUALCOMM_MODEL_RE.search(text)
        model = model_match.group(1).upper() if model_match else None

        chip: dict[str, Any] = {
            "name": name,
            "vendor": "Qualcomm",
            "model": model or name,
            "id": slug(name, model or ""),
        }

        # Process node
        proc_match = re.search(r"(\d+)\s*nm", text, re.IGNORECASE)
        if proc_match:
            chip["process_nm"] = int(proc_match.group(1))

        # CPU description
        cpu_text = self._extract_section_text(article, r"(CPU|Processor|Kryo)", text)
        if cpu_text:
            chip.update(parse_cpu(cpu_text))
        else:
            # Fallback: try to find core count directly
            cores_match = re.search(r"(\d+)[- ]?core", text, re.IGNORECASE)
            if cores_match:
                chip["cores"] = int(cores_match.group(1))
            clock_match = re.search(r"up to\s*([\d.]+)\s*GHz", text, re.IGNORECASE)
            if clock_match:
                chip["clock_max"] = int(float(clock_match.group(1)) * 1000)

        # GPU
        gpu_match = re.search(r"(Adreno\s+\d{3,})", text, re.IGNORECASE)
        if gpu_match:
            chip["gpu"] = gpu_match.group(1)

        # NPU / AI
        npu_match = re.search(r"(Qualcomm\s+)?(AI\s+Engine|Hexagon|NPU|AI\s+accelerator)", text, re.IGNORECASE)
        if npu_match:
            chip["npu"] = npu_match.group(0).strip()
        ai_ops_match = re.search(r"(\d+)\s*(TOPS|trillion operations per second)", text, re.IGNORECASE)
        if ai_ops_match:
            chip["ai_ops"] = f"{ai_ops_match.group(1)} TOPS"

        # Modem
        modem_match = re.search(r"(Snapdragon\s+)?(X\d+\s*(LTE|5G)?|Modem|5G|LTE)", text, re.IGNORECASE)
        if modem_match:
            chip["modem"] = modem_match.group(0).strip()
        dl_match = re.search(r"down\s*([\d.]+)\s*Gbps", text, re.IGNORECASE)
        if dl_match:
            chip["modem_dl"] = int(float(dl_match.group(1)) * 1000)
        ul_match = re.search(r"up\s*([\d.]+)\s*Gbps", text, re.IGNORECASE)
        if ul_match:
            chip["modem_ul"] = int(float(ul_match.group(1)) * 1000)

        # Memory
        mem_match = re.search(r"(LPDDR\d[X]?)", text, re.IGNORECASE)
        if mem_match:
            chip["memory_type"] = mem_match.group(1).upper()
        mem_size_match = re.search(r"(?:up to\s+)?(\d+)\s*GB", text, re.IGNORECASE)
        if mem_size_match:
            chip["memory_max"] = int(mem_size_match.group(1))

        # Wi-Fi
        wifi_match = re.search(r"(Wi-?Fi\s*\d+|802\.11\w*)", text, re.IGNORECASE)
        if wifi_match:
            chip["wifi"] = wifi_match.group(1)

        # Bluetooth
        bt_match = re.search(r"Bluetooth\s*([\d.]+)", text, re.IGNORECASE)
        if bt_match:
            chip["bluetooth"] = bt_match.group(1)

        # Year
        year = self._detect_year(text)
        if year:
            chip["year"] = year

        # Display
        display_match = re.search(r"(4K|8K|WQHD|FHD\+?|DisplayPort)", text, re.IGNORECASE)
        if display_match:
            chip["display_max"] = display_match.group(0)

        # Camera
        cam_match = re.search(r"(\d+)\s*MP", text, re.IGNORECASE)
        if cam_match:
            chip["camera_max"] = cam_match.group(0)

        # Charging
        charging = parse_charging(text)
        if charging:
            chip["charging"] = charging

        # Architecture
        if "ARMv9" in text or "ARMv8" in text:
            chip["architecture"] = "ARMv8.2-A" if "ARMv8" in text else "ARMv9-A"
        elif not chip.get("architecture"):
            chip["architecture"] = "ARMv8.2-A"

        return chip

    def _parse_spec_table(self, table: Any) -> dict[str, Any] | None:
        """Parse a spec table element."""
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

            if "name" in key or "chip" in key or "model" in key:
                name_match = QUALCOMM_NAME_RE.search(val)
                if name_match:
                    name = name_match.group(0).strip()
                    model_match = QUALCOMM_MODEL_RE.search(val)
                    model = model_match.group(1).upper() if model_match else None
                    chip["name"] = name
                    chip["vendor"] = "Qualcomm"
                    chip["model"] = model or name
                    chip["id"] = slug(name, model or "")
                    name_found = True

            if name_found:
                self._apply_spec_key(chip, key, val)

        if not name_found:
            return None

        if not chip.get("architecture"):
            chip["architecture"] = "ARMv8.2-A"

        return chip

    def _apply_spec_key(self, chip: dict[str, Any], key: str, val: str) -> None:
        """Apply a spec table key-value pair to a chip dict."""
        # CPU cores
        if "cpu" in key or "core" in key:
            if "cores" not in chip:
                cores_match = re.search(r"(\d+)\s*(?:-core|cores?)", val, re.IGNORECASE)
                if cores_match:
                    chip["cores"] = int(cores_match.group(1))
            if "clock" not in key and "clock_max" not in chip:
                clock_match = re.search(r"([\d.]+)\s*GHz", val, re.IGNORECASE)
                if clock_match:
                    chip["clock_max"] = int(float(clock_match.group(1)) * 1000)

        # Process node
        if "process" in key or "fab" in key or "node" in key:
            chip.update(parse_process(val))

        # GPU
        if "gpu" in key or "graphics" in key:
            chip.update(parse_gpu(val))

        # Memory
        if "memory" in key or "ram" in key:
            chip.update(parse_memory(val))

        # Modem
        if "modem" in key or "cellular" in key:
            chip.update(parse_modem(val))

        # Connectivity
        if "wifi" in key or "bluetooth" in key or "connectivity" in key:
            chip.update(parse_connectivity(val))

        # Display
        if "display" in key or "screen" in key:
            chip.update(parse_display(val))

        # Camera
        if "camera" in key or "isp" in key:
            chip.update(parse_camera(val))

        # Video
        if "video" in key or "codec" in key:
            chip.update(parse_video(val))

        # Charging
        if "charging" in key or "charge" in key:
            charging = parse_charging(val)
            if charging:
                chip["charging"] = charging

        # Year
        if "year" in key or "release" in key or "announced" in key or "launch" in key:
            year = extract_int(val)
            if year and 2005 <= year <= 2030:
                chip["year"] = year

    @staticmethod
    def _extract_section_text(article: Any, pattern: str, fallback_text: str) -> str:
        """Extract text from a section matching a pattern within an article."""
        for elem in article.find_all(["div", "p", "span", "section"], class_=re.compile(pattern, re.I)):
            text = elem.get_text(" ", strip=True)
            if text:
                return text
        return ""

    @staticmethod
    def _detect_year(text: str) -> int | None:
        """Detect a 4-digit year from text."""
        years = re.findall(r"\b(20\d{2})\b", text)
        valid = [int(y) for y in years if 2005 <= int(y) <= 2030]
        return valid[0] if valid else None
