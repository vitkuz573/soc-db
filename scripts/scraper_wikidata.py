#!/usr/bin/env python3
"""Massive Wikidata SPARQL SoC scraper.

Queries ALL system-on-chip instances from Wikidata (5000+ entries),
groups by manufacturer, and writes to vendor-specific data files.
"""

import json
import re
import sys
from collections import defaultdict
from common import (
    fetch, clean, extract_int, extract_freq, extract_process,
    slug, write_vendor_file, DATA_DIR,
)

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql?format=json&query="

# Wikidata → our vendor name mapping
# Format: "wikidata QID": "our vendor name"
KNOWN_MANUFACTURERS = {
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
    # Additional manufacturers to map
    "Q17011490": "Unisoc",
    "Q24949598": "Unisoc",
    "Q1061228": "Realtek",
    "Q585964": "Marvell",
    "Q84423": "Broadcom",
    "Q4677449": "Actions Semiconductor",
    "Q1275817": "Loongson",
    "Q10860611": "Zhaoxin",
    "Q2299406": "Microchip",
    "Q220064": "STMicroelectronics",
    "Q128895": "AMD",
    "Q1000473": "NXP i.MX",
    "Q1194639": "Texas Instruments",
    "Q1124560": "Freescale",
    "Q1124561": "Freescale",
    "Q157106": "Renesas",
    "Q310791": "Infineon",
    "Q193555": "Analog Devices",
    "Q460201": "Maxim Integrated",
    "Q740345": "Cypress",
    "Q82301": "Microchip",
    "Q746194": "Silicon Labs",
    "Q485995": "Espressif",
    # New vendors from Linux DT
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
}

