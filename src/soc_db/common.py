"""Shared utilities for SoC scrapers — re-exports from per-domain enrich modules.

New code should import directly from ``soc_db.enrich``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

# Re-exports from per-domain enrichment modules (used by external callers)
from soc_db.enrich._helpers import _has, clean  # noqa: F401
from soc_db.enrich._vendor_data import (  # noqa: F401
    FIELD_GROUPS,
    FIELD_WEIGHTS,
    MEMORY_CLOCK_FROM_TYPE,
    VENDOR_FILES,
    VENDOR_KNOWLEDGE,
)
from soc_db.enrich.aliases import infer_aliases  # noqa: F401
from soc_db.enrich.connectivity import infer_bluetooth, infer_wifi  # noqa: F401
from soc_db.enrich.cpu import infer_cpu  # noqa: F401
from soc_db.enrich.gpu import infer_gpu  # noqa: F401
from soc_db.enrich.memory import infer_memory  # noqa: F401
from soc_db.enrich.modem import infer_modem  # noqa: F401
from soc_db.enrich.npu import infer_npu  # noqa: F401
from soc_db.enrich.process import infer_process  # noqa: F401
from soc_db.enrich.scoring import compute_completeness  # noqa: F401
from soc_db.enrich.storage import infer_storage  # noqa: F401
from soc_db.enrich.year import infer_year  # noqa: F401
from soc_db.robots import RobotsChecker  # noqa: F401

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
CACHE_DIR = Path(os.environ.get("SOC_DB_CACHE_DIR", tempfile.gettempdir())) / "soc-db-cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
USER_AGENT = "SOC-DB/1.0 (+https://github.com/vitkuz573/soc-db)"

# Per-source scraper identity — each source uses an identifiable User-Agent
# so target sites have a clear contact channel. Default is USER_AGENT.
SCRAPER_USER_AGENTS: dict[str, str] = {
    "wikipedia": "SOC-DB-Wikipedia/1.0 (+https://github.com/vitkuz573/soc-db)",
    "wikidata": "SOC-DB-Wikidata/1.0 (+https://github.com/vitkuz573/soc-db)",
    "apple": "SOC-DB-Apple/1.0 (+https://github.com/vitkuz573/soc-db)",
    "linux_dt": "SOC-DB-DeviceTree/1.0 (+https://github.com/vitkuz573/soc-db)",
    "techpowerup": "SOC-DB-TPU/1.0 (+https://github.com/vitkuz573/soc-db)",
    "notebookcheck": "SOC-DB-NBC/1.0 (+https://github.com/vitkuz573/soc-db)",
    "geekbench": "SOC-DB-GB/1.0 (+https://github.com/vitkuz573/soc-db)",
    "qualcomm": "SOC-DB-Qualcomm/1.0 (+https://github.com/vitkuz573/soc-db)",
    "mediatek": "SOC-DB-MediaTek/1.0 (+https://github.com/vitkuz573/soc-db)",
    "intel": "SOC-DB-Intel/1.0 (+https://github.com/vitkuz573/soc-db)",
    "amd": "SOC-DB-AMD/1.0 (+https://github.com/vitkuz573/soc-db)",
}

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DOCS_DIR = REPO_ROOT / "docs"

# Per-domain robots.txt checker (cached with 24h TTL, fail-open)
_robots_checker = RobotsChecker()


def guard_path(path: Path) -> None:
    """Reject writes to the docs/ directory (GitHub Pages integrity).

    Called before every file write in the data pipeline. Raises
    PermissionError if the resolved path falls under DOCS_DIR.

    Args:
        path: The destination file path to check.

    Raises:
        PermissionError: If path resolves inside DOCS_DIR.
    """
    resolved = Path(path).resolve()
    docs_resolved = DOCS_DIR.resolve()
    if docs_resolved in resolved.parents or resolved == docs_resolved:
        raise PermissionError(
            f"CRITICAL: Write to docs/ blocked — GitHub Pages integrity. "
            f"Path: {resolved}"
        )


def fetch(url: str, ttl: int = 86400, user_agent: str | None = None) -> str:
    """Fetch a URL with caching.

    Retrieves the content at the given URL. Results are cached on disk
    under CACHE_DIR keyed by MD5 hash of the URL. Subsequent calls within
    the TTL window return the cached response.

    Args:
        url: The URL to fetch.
        ttl: Time-to-live in seconds for the cache (default 86400).
        user_agent: Optional per-source User-Agent. Falls back to USER_AGENT.

    Returns:
        The response body as a UTF-8 decoded string.
    """
    key = hashlib.md5(url.encode(), usedforsecurity=False).hexdigest()
    cache_file = CACHE_DIR / key
    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < ttl:
            return cache_file.read_text("utf-8")
    # Robots.txt compliance check (only before network fetch)
    ua = user_agent or USER_AGENT
    if not _robots_checker.can_fetch(url, ua):
        raise PermissionError(
            f"robots.txt disallows fetching {url} for User-Agent: {ua}"
        )
    req = Request(url, headers={"User-Agent": ua})
    with urlopen(req, timeout=30) as resp:  # nosec - controlled URLs only
        data: str = resp.read().decode("utf-8")
    guard_path(cache_file)
    cache_file.write_text(data, "utf-8")
    time.sleep(1)
    return data


def extract_int(text: str) -> int | None:
    """Extract the first integer from a string.

    Args:
        text: The input string to search.

    Returns:
        The first integer found, or None if no digits are present.
    """
    if not isinstance(text, str):
        return None
    m = re.search(r"\d+", text)
    return int(m.group()) if m else None


def extract_freq(text: str) -> str | None:
    """Extract a clock frequency (MHz/GHz) from a string.

    Args:
        text: The input string to search.

    Returns:
        The matched frequency string (e.g. "3.2 GHz"), or None.
    """
    m = re.search(r"[\d.]+[\s]*(?:MHz|GHz)", text, re.IGNORECASE)
    if m:
        return m.group().strip()
    return None


def extract_process(text: str) -> str | None:
    """Extract a process node (e.g. "7 nm") from a string.

    Args:
        text: The input string to search.

    Returns:
        The matched process string (e.g. "7 nm"), or None.
    """
    m = re.search(r"(\d+)\s*nm", text, re.IGNORECASE)
    return m.group(0) if m else None


def slug(name: str, model: str = "") -> str:
    """Generate a URL/filesystem-friendly identifier from a chip name and model.

    Lowercases the name, removes special characters, filters common
    stop-words, joins up to six parts with underscores, and optionally
    appends a sanitised model string.

    Args:
        name: The chip name (e.g. "Snapdragon 8 Gen 2").
        model: An optional model number (e.g. "SM8550").

    Returns:
        A slug string suitable for use as a unique ID.
    """
    s = name.lower().replace("+", "p").replace("®", "").replace("-", "_")
    s = re.sub(r"[^a-z0-9_ ]", "", s)
    parts = [p for p in s.split() if p]
    skip = {"with", "and", "the", "for", "integrated", "support", "using", "based", "cores", "ghz", "mhz", "kryo", "cortex"}
    parts = [p for p in parts if p not in skip]
    base = "_".join(parts[:6]) if parts else "chip"
    if model:
        m = re.sub(r"[^a-z0-9]", "", model.lower()).strip()
        if m and m not in base:
            base = f"{base}_{m}"
    base = re.sub(r"_+", "_", base).strip("_")
    return base or "unknown"


def _match_existing(chip: dict[str, Any], existing: dict[str, Any]) -> str | None:
    """Match a chip dict against a dict of already-known chips.

    Tries matching by ``id``, then by ``model`` (case-insensitive),
    then by ``name`` (case-insensitive).

    Args:
        chip: The new chip record.
        existing: Mapping of existing chip IDs to their records.

    Returns:
        The matching ID from *existing*, or None if no match found.
    """
    cid: str = chip.get("id", "")
    if cid in existing:
        return cid
    model: str = chip.get("model", "").strip().upper()
    if model:
        for eid, ec in existing.items():
            ec_model: str = ec.get("model", "").strip().upper()
            if ec_model == model:
                return eid
    name: str = chip.get("name", "").lower().strip()
    if name:
        for eid, ec in existing.items():
            ec_name: str = ec.get("name", "").lower().strip()
            if ec_name == name:
                return eid
    return None


def write_vendor_file(vendor: str, chips: list[dict[str, Any]]) -> None:
    """Merge a list of scraped chips into the vendor's JSON file on disk.

    Loads the existing vendor file (if any), matches new chips against
    existing entries by ID/model/name, updates or adds records, prunes
    stale entries with low completeness, and writes the merged result
    back through :func:`enrich_all`.

    Args:
        vendor: Vendor name (must be a key in VENDOR_FILES).
        chips: List of chip dicts produced by a scraper.
    """
    vfile = VENDOR_FILES.get(vendor)
    if not vfile:
        logger.warning("Unknown vendor: %s", vendor)
        return
    fpath = DATA_DIR / vfile
    existing = {}
    if fpath.exists():
        try:
            for c in json.loads(fpath.read_text("utf-8")):
                existing[c["id"]] = c
        except json.JSONDecodeError:
            pass
    matched_ids = set()
    added = updated = removed = 0
    for chip in chips:
        match_id = _match_existing(chip, existing)
        if match_id:
            matched_ids.add(match_id)
            old = existing[match_id]
            for k in ("name", "model"):
                if chip.get(k) and chip[k] != old.get(k):
                    old[k] = chip[k]
            new_id = slug(old.get("name", ""), old.get("model", ""))
            if new_id != match_id and new_id not in existing:
                old["id"] = new_id
                existing[new_id] = old
                del existing[match_id]
                matched_ids.remove(match_id)
                matched_ids.add(new_id)
                match_id = new_id
            for k, v in chip.items():
                if k in ("name", "model"):
                    continue
                if (k not in old or old[k] in (None, "", [], 0, 0.0)) and v not in (None, "", [], 0, 0.0):
                    old[k] = v
            updated += 1
        else:
            cid = chip["id"]
            existing[cid] = dict(chip)
            matched_ids.add(cid)
            added += 1
    stale = set()
    for eid, ec in existing.items():
        if eid not in matched_ids and (ec.get("completeness", 1) < 0.28 or ec.get("name", "").lower().startswith(("mali ", "adreno ", "powervr "))):
            stale.add(eid)
    matched_models: dict[str, list[str]] = defaultdict(list)
    for eid in matched_ids:
        ec = existing.get(eid, {})
        m = ec.get("model", "").strip().upper()
        if m:
            matched_models[m].append(ec.get("name", "").lower())
    for eid in list(existing.keys()):
        if eid not in matched_ids:
            ec = existing[eid]
            m = ec.get("model", "").strip().upper()
            if m and m in matched_models:
                ename = ec.get("name", "").lower()
                for mname in matched_models[m]:
                    if ename and (ename in mname or mname in ename or any(w in ename and w in mname for w in ename.split() if len(w) > 2)):
                        stale.add(eid)
                        break
    for eid in stale:
        del existing[eid]
        removed += 1
    output = sorted(existing.values(), key=lambda x: (x.get("year", 9999), x["name"]))
    output = enrich_all(output)
    guard_path(fpath)
    fpath.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", "utf-8")
    logger.info("%s: %d entries (%d new, %d updated, %d pruned)", vfile, len(output), added, updated, removed)


def extract_model(text: str) -> str | None:
    """Extract a SoC model identifier from arbitrary text.

    Matches against known vendor patterns such as Qualcomm SM/SDM/MSM,
    MediaTek MT, Samsung Exynos, HiSilicon Kirin, Google GS, Rockchip RK,
    TI OMAP, Amlogic AM/DM, and Apple APL/T-prefix identifiers.

    Args:
        text: The input string to search.

    Returns:
        The uppercased model string (e.g. "SM8550"), or None.
    """
    patterns = [
        r"\b(SM\d{3,}|SDM\d{3,}|MSM\d{3,}|APQ\d{3,}|SC\d{4}|QCS\d{3})\b",
        r"\b(MT\d{4,})\b",
        r"\b(Exynos\s*\d{4,})\b",
        r"\b(Kirin\s*\d{3,})\b",
        r"\b(GS\d{3})\b",
        r"\b(RK\d{3,})\b",
        r"\b(OMAP\d{4,})\b",
        r"\b(AM\d{3,}|DM\d{3,})\b",
        r"\b(APL\w+|T\d{4})\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).upper()
    return None


def merge_chips(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Merge two chip dicts, preferring non-empty values from *b*.

    Fields in *b* whose values are ``None``, ``""``, ``0``, or ``[]``
    are skipped, preserving the value from *a*.

    Args:
        a: The base chip dict.
        b: The chip dict whose values take precedence.

    Returns:
        A new merged dict.
    """
    merged = dict(a)
    for k, v in b.items():
        if v not in (None, "", 0, []):
            merged[k] = v
    return merged


