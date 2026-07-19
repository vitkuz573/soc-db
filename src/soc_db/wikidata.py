"""Wikidata SPARQL query module for vendor knowledge.

Provides SPARQL query builders, cached query execution with exponential backoff,
and a ``refresh_vendor_knowledge`` function that returns Wikidata-sourced process node,
GPU, and architecture maps per vendor.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

from SPARQLWrapper import JSON, SPARQLWrapper

from soc_db.common import CACHE_DIR, USER_AGENT, extract_model

logger = logging.getLogger(__name__)

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

# SoC/processor instance-of (P31) classes — same as the legacy scraper in
# scripts/scraper_wikidata_sparql.py.
SOC_CLASSES = [
    "Q122901167",  # system on a chip model
    "Q610398",     # system on a chip
    "Q16521",      # taxon (misused for chips)
    "Q350495",     # class of computer
    "Q3305213",    # electronic component
    "Q34442",      # model
    "Q811701",     # microprocessor model
    "Q431289",     # microprocessor
    "Q181218",     # integrated circuit
    "Q131191",     # microcontroller
    "Q827407",     # multi-chip module
    "Q15625882",   # system-in-package
]

# Wikidata QID mappings for vendors with known identifiers.
# Vendors without a known QID are omitted — they will keep their hardcoded maps.
# Source: scripts/scraper_wikidata_sparql.py MANUFACTURERS dict.
VENDOR_QIDS: dict[str, str] = {
    "Qualcomm": "Q544847",
    "MediaTek": "Q699848",
    "Samsung": "Q22822500",  # Samsung System LSI Division
    "HiSilicon": "Q3135124",
    "Apple": "Q312",
    "Intel Atom": "Q248",  # Intel Corporation
    "Rockchip": "Q1772192",
    "Allwinner": "Q1775596",
    "Amlogic": "Q474724",
    "Nvidia": "Q182477",
    "TI OMAP": "Q193412",
    "Ingenic": "Q10849149",
    "NXP i.MX": "Q1155668",
    "Unisoc": "Q117321369",
    "Broadcom": "Q7905541",
    "Realtek": "Q1061228",
    "Marvell": "Q1347782",
    "Renesas": "Q1324134",
    "STMicroelectronics": "Q208585",
    "Microchip": "Q1933150",
    "Xilinx": "Q635059",
    "Google": "Q95",
    "AMD": "Q68",
}


def _build_process_query(vendor_qid: str) -> str:
    """Build a SPARQL query for process node (P2175) on items manufactured by *vendor_qid*.

    Returns:
        A SPARQL SELECT string returning ``?itemLabel`` and ``?processNode``.
    """
    p31_values = " ".join(f"wd:{c}" for c in SOC_CLASSES)
    return f"""
