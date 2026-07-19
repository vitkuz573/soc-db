"""WikidataScraper — BaseScraper implementation for Wikidata SPARQL queries.

Combines the per-vendor SPARQL queries from the legacy scripts/scraper_wikidata.py
and scripts/scraper_wikidata_sparql.py into a single BaseScraper subclass
that queries Wikidata for all known SoC/processor items by manufacturer.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Any

from soc_db.common import slug
from soc_db.scraping.base import BaseScraper, ChipScrapeResult

logger = logging.getLogger(__name__)

# Wikidata type QIDs that cover SoCs
SOC_BASE_TYPES: list[str] = [
    "Q610398",  # system on a chip
    "Q1671695",  # microprocessor
    "Q188509",  # microcontroller
]

# Architecture QID → name mapping
ARCH_MAP: dict[str, str] = {
    "Q28053211": "ARMv9-A",
    "Q116171328": "ARMv9.2-A",
    "Q627843": "ARMv8-A",
    "Q49387": "ARMv8-A",
    "Q189589": "ARMv7-A",
    "Q28053214": "ARMv8.1-A",
    "Q28053216": "ARMv8.2-A",
    "Q28053218": "ARMv8.3-A",
    "Q28053220": "ARMv8.4-A",
    "Q28053222": "ARMv8.5-A",
    "Q28053224": "ARMv8.6-A",
}

# Manufacturer Wikidata QID → our vendor name mapping
KNOWN_MANUFACTURERS: dict[str, str] = {
    "Q43456": "Qualcomm",
    "Q13785": "MediaTek",
    "Q18572479": "Samsung",
    "Q17113619": "HiSilicon",
    "Q104838015": "Google",
    "Q105073008": "Apple",
    "Q13429015": "Rockchip",
    "Q1135421": "Allwinner",
    "Q467610": "Amlogic",
    "Q180664": "Nvidia",
    "Q724382": "TI OMAP",
    "Q248": "Intel Atom",
    "Q6033917": "Ingenic",
    "Q1166585": "NXP i.MX",
    "Q17011490": "Unisoc",
    "Q24949598": "Unisoc",
    "Q1061228": "Realtek",
    "Q585964": "Marvell",
    "Q84423": "Broadcom",
    "Q4677436": "Actions",
    "Q157106": "Renesas",
    "Q220064": "STMicroelectronics",
    "Q2299406": "Microchip",
    "Q128895": "AMD",
    "Q312": "Apple",
    "Q2165106": "Allwinner",
    "Q1046482": "Xilinx",
    "Q4781558": "APM",
    "Q131399365": "Airoha",
    "Q438294": "Altera",
    "Q19599375": "Amazon",
    "Q43177802": "Bitmain",
    "Q5055187": "Cavium",
    "Q2005766": "Nuvoton",
    "Q20983128": "Socionext",
    "Q1571490": "Synaptics",
    "Q478214": "Tesla",
    "Q49125": "Toshiba",
    "Q114358044": "SigmaStar",
    "Q633839": "VIA WonderMedia",
    "Q1067998": "Cirrus Logic",
}

# Per-vendor SPARQL manufacturer info (from scripts/scraper_wikidata_sparql.py)
MANUFACTURERS: dict[str, dict[str, Any]] = {
    "Qualcomm": {"qid": "Q544847", "variant_search": ["Qualcomm Snapdragon"]},
    "MediaTek": {"qid": "Q699848", "variant_search": []},
    "Samsung": {"qid": "Q22822500", "variant_search": ["Samsung Exynos", "Samsung Electronics"], "alt_qids": ["Q20718"]},
    "HiSilicon": {"qid": "Q3135124", "variant_search": []},
    "Apple": {"qid": "Q312", "variant_search": ["Apple Silicon"]},
    "Intel Atom": {"qid": "Q248", "variant_search": []},
    "Rockchip": {"qid": "Q1772192", "variant_search": ["Rockchip (company)"]},
    "Allwinner": {"qid": "Q1775596", "variant_search": []},
    "Amlogic": {"qid": "Q474724", "variant_search": []},
    "Nvidia": {"qid": "Q182477", "variant_search": ["NVIDIA Tegra"]},
    "TI OMAP": {"qid": "Q193412", "variant_search": ["Texas Instruments"]},
    "Ingenic": {"qid": "Q10849149", "variant_search": ["Beijing Ingenic"]},
    "NXP i.MX": {"qid": "Q1155668", "variant_search": ["NXP Semiconductors", "Freescale Semiconductor"]},
    "Unisoc": {"qid": "Q117321369", "variant_search": ["Spreadtrum"]},
    "Broadcom": {"qid": "Q7905541", "variant_search": []},
    "Realtek": {"qid": "Q1061228", "variant_search": []},
    "Marvell": {"qid": "Q1347782", "variant_search": []},
    "Renesas": {"qid": "Q1324134", "variant_search": []},
    "STMicroelectronics": {"qid": "Q208585", "variant_search": []},
    "Microchip": {"qid": "Q1933150", "variant_search": ["Microchip Technology", "Atmel"]},
    "Xilinx": {"qid": "Q635059", "variant_search": []},
}


class WikidataScraper(BaseScraper):
    """Scraper for SoC data from Wikidata SPARQL endpoint.

    Queries Wikidata by manufacturer (P178) using multiple SPARQL queries
    per vendor (P31-filtered + broad) to collect all known SoC items,
    then produces chip records for the enrichment pipeline.
    """

    SOURCE_ID = "wikidata"
    VENDORS = list(MANUFACTURERS.keys())
    PRIORITY = 70

    def __init__(self, robots_checker=None, rate_limiter=None) -> None:
        super().__init__(robots_checker, rate_limiter)
        self._raw_bindings: dict[str, list[dict[str, Any]]] = {}

    # ── fetch ───────────────────────────────────────────────────────────

    def fetch(self) -> dict[str, list[dict[str, Any]]]:
        """Run SPARQL queries for all vendors.

        Returns:
            Dict mapping vendor names to lists of SPARQL binding dicts.
        """
        from soc_db.wikidata import _build_process_query, _build_gpu_query, _build_architecture_query, _cached_sparql  # noqa: PLC0415

        self._raw_bindings = {}

        for vendor_name, manuf_info in MANUFACTURERS.items():
            qid = manuf_info.get("qid", "")
            if not qid:
                continue

            # Collect bindings from multiple queries
            vendor_bindings: list[dict[str, Any]] = []

            # Process node query
            process_query = _build_process_query(qid)
            process_results = _cached_sparql(process_query)
            for b in process_results:
                b["_query_type"] = "process"
                vendor_bindings.append(b)

            # GPU query
            gpu_query = _build_gpu_query(qid)
            gpu_results = _cached_sparql(gpu_query)
            for b in gpu_results:
                b["_query_type"] = "gpu"
                vendor_bindings.append(b)

            # Architecture query
            arch_query = _build_architecture_query(qid)
            arch_results = _cached_sparql(arch_query)
            for b in arch_results:
                b["_query_type"] = "architecture"
                vendor_bindings.append(b)

            self._raw_bindings[vendor_name] = vendor_bindings

        logger.info(
            "[WikidataScraper] Fetched bindings for %d vendor(s)",
            len(self._raw_bindings),
        )
        return self._raw_bindings

    # ── parse ───────────────────────────────────────────────────────────

    def parse(self, raw_bindings: dict[str, list[dict[str, Any]]]) -> list[ChipScrapeResult]:
        """Parse SPARQL bindings into ChipScrapeResults.

        Args:
            raw_bindings: Dict mapping vendor names to SPARQL binding lists.

        Returns:
            List of parsed chip results.
        """
        results: list[ChipScrapeResult] = []
        seen_qids: set[str] = set()

        for vendor_name, bindings in raw_bindings.items():
            for binding in bindings:
                chip = self._parse_binding(binding, vendor_name)
                if not chip:
                    continue

                qid = chip.get("_qid", "")
                if qid:
                    if qid in seen_qids:
                        continue
                    seen_qids.add(qid)

                results.append(
                    ChipScrapeResult(
                        name=chip.get("name", ""),
                        vendor=vendor_name,
                        model=chip.get("model"),
                        fields=dict(chip),
                        source_id=self.SOURCE_ID,
                    )
                )

        logger.info("[WikidataScraper] Parsed %d unique chip(s)", len(results))
        return results

    # ── binding parser ──────────────────────────────────────────────────

    @staticmethod
    def _parse_binding(binding: dict[str, Any], vendor_name: str) -> dict[str, Any] | None:
        """Parse a single SPARQL binding into a chip dict."""
        from soc_db.wikidata import run_sparql, _build_process_query, _cached_sparql  # noqa: PLC0415

        def _extract_value(b: dict[str, Any], key: str) -> str:
            if key not in b:
                return ""
            return b[key].get("value", "")

        name = _extract_value(binding, "itemLabel")
        if not name or name.startswith("Category:") or name.startswith("List of"):
            return None

        skip_keywords = ("series", "family", "processor", "comparison",
                         "architecture", "instruction set", "microarchitecture",
                         "category:", "template:", "wikipedia:")
        if any(kw in name.lower() for kw in skip_keywords):
            return None

        soc_uri = _extract_value(binding, "item")
        wd_qid = soc_uri.split("/")[-1] if soc_uri else ""

        model = _extract_value(binding, "modelNumber")

        chip_id = slug(name, model)
        if not chip_id or chip_id == "unknown":
            chip_id = "wd_" + wd_qid

        chip: dict[str, Any] = {
            "id": chip_id,
            "name": name,
            "vendor": vendor_name,
            "_qid": wd_qid,
        }

        if model:
            chip["model"] = model

        # Cores
        cores_raw = _extract_value(binding, "cores")
        if cores_raw:
            try:
                chip["cores"] = int(float(cores_raw))
            except ValueError:
                pass
        if "cores" not in chip:
            chip["cores"] = 8

        # Architecture
        arch_qid = _extract_value(binding, "arch").split("/")[-1]
        if arch_qid in ARCH_MAP:
            chip["architecture"] = ARCH_MAP[arch_qid]
        else:
            arch_label = _extract_value(binding, "archLabel")
            if arch_label:
                chip["architecture"] = arch_label
        if "architecture" not in chip:
            chip["architecture"] = "ARMv8.2-A"

        # GPU
        gpu = _extract_value(binding, "gpuLabel")
        if gpu:
            chip["gpu"] = gpu

        # Process node (stored as nm integer in Wikidata)
        process_raw = _extract_value(binding, "processNode")
        if process_raw:
            try:
                nm = int(float(process_raw))
                chip["process"] = f"{nm}nm"
            except ValueError:
                pm = re.search(r'(\d+)\s*nm', process_raw, re.IGNORECASE)
                if pm:
                    chip["process"] = pm.group(0)

        # Year
        year_raw = _extract_value(binding, "publicationDate")
        if year_raw:
            try:
                year = int(year_raw[:4])
                if 1980 < year < 2028:
                    chip["year"] = year
            except ValueError:
                pass

        # Max frequency (MHz)
        freq_raw = _extract_value(binding, "maxFreq")
        if freq_raw:
            try:
                freq_val = float(freq_raw)
                if freq_val >= 1000:
                    chip["max_freq"] = f"{freq_val / 1000:.2f} GHz"
                else:
                    chip["max_freq"] = f"{freq_val:.0f} MHz"
            except ValueError:
                pass

        return chip