def enrich_one(chip: dict[str, Any]) -> dict[str, Any]:
    """Enrich a single chip record by filling in missing fields with
    inferred defaults.

    The enrichment pipeline applies the following stages in order:

    1. **Cleanup** – strip ``(now ...)`` suffixes from name/model.
    2. **Model fallback** – if no model, derive from name or use ``id``.
    3. **Memory** – infer clock speed and bus width from memory type.
    4. **Process node** – look up ``VENDOR_KNOWLEDGE`` process map, then
       fall back to a year-based heuristic.
    5. **GPU** – look up ``VENDOR_KNOWLEDGE`` gpu map, then vendor defaults.
    6. **Year** – attempt to parse the year from model/name via extensive
       vendor-specific regex patterns; validate range.
    7. **Wi-Fi / Bluetooth** – infer from year.
    8. **Modem / NPU** – infer from vendor and year.
    9. **Storage type** – infer from year.
    10. **Aliases** – generate known codename aliases.
    11. **Completeness score** – weighted fill ratio of ``FIELD_GROUPS``.
    12. **Sources / updated** – ensure provenance metadata.

    Args:
        chip: The raw chip record to enrich (modified in place).

    Returns:
        The enriched chip dict (same object as the input).
    """
    ann = re.compile(r"\s*\(now\s+[^)]*?\)")
    for k in ("name", "model"):
        if chip.get(k):
            cleaned = ann.sub("", chip[k]).strip()
            if cleaned != chip[k]:
                chip[k] = cleaned
    if not chip.get("model"):
        name = chip.get("name", "")
        if re.match(r"^[A-Za-z0-9][A-Za-z0-9/\-.\s]{1,30}$", name) and re.search(r"\d", name):
            chip["model"] = name
        else:
            chip["model"] = chip.get("id", "unknown")
    infer_cpu(chip)
    infer_memory(chip)  # first pass: clock/bus from type
    infer_process(chip)  # first pass: model-based lookup
    infer_gpu(chip)  # first pass: model-based lookup
    y_chk = chip.get("year")
    if y_chk and (y_chk < 2003 or y_chk > 2026):
        chip["year"] = None
    year = chip.get("year")
    if not year:
        inferred = infer_year(chip)
        if inferred:
            chip["year"] = inferred
            year = inferred
    infer_process(chip)  # second pass: year-based fallback
    infer_memory(chip)  # second pass: type/clock/bus from year
    infer_gpu(chip)  # second pass: vendor defaults from year
    infer_storage(chip)
    infer_npu(chip)
    infer_modem(chip)
    infer_wifi(chip)
    infer_bluetooth(chip)
    infer_aliases(chip)
    compute_completeness(chip)
    return chip


def enrich_all(chips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply :func:`enrich_one` to every chip in a list.

    Args:
        chips: List of chip records to enrich.

    Returns:
        The enriched list (same objects in-place).
    """
    return [enrich_one(c) for c in chips]