SELECT DISTINCT ?item ?itemLabel ?processNode WHERE {{
  VALUES ?p31 {{ {p31_values} }}
  ?item wdt:P31 ?p31 .
  ?item wdt:P178 wd:{vendor_qid} .
  ?item wdt:P2175 ?processNode .
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
LIMIT 500
"""


def _build_gpu_query(vendor_qid: str) -> str:
    """Build a SPARQL query for GPU model (P488) on items manufactured by *vendor_qid*.

    Returns:
        A SPARQL SELECT string returning ``?itemLabel``, ``?gpu``, and ``?gpuLabel``.
    """
    p31_values = " ".join(f"wd:{c}" for c in SOC_CLASSES)
    return f"""
SELECT DISTINCT ?item ?itemLabel ?gpu ?gpuLabel WHERE {{
  VALUES ?p31 {{ {p31_values} }}
  ?item wdt:P31 ?p31 .
  ?item wdt:P178 wd:{vendor_qid} .
  ?item wdt:P488 ?gpu .
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
LIMIT 500
"""


def _build_architecture_query(vendor_qid: str) -> str:
    """Build a SPARQL query for instruction set architecture (P10620) on items
    manufactured by *vendor_qid*.

    Returns:
        A SPARQL SELECT string returning ``?itemLabel``, ``?architecture``, and
        ``?architectureLabel``.
    """
    p31_values = " ".join(f"wd:{c}" for c in SOC_CLASSES)
    return f"""
SELECT DISTINCT ?item ?itemLabel ?architecture ?architectureLabel WHERE {{
  VALUES ?p31 {{ {p31_values} }}
  ?item wdt:P31 ?p31 .
  ?item wdt:P178 wd:{vendor_qid} .
  ?item wdt:P10620 ?architecture .
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
LIMIT 500
"""


def run_sparql(
    query: str,
    retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 16.0,
) -> list[dict]:
    """Execute a SPARQL query against Wikidata with exponential backoff.

    Args:
        query: The SPARQL query string.
        retries: Maximum number of retry attempts (default 5).
        base_delay: Initial delay in seconds (default 1.0).
        max_delay: Maximum delay in seconds (default 16.0).

    Returns:
        List of binding dicts, or empty list on persistent failure.
    """
    sparql = SPARQLWrapper(WIKIDATA_SPARQL)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    sparql.addCustomHttpHeader("User-Agent", USER_AGENT)

    for attempt in range(retries):
        try:
            results = sparql.query().convert()
            return results.get("results", {}).get("bindings", [])
        except Exception as e:
            if attempt < retries - 1:
                delay = min(base_delay * (2**attempt), max_delay)
                logger.warning(
                    "SPARQL query failed (attempt %d/%d): %s. Retrying in %.1fs...",
                    attempt + 1,
                    retries,
                    e,
                    delay,
                )
                time.sleep(delay)
            else:
                logger.error("SPARQL query failed after %d attempts: %s", retries, e)

    return []


def _cached_sparql(query: str, ttl: int = 86400) -> list[dict]:
    """Execute a SPARQL query with TTL-based disk caching.

    Args:
        query: The SPARQL query string.
        ttl: Cache TTL in seconds (default 86400 = 24 hours).

    Returns:
        List of binding dicts.
    """
    key = hashlib.md5(query.encode("utf-8"), usedforsecurity=False).hexdigest()
    cache_file = CACHE_DIR / key
    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < ttl:
            try:
                return json.loads(cache_file.read_text("utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
    bindings = run_sparql(query)
    if bindings:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(bindings, indent=2), "utf-8")
        except OSError:
            pass
    return bindings


def _extract_model_key(item_label: str) -> str:
    """Extract a normalised model key from a Wikidata item label.

    Uses :func:`extract_model` from ``common.py`` which knows vendor model patterns
    (e.g. extracts ``sm8550`` from ``"Snapdragon 8 Gen 2 (SM8550)"``).
    Falls back to the lowercased label on failure.
    """
    model = extract_model(item_label)
    if model:
        return model.lower()
    return item_label.lower().strip()


def _int_or_none(value: object) -> int | None:
    """Try to convert a value to int, returning None on failure."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def refresh_vendor_knowledge(dry_run: bool = False) -> dict[str, dict[str, Any]]:
    """Query Wikidata for all vendors in :data:`VENDOR_QIDS` and return structured results.

    Iterates over vendors, runs SPARQL queries for process node (P2175), GPU (P488),
    and instruction set architecture (P10620), and assembles results into a dict
    matching the ``VENDOR_KNOWLEDGE`` structure from ``_vendor_data.py``.

    Results are cached on disk with a 24-hour TTL to avoid redundant network calls.

    Args:
        dry_run: If True, log results via ``logger.info`` per vendor and return {}.
                 If False, return the assembled dict for the merge layer.

    Returns:
        Mapping of vendor name to ``{process_map, gpu_map, architecture}``.
        Returns {} when *dry_run* is True or when no Wikidata data was found.
    """
    # Lazy import to avoid circular dependency at module level
    from soc_db.enrich._vendor_data import VENDOR_FILES  # noqa: PLC0415

    result: dict[str, dict[str, Any]] = {}

    for vendor, qid in VENDOR_QIDS.items():
        if vendor not in VENDOR_FILES:
            logger.debug("Vendor %r not in VENDOR_FILES, skipping", vendor)
            continue

        vendor_data: dict[str, Any] = {}

        # --- Process node (P2175) ---
        process_bindings = _cached_sparql(_build_process_query(qid))
        process_map: dict[str, int] = {}
        for binding in process_bindings:
            item_label = binding.get("itemLabel", {}).get("value", "")
            proc_str = binding.get("processNode", {}).get("value", "")
            if not item_label or not proc_str:
                continue
            key = _extract_model_key(item_label)
            nm = _int_or_none(proc_str)
            if key and nm is not None:
                process_map[key] = nm

        # --- GPU model (P488) ---
        gpu_bindings = _cached_sparql(_build_gpu_query(qid))
        gpu_map: dict[str, str] = {}
        for binding in gpu_bindings:
            item_label = binding.get("itemLabel", {}).get("value", "")
            gpu_label = binding.get("gpuLabel", {}).get("value", "")
            if not item_label or not gpu_label:
                continue
            key = _extract_model_key(item_label)
            if key:
                gpu_map[key] = gpu_label

        # --- Instruction set architecture (P10620) ---
        arch_bindings = _cached_sparql(_build_architecture_query(qid))
        architecture: str | None = None
        for binding in arch_bindings:
            arch_label = binding.get("architectureLabel", {}).get("value", "")
            if arch_label:
                architecture = arch_label
                break  # Take first architecture found at vendor level

        if dry_run:
            logger.info(
                "Wikidata refresh for %s: %d process mappings, %d GPU mappings, arch=%s",
                vendor,
                len(process_map),
                len(gpu_map),
                architecture or "?",
            )
        elif process_map or gpu_map or architecture:
            if process_map:
                vendor_data["process_map"] = process_map
            if gpu_map:
                vendor_data["gpu_map"] = gpu_map
            if architecture:
                vendor_data["architecture"] = architecture
            result[vendor] = vendor_data

    return result
