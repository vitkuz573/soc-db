"""Merge layer for Wikidata-sourced vendor knowledge.

Provides functions to merge Wikidata SPARQL results with the hardcoded
``VENDOR_KNOWLEDGE`` dict, apply manual overrides from
``data/vendor_overrides.json``, and obtain the final merged knowledge dict.

Usage::

    from soc_db.enrich._vendor_data_wikidata import get_vendor_knowledge

    knowledge = get_vendor_knowledge()
"""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any

from soc_db.config import settings

logger = logging.getLogger(__name__)

# Path to the vendor overrides file (resolved relative to the data/ directory)
_OVERRIDES_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "vendor_overrides.json"
)

# Module-level caches
_overrides_cache: dict[str, Any] | None = None
_VENDOR_KNOWLEDGE_CACHE: dict[str, Any] | None = None


def load_overrides(path: Path | None = None) -> dict[str, Any]:
    """Load manual overrides from ``vendor_overrides.json``.

    Results are cached in the module-level ``_overrides_cache`` after the
    first load.

    Args:
        path: Path to the overrides file. Defaults to ``data/vendor_overrides.json``.

    Returns:
        Parsed dict of overrides, or ``{}`` if the file is missing or invalid.
    """
    global _overrides_cache  # noqa: PLW0603
    if _overrides_cache is not None and path is None:
        return _overrides_cache

    p = path or _OVERRIDES_PATH
    if not p.exists():
        if path is None:
            _overrides_cache = {}
        return {}

    try:
        data = json.loads(p.read_text("utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (json.JSONDecodeError, OSError):
        logger.warning("Failed to parse overrides file at %s", p)
        data = {}

    if path is None:
        _overrides_cache = data
    return data


def merge_vendor_knowledge(wikidata_result: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Merge Wikidata results into a deep copy of VENDOR_KNOWLEDGE.

    Merge rules, in order:

    1. Start with a deep copy of the hardcoded ``VENDOR_KNOWLEDGE``.
    2. For each vendor in *wikidata_result*:
       - If the vendor is **not** in the hardcoded dict: add the entire entry.
       - If the vendor **exists**: merge per-field:
         - ``architecture``: replace with Wikidata value (Wikidata takes
           precedence for known items).
         - ``process_map`` / ``gpu_map``: Wikidata fills in missing models
           but does **not** remove existing models that Wikidata didn't return.
    3. Apply overrides from ``data/vendor_overrides.json``: for each vendor,
       field, and key, set the value unconditionally (manual correction wins
       over everything).

    Args:
        wikidata_result: Dict returned by ``refresh_vendor_knowledge()``.

    Returns:
        The merged VENDOR_KNOWLEDGE dict.
    """
    # Lazy import to avoid circular dependency
    from soc_db.enrich._vendor_data import VENDOR_KNOWLEDGE  # noqa: PLC0415

    merged = deepcopy(dict(VENDOR_KNOWLEDGE))

    for vendor, wd_data in wikidata_result.items():
        wd_process = wd_data.get("process_map", {})
        wd_gpu = wd_data.get("gpu_map", {})
        wd_arch = wd_data.get("architecture")

        if vendor in merged:
            # Merge architecture: Wikidata takes precedence
            if wd_arch:
                merged[vendor]["architecture"] = wd_arch

            # Merge process_map: Wikidata fills gaps
            existing_process = merged[vendor].get("process_map", {})
            for key, val in wd_process.items():
                if key not in existing_process:
                    existing_process[key] = val

            # Merge gpu_map: Wikidata fills gaps
            existing_gpu = merged[vendor].get("gpu_map", {})
            for key, val in wd_gpu.items():
                if key not in existing_gpu:
                    existing_gpu[key] = val
        else:
            # New vendor from Wikidata
            entry: dict[str, Any] = {}
            if wd_arch:
                entry["architecture"] = wd_arch
            if wd_process:
                entry["process_map"] = dict(wd_process)
            if wd_gpu:
                entry["gpu_map"] = dict(wd_gpu)
            merged[vendor] = entry

    # Apply overrides unconditionally
    overrides = load_overrides()
    for vendor, vendor_overrides in overrides.items():
        if vendor not in merged:
            merged[vendor] = {}

        for field in ("architecture", "process_map", "gpu_map"):
            override_val = vendor_overrides.get(field)
            if override_val is not None:
                if field == "architecture":
                    merged[vendor][field] = override_val
                elif isinstance(override_val, dict):
                    merged[vendor].setdefault(field, {})
                    for key, val in override_val.items():
                        merged[vendor][field][key] = val

    return merged


def get_vendor_knowledge() -> dict[str, dict[str, Any]] | None:
    """Get the vendor knowledge dict — optionally merged with Wikidata data.

    Behaviour depends on ``settings.use_wikidata`` (``SOC_DB_USE_WIKIDATA`` env var):

    * ``False`` (default): Returns the hardcoded ``VENDOR_KNOWLEDGE`` directly.
      No network calls, no Wikidata imports.
    * ``True``: Queries Wikidata via ``refresh_vendor_knowledge()``, merges
      results with ``VENDOR_KNOWLEDGE``, applies overrides. Falls back to
      hardcoded data on any error.

    The result is cached at module level after the first successful load.

    Returns:
        The merged VENDOR_KNOWLEDGE dict, or ``None`` if loading entirely fails.
    """
    global _VENDOR_KNOWLEDGE_CACHE  # noqa: PLW0603
    if _VENDOR_KNOWLEDGE_CACHE is not None:
        return _VENDOR_KNOWLEDGE_CACHE

    from soc_db.enrich._vendor_data import VENDOR_KNOWLEDGE  # noqa: PLC0415

    if not settings.use_wikidata:
        _VENDOR_KNOWLEDGE_CACHE = VENDOR_KNOWLEDGE
        return VENDOR_KNOWLEDGE

    # Lazy import — SPARQLWrapper is only loaded when Wikidata mode is active
    try:
        from soc_db.wikidata import refresh_vendor_knowledge  # noqa: PLC0415

        logger.info("Refreshing vendor knowledge from Wikidata...")
        wikidata_result = refresh_vendor_knowledge(dry_run=False)
        merged = merge_vendor_knowledge(wikidata_result)
        _VENDOR_KNOWLEDGE_CACHE = merged
        return merged
    except Exception as exc:
        logger.warning("Wikidata refresh failed, falling back to hardcoded VENDOR_KNOWLEDGE: %s", exc)
        _VENDOR_KNOWLEDGE_CACHE = VENDOR_KNOWLEDGE
        return VENDOR_KNOWLEDGE
