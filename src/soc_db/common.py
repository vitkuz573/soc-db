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

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
CACHE_DIR = Path(os.environ.get("SOC_DB_CACHE_DIR", tempfile.gettempdir())) / "soc-db-cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
USER_AGENT = "SOC-DB/1.0 (+https://github.com/vitkuz573/soc-db)"


def fetch(url: str, ttl: int = 86400) -> str:
    """Fetch a URL with caching.

    Retrieves the content at the given URL. Results are cached on disk
    under CACHE_DIR keyed by MD5 hash of the URL. Subsequent calls within
    the TTL window return the cached response.

    Args:
        url: The URL to fetch.
        ttl: Time-to-live in seconds for the cache (default 86400).

    Returns:
        The response body as a UTF-8 decoded string.
    """
    key = hashlib.md5(url.encode(), usedforsecurity=False).hexdigest()
    cache_file = CACHE_DIR / key
    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < ttl:
            return cache_file.read_text("utf-8")
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=30) as resp:  # nosec - controlled URLs only
        data: str = resp.read().decode("utf-8")
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
    fpath.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", "utf-8")
    logger.info("%s: %d entries (%d new, %d updated, %d pruned)", vfile, len(output), added, updated, removed)


from soc_db.enrich._vendor_data import (
    FIELD_GROUPS,
    FIELD_WEIGHTS,
    MEMORY_CLOCK_FROM_TYPE,
    VENDOR_FILES,
    VENDOR_KNOWLEDGE,
)
from soc_db.enrich._helpers import _has, clean


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
    vk = VENDOR_KNOWLEDGE.get(chip.get("vendor", ""), {})
    model_upper = chip.get("model", "").upper()
    if not chip.get("memory_clock") and chip.get("memory_type"):
        for mtype, clock in MEMORY_CLOCK_FROM_TYPE.items():
            if mtype in chip["memory_type"].upper():
                chip["memory_clock"] = clock
                break
    if not chip.get("memory_bus") and chip.get("memory_type") in ("LPDDR5X", "LPDDR5", "LPDDR4X", "LPDDR4"):
        chip["memory_bus"] = 64
    if not chip.get("architecture") and vk.get("architecture"):
        chip["architecture"] = vk["architecture"]
    if not chip.get("process_nm") and vk.get("process_map"):
        for key, nm in vk["process_map"].items():
            if key.upper() in model_upper:
                chip["process_nm"] = nm
                chip["process_name"] = f"{nm}nm"
                break
    if not chip.get("gpu") and vk.get("gpu_map"):
        for key, gpu_name in vk["gpu_map"].items():
            if key.upper() in model_upper:
                chip["gpu"] = gpu_name
                break
    y_chk = chip.get("year")
    if y_chk and (y_chk < 2003 or y_chk > 2026):
        chip["year"] = None
    year = chip.get("year")
    if not year:
        for f_text in (chip.get("model", "").upper(), chip.get("name", "").upper()):
            if not f_text:
                continue
            m = re.search(r"MT(\d{4})", f_text)
            if m:
                mt_val = int(m.group(1))
                if mt_val >= 9900:
                    year = 2025
                elif mt_val >= 9800:
                    year = 2024
                elif mt_val >= 9200:
                    year = 2023
                elif mt_val >= 8700:
                    year = 2022
                elif mt_val >= 8300:
                    year = 2021
                elif mt_val >= 8000:
                    year = 2020
                elif mt_val >= 7900:
                    year = 2019
                elif mt_val >= 7500:
                    year = 2018
                elif mt_val >= 7000:
                    year = 2017
                elif mt_val >= 6500:
                    year = 2016
                elif mt_val >= 6000:
                    year = 2015
                elif mt_val >= 5000:
                    year = 2014
                else:
                    year = 2013
                break
            m = re.search(r"(?:DIMENSITY|HELIO)\s*(\d{3,4})", f_text)
            if m:
                d = int(m.group(1))
                if d >= 9400:
                    year = 2025
                elif d >= 9300 or d >= 9200:
                    year = 2024
                elif d >= 9000:
                    year = 2023
                elif d >= 8400 or d >= 8300:
                    year = 2024
                elif d >= 8200:
                    year = 2023
                elif d >= 8100 or d >= 8000:
                    year = 2022
                elif d >= 7200:
                    year = 2023
                elif d >= 7000 or d >= 6000:
                    year = 2022
                elif d >= 1200 or d >= 1100:
                    year = 2021
                elif d >= 1000:
                    year = 2020
                elif d >= 900:
                    year = 2019
                elif d >= 800:
                    year = 2018
                elif d >= 700:
                    year = 2017
                elif d >= 600:
                    year = 2016
                elif d >= 500:
                    year = 2015
                else:
                    year = 2014
                break
            m = re.search(r"KIRIN\s*(\d{3,4})", f_text)
            if m:
                kirin = int(m.group(1))
                if kirin >= 9010:
                    year = 2024
                elif kirin >= 9000:
                    year = 2020
                elif kirin >= 8000:
                    year = 2024
                elif kirin >= 990:
                    year = 2019
                elif kirin >= 980:
                    year = 2018
                elif kirin >= 970:
                    year = 2017
                elif kirin >= 960:
                    year = 2016
                elif kirin >= 950 or kirin >= 930:
                    year = 2015
                elif kirin >= 920 or kirin >= 900:
                    year = 2014
                elif kirin >= 800 or kirin >= 700:
                    year = 2018
                elif kirin >= 600:
                    year = 2015
                else:
                    year = 2013
                break
            m = re.search(r"(?:SM|SDM)(\d{3,4})", f_text)
            if m:
                sm = int(m.group(1))
                if sm >= 8750:
                    year = 2025
                elif sm >= 8650:
                    year = 2024
                elif sm >= 8550:
                    year = 2023
                elif sm >= 8450:
                    year = 2022
                elif sm >= 8350:
                    year = 2021
                elif sm >= 8250:
                    year = 2020
                elif sm >= 8150:
                    year = 2019
                elif sm >= 8000:
                    year = 2018
                elif sm >= 7000:
                    year = 2017
                elif sm >= 6000:
                    year = 2016
                elif sm >= 5000:
                    year = 2015
                elif sm >= 4000:
                    year = 2014
                elif sm >= 3000:
                    year = 2013
                elif sm >= 2000:
                    year = 2012
                else:
                    year = 2011
                break
            m = re.search(r"(?:MSM|APQ)(\d{4})", f_text)
            if m:
                msm = int(m.group(1))
                if msm >= 9000:
                    year = 2018
                elif msm >= 8998:
                    year = 2017
                elif msm >= 8996:
                    year = 2016
                elif msm >= 8994:
                    year = 2015
                elif msm >= 8974:
                    year = 2013
                elif msm >= 8960:
                    year = 2012
                elif msm >= 8900:
                    year = 2011
                elif msm >= 8200:
                    year = 2010
                elif msm >= 7600:
                    year = 2009
                elif msm >= 7200:
                    year = 2008
                else:
                    year = 2007
                break
            m = re.search(r"EXYNOS", f_text)
            if m:
                all_nums = re.findall(r"(\d{4})", f_text[m.end() :])
                if all_nums:
                    ex = int(all_nums[0])
                    if ex >= 2500:
                        year = 2025
                    elif ex >= 2400:
                        year = 2024
                    elif ex >= 2200:
                        year = 2022
                    elif ex >= 2100:
                        year = 2021
                    elif ex >= 2000:
                        year = 2020
                    elif ex >= 1580:
                        year = 2025
                    elif ex >= 1480:
                        year = 2024
                    elif ex >= 1380:
                        year = 2023
                    elif ex >= 1280:
                        year = 2022
                    elif ex >= 1080:
                        year = 2020
                    else:
                        year = 2005
                    break
                all_3 = re.findall(r"(\d{3})", f_text[m.end() :])
                if all_3:
                    ex3 = int(all_3[0])
                    year = 2020 if ex3 >= 990 or ex3 >= 980 or ex3 >= 880 or ex3 >= 850 else 2015
                    break
                m_w = re.search(r"EXYNOS\s+W(\d+)", f_text)
                if m_w:
                    w = int(m_w.group(1))
                    year = 2023 if w >= 930 else 2020
                    break
                m_a = re.search(r"EXYNOS\s+AUTO\s*V(\d+)", f_text)
                if m_a:
                    av = int(m_a.group(1))
                    year = 2023 if av >= 920 else 2020
                    break
            m = re.search(r"SNAPDRAGON\s*X\s*(?:ELITE|PLUS)", f_text)
            if m and not re.search(r"X\s*2", f_text):
                year = 2024
                break
            m = re.search(r"SNAPDRAGON\s*X\s*2", f_text)
            if m:
                year = 2025
                break
            m = re.search(r"SNAPDRAGON\s*(\d+)\s*GEN\s*(\d+)", f_text)
            if m:
                series = int(m.group(1))
                gen = int(m.group(2))
                year = 2021 + gen if series >= 8 else 2020 + gen
                break
            m = re.search(r"RK(\d{4})", f_text)
            if m:
                rk = int(m.group(1))
                year = 2008 + (rk - 2000) // 200
                break
            m = re.search(r"\b([AM])(\d+)\b", f_text)
            if m:
                prefix = m.group(1)
                num = int(m.group(2))
                if prefix == "A":
                    if num >= 18:
                        year = 2025
                    elif num == 17:
                        year = 2024
                    elif num == 16:
                        year = 2023
                    elif num == 15:
                        year = 2022
                    elif num == 14:
                        year = 2020
                    elif num == 13:
                        year = 2019
                    elif num == 12:
                        year = 2018
                    elif num == 11:
                        year = 2017
                    elif num == 10:
                        year = 2016
                    elif num == 9:
                        year = 2015
                    elif num == 8:
                        year = 2014
                    elif num == 7:
                        year = 2013
                    else:
                        year = 2011 + num - 5
                elif prefix == "M":
                    if num >= 4:
                        year = 2025
                    elif num == 3:
                        year = 2023
                    elif num == 2:
                        year = 2022
                    elif num == 1:
                        year = 2020
                break
            m = re.search(r"TEGRA\s*(\d+)", f_text)
            if m:
                t = int(m.group(1))
                year = 2008 + t
                break
            m = re.search(r"\bT([01]\d{2}|20[0-9])\b", f_text)
            if m:
                year = 2008 + int(m.group(1)[:2])
                break
            x1_match = re.search(r"(?:TE|T)\d{3}X1", f_text)
            if x1_match:
                year = 2015
                break
            m = re.search(r"ATOM\s*(\w+)", f_text)
            if m:
                atom_name = m.group(1).upper()
                if re.search(r"Z\d{3,}", atom_name) or re.search(r"N\d{3,}", atom_name) or re.search(r"x\d{2,}", atom_name):
                    pass
            m = re.search(r"\b[xzzn]\d+", f_text, re.IGNORECASE)
            if m:
                if re.search(r"[xX]\d", f_text):
                    year = 2015
                elif re.search(r"[Zz]\d{4}", f_text):
                    year = 2014
            m = re.search(r"\bG(\d+)\s*GEN\s*(\d+)", f_text)
            if m:
                g_series = int(m.group(1))
                g_gen = int(m.group(2))
                if g_series == 1:
                    year = 2020 + g_gen
                elif g_series == 3:
                    year = 2022 + g_gen - 1 if g_gen >= 3 else 2021
                else:
                    year = 2020 + g_gen + (g_series > 1)
                break
            m = re.search(r"\bG(\d+)X\s*GEN\s*(\d+)", f_text)
            if m:
                g_gen = int(m.group(2))
                year = 2020 + g_gen if g_gen == 1 else 2021 + g_gen
                break
            m = re.search(r"MICROSOFT\s+SQ(\d+)", f_text)
            if m:
                sq = int(m.group(1))
                year = 2018 + sq
                break
            m = re.search(r"\bQCS(\d{3})\b", f_text)
            if m:
                qcs = int(m.group(1))
                year = 2015 + (qcs // 100)
                break
            m = re.search(r"\bSC(\d{4})", f_text)
            if m:
                sc = int(m.group(1))
                if sc >= 8380:
                    year = 2022
                elif sc >= 8280:
                    year = 2021
                elif sc >= 8180:
                    year = 2019
                elif sc >= 7280:
                    year = 2021
                elif sc >= 7180:
                    year = 2020
                else:
                    year = 2018
                break
            m = re.search(r"\bSA(\d{4})P?\b", f_text)
            if m:
                sa = int(m.group(1))
                if sa >= 8295:
                    year = 2021
                elif sa >= 8255:
                    year = 2024
                elif sa >= 8195 or sa >= 8155 or sa >= 6155:
                    year = 2019
                else:
                    year = 2018
                break
            m = re.search(r"WEAR\s*(\d+)", f_text)
            if m:
                wear = int(m.group(1))
                year = 2016 + (wear - 2100) // 500 if wear >= 2100 else 2018 + (wear - 2500) // 500
                year = 2020
                break
            m = re.search(r"W\d+\+?\s*GEN\s*(\d+)", f_text)
            if m:
                w_gen = int(m.group(1))
                year = 2021 + w_gen
                break
            m = re.search(r"XR(\d+)\s*(?:GEN\s*(\d+))?", f_text)
            if m:
                xr = int(m.group(1))
                xr_gen = m.group(2)
                if xr_gen:
                    year = 2020 + int(xr_gen)
                elif xr >= 2:
                    year = 2019
                else:
                    year = 2018
                break
            m = re.search(r"SNAPDRAGON\s+(\d{3})(\d?)", f_text)
            if m:
                sd_full = int(m.group(1))
                if sd_full >= 855:
                    year = 2019
                elif sd_full >= 845:
                    year = 2018
                elif sd_full >= 835:
                    year = 2017
                elif sd_full >= 820:
                    year = 2016
                elif sd_full >= 810:
                    year = 2015
                elif sd_full >= 800 or sd_full >= 600:
                    year = 2014
                elif sd_full >= 400:
                    year = 2013
                else:
                    year = 2012
                break
            m = re.search(r"\bQSD(\d{4})\b", f_text)
            if m:
                year = 2009
                break
            m = re.search(r"\bSW(\d{4})\b", f_text)
            if m:
                sw = int(m.group(1))
                year = 2015 + (sw // 1000)
                break
            m = re.search(r"\bCE(\d{4})\b", f_text)
            if m:
                ce = int(m.group(1))
                year = 2008 + (ce // 1000)
                break
            m = re.search(r"\bOMAP(\d)\d{3}\b", f_text)
            if m:
                omap_gen = int(m.group(1))
                year = 2004 + omap_gen * 2
                break
            m = re.search(r"\b([AHFR])(\d{2,3})", f_text)
            if m:
                aw_prefix = m.group(1)
                aw_num = int(m.group(2))
                if aw_prefix == "F":
                    year = 2015 if aw_num >= 100 else 2013
                elif aw_prefix == "R":
                    year = 2012 + (aw_num // 10) if aw_num >= 40 else 2014
                elif aw_prefix == "H":
                    if aw_num >= 700:
                        year = 2018 + (aw_num - 700) // 2
                    elif aw_num >= 600:
                        year = 2015 + (aw_num - 600) // 2
                    elif aw_num >= 500:
                        year = 2017 + (aw_num - 500) // 2
                    elif aw_num >= 300:
                        year = 2014 + (aw_num - 300) // 2
                    else:
                        year = 2013
                elif aw_prefix == "A":
                    if aw_num >= 100:
                        year = 2014 + (aw_num - 100) // 10
                    elif aw_num >= 80:
                        year = 2014
                    elif aw_num >= 40:
                        year = 2015
                    elif aw_num >= 31:
                        year = 2013
                    elif aw_num >= 20 or aw_num >= 13:
                        year = 2012
                    elif aw_num >= 10:
                        year = 2011
                    else:
                        year = 2011 + aw_num // 5
                break
            m = re.search(r"\bS(\d{3})", f_text)
            if m:
                aml = int(m.group(1))
                if aml >= 928:
                    year = 2020
                elif aml >= 922:
                    year = 2019
                elif aml >= 912 or aml >= 905:
                    year = 2016
                elif aml >= 812:
                    year = 2015
                elif aml >= 805:
                    year = 2014
                elif aml >= 802:
                    year = 2013
                else:
                    year = 2012
                break
            if chip.get("vendor") == "Amlogic":
                m = re.search(r"\bT(\d{3})", f_text)
                if m:
                    aml_t = int(m.group(1))
                    if aml_t >= 960:
                        year = 2016
                    elif aml_t >= 950:
                        year = 2015
                    elif aml_t >= 920:
                        year = 2018
                    else:
                        year = 2014
                    break
            m = re.search(r"KOMPANIO\s*(\d+)", f_text)
            if m:
                komp = int(m.group(1))
                if komp >= 1300 or komp >= 1200 or komp >= 800:
                    year = 2022
                elif komp >= 500:
                    year = 2021
                else:
                    year = 2020
                break
            m = re.search(r"ATOM\s+([DN])(\d{4})", f_text)
            if m:
                atom_letter = m.group(1)
                atom_digits = int(m.group(2))
                year = 2010 + (atom_digits // 1000) if atom_letter == "D" else 2009 + (atom_digits // 500)
                break
            m = re.search(r"\bJZ(\d{4})\b", f_text, re.IGNORECASE)
            if m:
                jz = int(m.group(1))
                year = 2005 + (jz // 1000)
                break
            m = re.search(r"\bTHOR\b", f_text)
            if m:
                year = 2025
                break
            m = re.search(r"F1[CE](\d{3})", f_text)
            if m:
                f1 = int(m.group(1))
                year = 2014 + (f1 // 100)
                break
            m = re.search(r"AIOT\s*[Ii](\d{3})", f_text)
            if m:
                year = 2020 + (int(m.group(1)) // 100)
                break
            m = re.search(r"\bSP(\d{4})\b", f_text)
            if m:
                sp = int(m.group(1))
                year = 2010 + (sp - 9000) // 100
                break
            m = re.search(r"\bUMS(\d{4})\b", f_text)
            if m:
                ums = int(m.group(1))
                year = 2018 + ((ums - 9000) // 200)
                break
            m = re.search(r"\bK3V2", f_text)
            if m:
                year = 2012
                if "K3V2E" in f_text:
                    year = 2013
                break
            m = re.search(r"\bT(\d{2,3})", f_text)
            if m and "KIRIN" in f_text:
                kt = int(m.group(1))
                if kt >= 92:
                    year = 2025
                elif kt >= 91:
                    year = 2024
                elif kt >= 90:
                    year = 2023
                elif kt >= 80:
                    year = 2020
                break
            if year:
                break
    if year:
        chip["year"] = year
    yr = chip.get("year")
    if not chip.get("process_nm") and yr:
        proc_by_year = [
            (2024, 3),
            (2023, 4),
            (2021, 5),
            (2019, 7),
            (2017, 10),
            (2015, 14),
            (2013, 20),
            (2011, 28),
            (2009, 40),
            (0, 65),
        ]
        for yr_proc, nm in proc_by_year:
            if yr >= yr_proc:
                chip["process_nm"] = nm
                chip["process_name"] = f"{nm}nm"
                break
    yr = chip.get("year")
    if not chip.get("memory_type") and yr:
        mem_by_year = [
            (2023, "LPDDR5X"),
            (2021, "LPDDR5"),
            (2019, "LPDDR4X"),
            (2016, "LPDDR4"),
            (2014, "LPDDR3"),
            (2012, "LPDDR2"),
            (0, "LPDDR"),
        ]
        for yr_mem, mt_name in mem_by_year:
            if yr >= yr_mem:
                chip["memory_type"] = mt_name
                break
    yr = chip.get("year")
    if not chip.get("storage_type") and yr:
        st_by_year = [
            (2021, "UFS 3.1"),
            (2019, "UFS 3.0"),
            (2017, "UFS 2.1"),
            (2015, "UFS 2.0"),
            (0, "eMMC 5.0"),
        ]
        for yr_st, st_name in st_by_year:
            if yr >= yr_st:
                chip["storage_type"] = st_name
                break
    mt = chip.get("memory_type", "")
    if not chip.get("memory_clock") and mt:
        clock_map = {
            "LPDDR6": 6400,
            "LPDDR5X": 4266,
            "LPDDR5": 3200,
            "LPDDR4X": 2133,
            "LPDDR4": 1600,
            "LPDDR3": 933,
            "LPDDR2": 533,
            "LPDDR": 400,
        }
        for k, v in clock_map.items():
            if mt.startswith(k):
                chip["memory_clock"] = v
                break
    if not chip.get("memory_bus") and mt:
        if mt.startswith(("LPDDR4", "LPDDR5", "LPDDR6")):
            chip["memory_bus"] = 64
        elif mt.startswith(("LPDDR3", "LPDDR2", "LPDDR")):
            chip["memory_bus"] = 32
    if not chip.get("gpu") and chip.get("year"):
        vendor = chip.get("vendor", "")
        yr = chip["year"]
        gpu_by_vendor = {
            "Allwinner": "Mali-400 MP" if yr < 2015 else "Mali-450 MP",
            "Amlogic": "Mali-450 MP" if yr < 2017 else "Mali-G31 MP2",
            "Rockchip": "Mali-400 MP" if yr < 2014 else "Mali-T760 MP4" if yr < 2017 else "Mali-G52 MP2",
            "Nvidia": "Nvidia GPU",
            "Intel Atom": "Intel HD Graphics",
            "TI OMAP": "PowerVR SGX",
            "Ingenic": "GC400" if yr < 2014 else "GC800",
            "Actions": "Mali-400 MP",
        }
        if vendor in gpu_by_vendor:
            chip["gpu"] = gpu_by_vendor[vendor]
        elif vendor == "MediaTek":
            chip["gpu"] = "Mali GPU"
        elif vendor == "Qualcomm":
            chip["gpu"] = "Adreno GPU"
        elif vendor == "Samsung" or vendor == "HiSilicon" or vendor == "Unisoc":
            chip["gpu"] = "Mali GPU"
        elif vendor == "NXP i.MX":
            chip["gpu"] = "Vivante GC"
        elif vendor == "Xilinx":
            chip["gpu"] = "Mali GPU"
    if not chip.get("npu") and yr and yr >= 2017:
        vendor = chip.get("vendor", "")
        model_u = chip.get("model", "").upper()
        name_u = chip.get("name", "").upper()
        vk_npu = vk.get("npu_map", {})
        if not vk_npu:
            if vendor == "Apple" and chip["year"] >= 2017:
                chip["npu"] = "Neural Engine"
            elif vendor == "Qualcomm":
                if any(x in model_u for x in ("SM8", "SM7", "SDM8", "SDM7")) or any(x in model_u for x in ("SM6", "SDM6")):
                    chip["npu"] = "Hexagon NPU"
            elif vendor == "MediaTek":
                if "DIMENSITY" in model_u or "DIMENSITY" in name_u:
                    chip["npu"] = "MediaTek APU"
                elif re.search(r"MT\d{4}", model_u):
                    mt_m = re.search(r"MT(\d{4})", model_u)
                    if mt_m and int(mt_m.group(1)) >= 8000:
                        chip["npu"] = "MediaTek APU"
            elif vendor == "Samsung" and re.search(r"EXYNOS\s*(21|22|24|25)", model_u):
                chip["npu"] = "Samsung NPU"
            elif vendor == "HiSilicon" and re.search(r"KIRIN\s*(9|8|7)", model_u):
                chip["npu"] = "HiSilicon NPU"
    if not chip.get("modem") and chip.get("year"):
        vendor = chip.get("vendor", "")
        model_u = chip.get("model", "").upper()
        name_u = chip.get("name", "").upper()
        yr = chip["year"]
        if vendor == "Qualcomm":
            sm_match = re.search(r"(SM|SDM)(\d{4})", model_u)
            if sm_match:
                sm_num = int(sm_match.group(2))
                modem_map = {8750: "X80", 8650: "X75", 8550: "X70", 8450: "X65", 8350: "X60", 8250: "X55", 8150: "X50", 8000: "X24"}
                for num, modem_name in modem_map.items():
                    if sm_num >= num:
                        chip["modem"] = f"Snapdragon {modem_name} 5G"
                        break
            gen_match = re.search(r"SNAPDRAGON\s*(\d+)\s*GEN\s*(\d+)", model_u)
            if gen_match and not chip.get("modem"):
                gen_num = int(gen_match.group(2))
                if int(gen_match.group(1)) >= 8:
                    modem_by_gen = {3: "X70", 2: "X65", 1: "X60"}
                    if gen_num in modem_by_gen:
                        chip["modem"] = f"Snapdragon {modem_by_gen[gen_num]} 5G"
            if not chip.get("modem") and chip["year"] >= 2019:
                chip["modem"] = "Snapdragon 5G"
            elif not chip.get("modem") and chip["year"] >= 2013:
                chip["modem"] = "Snapdragon 4G LTE"
        elif vendor == "MediaTek":
            if re.search(r"DIMENSITY", model_u) or re.search(r"MT\d{4}", model_u):
                if chip["year"] >= 2020:
                    chip["modem"] = "MediaTek 5G"
                elif chip["year"] >= 2015:
                    chip["modem"] = "MediaTek 4G LTE"
        elif vendor == "Samsung" and re.search(r"EXYNOS", model_u):
            if chip["year"] >= 2020:
                chip["modem"] = "Exynos 5G"
            elif chip["year"] >= 2014:
                chip["modem"] = "Exynos 4G LTE"
        elif vendor == "Apple" and chip["year"] >= 2019:
            chip["modem"] = "Apple 5G"
        elif vendor == "HiSilicon" and re.search(r"KIRIN", model_u):
            if chip["year"] >= 2019:
                chip["modem"] = "Balong 5G"
            elif chip["year"] >= 2014:
                chip["modem"] = "Balong 4G LTE"
    yr = chip.get("year")
    if not chip.get("wifi") and yr:
        wifi_by_year = [
            (2025, "Wi-Fi 7"),
            (2023, "Wi-Fi 7"),
            (2021, "Wi-Fi 6E"),
            (2019, "Wi-Fi 6"),
            (2015, "Wi-Fi 5"),
            (2010, "Wi-Fi 4"),
            (2005, "Wi-Fi 3"),
            (0, "Wi-Fi 2"),
        ]
        for yr_wifi, w_name in wifi_by_year:
            if yr >= yr_wifi:
                chip["wifi"] = w_name
                break
    if not chip.get("bluetooth") and yr:
        bt_by_year = [
            (2025, "5.4"),
            (2023, "5.3"),
            (2021, "5.2"),
            (2019, "5.0"),
            (2017, "4.2"),
            (2015, "4.1"),
            (2012, "4.0"),
            (2010, "3.0"),
            (2007, "2.1"),
            (0, "2.0"),
        ]
        for yr_bt, b_name in bt_by_year:
            if yr >= yr_bt:
                chip["bluetooth"] = b_name
                break
    if not chip.get("aliases"):
        aliases = set()
        name = chip.get("name", "")
        model = chip.get("model", "")
        if name and model and model not in name:
            aliases.add(f"{name} ({model})")
        codenames = {
            "SM8250": ["Kona"],
            "SM8350": ["Lahaina"],
            "SM8450": ["Waipio"],
            "SM8475": ["Waipio"],
            "SM8550": ["Kalama"],
            "SM8650": ["Pineapple"],
            "SM8750": ["Pineapple"],
        }
        for key, alist in codenames.items():
            if key.upper() in model_upper:
                for a in alist:
                    aliases.add(a)
        if aliases:
            chip["aliases"] = sorted(aliases)
    w_total = sum(FIELD_WEIGHTS.get(f, 1) for _, flist in FIELD_GROUPS.items() for f in flist)
    w_filled = sum(FIELD_WEIGHTS.get(f, 1) for _, flist in FIELD_GROUPS.items() for f in flist if _has(chip, f))
    chip["completeness"] = round(w_filled / max(w_total, 1), 4)
    if not chip.get("sources"):
        chip["sources"] = {}
    chip["updated"] = "2026-06-21"
    return chip


def enrich_all(chips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply :func:`enrich_one` to every chip in a list.

    Args:
        chips: List of chip records to enrich.

    Returns:
        The enriched list (same objects in-place).
    """
    return [enrich_one(c) for c in chips]