# Architecture QID → name
ARCH_MAP = {
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

# Reverse: our vendor → Wikidata QID (for the manufacturer filter)
OUR_VENDOR_QIDS = {name: qid for qid, name in KNOWN_MANUFACTURERS.items()}


def build_query(vendor_qid: str | None = None) -> str:
    """Build SPARQL query. If vendor_qid is None, get ALL SoCs."""
    vendor_filter = ""
    if vendor_qid:
        vendor_filter = f"?soc wdt:P178 wd:{vendor_qid}."

    # Use a simpler query that's less likely to timeout
    return f"""
    SELECT DISTINCT ?soc ?socLabel ?manufacturer ?manufacturerLabel
                    ?modelNumber ?cores ?arch ?archLabel
                    ?processNode ?gpu ?gpuLabel ?publicationDate ?maxFreq
    WHERE {{
      ?soc wdt:P31 wd:Q610398.           # instance of system-on-chip
      {vendor_filter}
      OPTIONAL {{ ?soc wdt:P178 ?manufacturer. }}
      OPTIONAL {{ ?soc wdt:P1552 ?modelNumber. }}
      OPTIONAL {{ ?soc wdt:P2101 ?cores. }}
      OPTIONAL {{ ?soc wdt:P577 ?publicationDate. }}
      OPTIONAL {{ ?soc wdt:P880 ?arch. }}
      OPTIONAL {{ ?soc wdt:P2048 ?processNode. }}
      OPTIONAL {{ ?soc wdt:P1542 ?gpu. }}
      OPTIONAL {{ ?soc wdt:P2144 ?maxFreq. }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    ORDER BY ?publicationDate
    LIMIT 10000
    """


def fetch_sparql(query: str) -> list[dict]:
    """Execute SPARQL query and return bindings."""
    import urllib.parse
    url = SPARQL_ENDPOINT + urllib.parse.quote(query)
    try:
        raw = fetch(url, ttl=3600)
        data = json.loads(raw)
        return data.get("results", {}).get("bindings", [])
    except Exception as e:
        print(f"  SPARQL error: {e}", file=sys.stderr)
        return []


def extract_value(binding: dict, key: str) -> str:
    """Extract value from SPARQL binding."""
    if key not in binding:
        return ""
    return binding[key].get("value", "")


def parse_chip(binding: dict) -> dict | None:
    """Parse a SPARQL binding into a chip dict."""
    name = extract_value(binding, "socLabel")
    if not name:
        return None

    # Filter out categories, series, etc.
    if name.startswith("Category:") or name.startswith("List of"):
        return None
    if any(kw in name.lower() for kw in ("series", "family", "processor", "comparison",
                                           "architecture", "instruction set", "microarchitecture",
                                           "category:", "template:", "wikipedia:")):
        return None

    # Get manufacturer
    mfr_qid = extract_value(binding, "manufacturer").split("/")[-1]
    mfr_label = extract_value(binding, "manufacturerLabel")
    vendor = KNOWN_MANUFACTURERS.get(mfr_qid, mfr_label)

    model = extract_value(binding, "modelNumber")

    # Generate ID
    chip_id = slug(name, model)
    if not chip_id or chip_id == "unknown":
        # Use Q-ID as fallback
        chip_id = "wd_" + extract_value(binding, "soc").split("/")[-1]

    chip = {
        "id": chip_id,
        "name": name,
        "vendor": vendor,
    }

    # Model
    if model:
        chip["model"] = model

    # Cores
    cores_raw = extract_value(binding, "cores")
    if cores_raw:
        try:
            chip["cores"] = int(float(cores_raw))
        except ValueError:
            pass
    if "cores" not in chip:
        chip["cores"] = 8

    # Architecture
    arch_qid = extract_value(binding, "arch").split("/")[-1]
    if arch_qid in ARCH_MAP:
        chip["architecture"] = ARCH_MAP[arch_qid]
    else:
        arch_label = extract_value(binding, "archLabel")
        if arch_label:
            chip["architecture"] = arch_label
    if "architecture" not in chip:
        chip["architecture"] = "ARMv8.2-A"

    # GPU
    gpu = extract_value(binding, "gpuLabel")
    if gpu:
        chip["gpu"] = gpu

    # Process node (stored as nm integer in Wikidata)
    process_raw = extract_value(binding, "processNode")
    if process_raw:
        try:
            nm = int(float(process_raw))
            chip["process"] = f"{nm}nm"
        except ValueError:
            pm = re.search(r'(\d+)\s*nm', process_raw, re.IGNORECASE)
            if pm:
                chip["process"] = pm.group(0)

    # Year
    year_raw = extract_value(binding, "publicationDate")
    if year_raw:
        try:
            year = int(year_raw[:4])
            if 1980 < year < 2028:
                chip["year"] = year
        except ValueError:
            pass

    # Max frequency (MHz)
    freq_raw = extract_value(binding, "maxFreq")
    if freq_raw:
        try:
            freq_val = float(freq_raw)
            if freq_val >= 1000:
                chip["max_freq"] = f"{freq_val/1000:.2f} GHz"
            else:
                chip["max_freq"] = f"{freq_val:.0f} MHz"
        except ValueError:
            pass

    return chip


def scrape_all() -> dict[str, list[dict]]:
    """Scrape ALL SoCs from Wikidata, grouped by vendor."""
    print("  Fetching ALL SoCs from Wikidata (this may take a minute)...")
    query = build_query()
    results = fetch_sparql(query)

    print(f"  Got {len(results)} results from Wikidata")

    # Group by manufacturer
    vendor_chips: dict[str, list[dict]] = defaultdict(list)
    other_chips = []
    seen_ids = set()
    skipped = 0

    for binding in results:
        chip = parse_chip(binding)
        if not chip:
            skipped += 1
            continue
        if chip["id"] in seen_ids:
            continue
        seen_ids.add(chip["id"])

        # Check if vendor is known
        if chip["vendor"] in KNOWN_MANUFACTURERS.values():
            vendor_chips[chip["vendor"]].append(chip)
        elif chip["vendor"]:
            # Unknown vendor, but still has a name
            other_chips.append(chip)

    # Sort chips within each vendor by year
    for vendor in vendor_chips:
        vendor_chips[vendor].sort(key=lambda c: (c.get("year", 9999), c["name"]))

    other_chips.sort(key=lambda c: (c.get("year", 9999), c["name"], c["vendor"]))

    print(f"  Grouped into {len(vendor_chips)} known vendors + Others ({len(other_chips)})")
    print(f"  Skipped {skipped} entries")

    vendor_chips["Other"] = other_chips
    return vendor_chips


def main():
    print("=== Wikidata SoC Scraper ===")
    print()

    # First scrape all
    vendor_chips = scrape_all()

    # Write known vendors
    known_vendor_files = {
        "Qualcomm": "qualcomm.json",
        "MediaTek": "mediatek.json",
        "Samsung": "exynos.json",
        "HiSilicon": "kirin.json",
        "Google": "tensor.json",
        "Apple": "apple.json",
        "Rockchip": "rockchip.json",
        "Allwinner": "allwinner.json",
        "Amlogic": "amlogic.json",
        "Nvidia": "nvidia.json",
        "TI OMAP": "ti_omap.json",
        "Intel Atom": "intel_atom.json",
        "Ingenic": "ingenic.json",
        "NXP i.MX": "nxp_imx.json",
        "Unisoc": "unisoc.json",
        "Realtek": "realtek.json",
        "Broadcom": "broadcom.json",
        "Marvell": "marvell.json",
        "Espressif": "espressif.json",
        "APM": "apm.json",
        "ASPEED": "aspeed.json",
        "Airoha": "airoha.json",
        "Altera": "altera.json",
        "Amazon": "amazon.json",
        "Bitmain": "bitmain.json",
        "Cavium": "cavium.json",
        "Nuvoton": "nuvoton.json",
        "Socionext": "socionext.json",
        "Sophgo": "sophgo.json",
        "Synaptics": "synaptics.json",
        "Tesla": "tesla.json",
        "Toshiba": "toshiba.json",
        "Actions": "actions.json",
        "Renesas": "renesas.json",
        "STMicroelectronics": "stmicro.json",
        "Microchip": "microchip.json",
        "Xilinx": "xilinx.json",
        "AMD": "amd.json",
    }

    # Update VENDOR_FILES in common.py dynamically for new vendors
    # Write known vendors
    for vendor, vfile in known_vendor_files.items():
        if vendor in vendor_chips and vendor_chips[vendor]:
            fpath = DATA_DIR / vfile
            existing = {}
            if fpath.exists():
                try:
                    for c in json.loads(fpath.read_text("utf-8")):
                        existing[c["id"]] = c
                except json.JSONDecodeError:
                    pass

            # For known vendors, Wikidata is secondary to Wikipedia
            # Merge: existing (Wikipedia) wins, Wikidata fills gaps
            new_count = 0
            upd_count = 0
            for chip in vendor_chips[vendor]:
                cid = chip["id"]
                if cid in existing:
                    # Only add fields that are missing
                    for k, v in chip.items():
                        if k not in existing[cid] or existing[cid][k] in (None, "", 0, 8, "ARMv8.2-A", "?"):
                            existing[cid].setdefault(k, v)
                    upd_count += 1
                else:
                    existing[cid] = chip
                    new_count += 1

            output = sorted(existing.values(), key=lambda x: (x.get("year", 9999), x["name"]))
            fpath.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", "utf-8")
            print(f"  {vfile}: {len(output)} entries (+{new_count}, ~{upd_count} updated)")

    # Write "Other" vendors as a separate file
    other_file = DATA_DIR / "other.json"
    other_chips = vendor_chips.get("Other", [])
    # Group by actual vendor name within other
    other_by_vendor = defaultdict(list)
    for c in other_chips:
        other_by_vendor[c["vendor"]].append(c)

    # Write each other vendor as a separate file
    other_written = 0
    for vname, chips in sorted(other_by_vendor.items()):
        # Sanitize filename
        vkey = vname.lower().replace(" ", "_").replace("/", "_").replace("&", "and")
        vkey = re.sub(r"[^a-z0-9_]", "", vkey)
        vfile = f"{vkey}.json"
        fpath = DATA_DIR / vfile

        output = sorted(chips, key=lambda x: (x.get("year", 9999), x["name"]))
        fpath.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", "utf-8")
        other_written += 1
        print(f"  {vfile}: {len(output)} entries ({vname})")

    total = sum(len(c) for c in vendor_chips.values())
    print(f"\n  Total: {total} chips across {len(vendor_chips)} vendor groups")

    # Remove the "Other" key from vendor_chips for indexing
    if "Other" in vendor_chips:
        del vendor_chips["Other"]

    return total


if __name__ == "__main__":
    main()
