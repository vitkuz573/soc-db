#!/usr/bin/env python3
"""Wikidata SPARQL scraper for SoCs.

Queries Wikidata by manufacturer (P178) to get all SoC/processor items.
This catches chips that Wikipedia "List of..." pages don't cover.
"""

import json
import sys
import time
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import quote

from common import slug, write_vendor_file, DATA_DIR

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

# Known SoC/processor instance-of (P31) classes
# These are the common classes used for system-on-a-chip items
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

# Manufacturer search terms → Wikidata QID
# Each vendor has:
#   search_name: term to use for exact label match
#   qid: Wikidata item ID (verified)
#   variants: alternative names to search for (e.g. parent company names)
MANUFACTURERS = {
    "Qualcomm": {
        "qid": "Q544847",
        "variant_search": ["Qualcomm Snapdragon"],
    },
    "MediaTek": {
        "qid": "Q699848",
        "variant_search": [],
    },
    "Samsung": {
        "qid": "Q22822500",  # Samsung System LSI Division
        "variant_search": ["Samsung Exynos", "Samsung Electronics"],
        "alt_qids": ["Q20718"],  # Samsung Electronics
    },
    "HiSilicon": {
        "qid": "Q3135124",
        "variant_search": [],
    },
    "Apple": {
        "qid": "Q312",
        "variant_search": ["Apple Silicon"],
    },
    "Intel Atom": {
        "qid": "Q248",  # Intel Corporation
        "variant_search": [],
    },
    "Rockchip": {
        "qid": "Q1772192",
        "variant_search": ["Rockchip (company)"],
    },
    "Allwinner": {
        "qid": "Q1775596",
        "variant_search": [],
    },
    "Amlogic": {
        "qid": "Q474724",
        "variant_search": [],
    },
    "Nvidia": {
        "qid": "Q182477",
        "variant_search": ["NVIDIA Tegra"],
    },
    "TI OMAP": {
        "qid": "Q193412",
        "variant_search": ["Texas Instruments"],
    },
    "Ingenic": {
        "qid": "Q10849149",
        "variant_search": ["Beijing Ingenic"],
    },
    "NXP i.MX": {
        "qid": "Q1155668",
        "variant_search": ["NXP Semiconductors", "Freescale Semiconductor"],
    },
    "Unisoc": {
        "qid": "Q117321369",
        "variant_search": ["Spreadtrum"],
    },
    "Broadcom": {
        "qid": "Q7905541",  # Broadcom Inc.
        "variant_search": [],
    },
    "Realtek": {
        "qid": "Q1061228",  # Realtek (might be wrong)
        "variant_search": [],
    },
    "Marvell": {
        "qid": "Q1347782",
        "variant_search": [],
    },
    "Renesas": {
        "qid": "Q1324134",
        "variant_search": [],
    },
    "STMicroelectronics": {
        "qid": "Q208585",
        "variant_search": [],
    },
    "Microchip": {
        "qid": "Q1933150",
        "variant_search": ["Microchip Technology", "Atmel"],
    },
    "Xilinx": {
        "qid": "Q635059",
        "variant_search": [],
    },
}


def run_sparql(query: str, retries=3) -> list[dict]:
    """Execute a SPARQL query against Wikidata."""
    url = f"{WIKIDATA_SPARQL}?format=json&query={quote(query)}"
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "SOC-DB/1.0"})
            with urlopen(req, timeout=120) as r:
                data = json.loads(r.read())
                return data["results"]["bindings"]
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
            else:
                print(f"    SPARQL error: {e}", file=sys.stderr)
                return []


def fetch_chips_by_manufacturer(qid: str, vendor_name: str) -> list[dict]:
    """Fetch all SoC items from Wikidata that have this manufacturer.
    
    Uses multiple P31 (instance of) classes that SoCs might use.
    Also tries without P31 filter to catch misclassified items.
    """
    # Build P31 filter: wdt:P31 IN (Q122901167, Q610398, ...)
    p31_values = " ".join(f"wd:{c}" for c in SOC_CLASSES)
    
    # Strategy 1: Filter by P31 class (specific)
    query1 = f"""
    SELECT DISTINCT ?item ?itemLabel ?itemDescription ?model ?manufacturer WHERE {{
      VALUES ?p31 {{ {p31_values} }}
      ?item wdt:P31 ?p31 .
      ?item wdt:P178 wd:{qid} .
      OPTIONAL {{ ?item wdt:P2101 ?model . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    LIMIT 2000
    """
    
    results1 = run_sparql(query1)
    chips_by_qid = {}
    
    for r in results1:
        q = r.get("item", {}).get("value", "").split("/")[-1]
        label = r.get("itemLabel", {}).get("value", "")
        desc = r.get("itemDescription", {}).get("value", "")
        model = r.get("model", {}).get("value", "")
        
        if not label:
            continue
        
        chips_by_qid[q] = {
            "id": slug(label),
            "name": label,
            "vendor": vendor_name,
            "description": desc,
            "model": model or label,
            "source": "wikidata",
        }
    
    # Strategy 2: Also fetch items with manufacturer but NO P31 filter
    # (catches misclassified items)
    query2 = f"""
    SELECT DISTINCT ?item ?itemLabel ?itemDescription ?model WHERE {{
      ?item wdt:P178 wd:{qid} .
      ?item rdfs:label ?label .
      FILTER(LANG(?label) = "en")
      FILTER(
        CONTAINS(LCASE(?label), "soc") ||
        CONTAINS(LCASE(?label), "snapdragon") ||
        CONTAINS(LCASE(?label), "dimensity") ||
        CONTAINS(LCASE(?label), "exynos") ||
        CONTAINS(LCASE(?label), "kirin") ||
        CONTAINS(LCASE(?label), "helio") ||
        CONTAINS(LCASE(?label), "tensor") ||
        CONTAINS(LCASE(?label), "tegra") ||
        CONTAINS(LCASE(?label), "rockchip") ||
        CONTAINS(LCASE(?label), "omap") ||
        CONTAINS(LCASE(?label), "atom") ||
        CONTAINS(LCASE(?label), "bionic") ||
        CONTAINS(LCASE(?label), "processor") ||
        CONTAINS(LCASE(?label), "chip") ||
        CONTAINS(LCASE(?label), "samsung") ||
        CONTAINS(LCASE(?label), "apple") ||
        CONTAINS(LCASE(?label), "a[0-9]") ||
        CONTAINS(LCASE(?label), "m[0-9]")
      )
      OPTIONAL {{ ?item wdt:P2101 ?model . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    LIMIT 1000
    """
    
    results2 = run_sparql(query2)
    for r in results2:
        q = r.get("item", {}).get("value", "").split("/")[-1]
        label = r.get("itemLabel", {}).get("value", "")
        if q in chips_by_qid or not label:
            continue
        
        chips_by_qid[q] = {
            "id": slug(label),
            "name": label,
            "vendor": vendor_name,
            "description": r.get("itemDescription", {}).get("value", ""),
            "model": r.get("model", {}).get("value", "") or label,
            "source": "wikidata",
        }
    
    return list(chips_by_qid.values())


def fetch_chips_from_list_page(wikipedia_title: str, vendor_name: str) -> list[dict]:
    """Fallback: fetch items from a Wikipedia list page via Wikidata.
    
    Uses pageprops to get the Wikidata QID of the list page's main item,
    then queries for items that are subclasses or instances.
    """
    from urllib.parse import quote as q
    import re
    
    # Use Wikipedia API to get the page's Wikidata item
    url = f"https://en.wikipedia.org/w/api.php?action=query&titles={q(wikipedia_title)}&prop=pageprops&format=json"
    req = Request(url, headers={"User-Agent": "SOC-DB/1.0"})
    try:
        with urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        pages = data.get("query", {}).get("pages", {})
        for pid, page in pages.items():
            if "pageprops" in page and "wikibase_item" in page["pageprops"]:
                wb_qid = page["pageprops"]["wikibase_item"]
                print(f"    Wikidata list item: {wb_qid}")
                
                # Query for items that are subclasses of this list
                q3 = f"""
                SELECT DISTINCT ?item ?itemLabel ?itemDescription WHERE {{
                  ?item wdt:P279* wd:{wb_qid} .
                  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
                }}
                LIMIT 2000
                """
                # Don't use subclasses, use items that are part of this category
                q3 = f"""
                SELECT DISTINCT ?item ?itemLabel ?itemDescription ?model WHERE {{
                  ?item (wdt:P361|wdt:P527|wdt:P1552) wd:{wb_qid} .
                  OPTIONAL {{ ?item wdt:P2101 ?model . }}
                  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
                }}
                LIMIT 2000
                """
                return run_sparql(q3)
    except Exception as e:
        print(f"    Error: {e}")
    
    return []


def scrape_vendor(vendor_name: str, manuf_info: dict) -> list[dict]:
    """Scrape all chips for a given vendor from Wikidata."""
    print(f"  {vendor_name}...", end=" ", flush=True)
    
    all_chips = []
    seen_qids = set()
    
    # Primary QID
    qid = manuf_info.get("qid")
    if qid:
        chips = fetch_chips_by_manufacturer(qid, vendor_name)
        for c in chips:
            if c["id"] not in seen_qids:
                all_chips.append(c)
                seen_qids.add(c["id"])
    
    # Alternative QIDs
    for alt_qid in manuf_info.get("alt_qids", []):
        chips = fetch_chips_by_manufacturer(alt_qid, vendor_name)
        for c in chips:
            if c["id"] not in seen_qids:
                all_chips.append(c)
                seen_qids.add(c["id"])
    
    # If we got very few, try with a broader search
    if len(all_chips) < 5:
        # Try fetching ALL items by manufacturer (no P31 filter)
        query_bare = f"""
        SELECT DISTINCT ?item ?itemLabel ?itemDescription WHERE {{
          ?item wdt:P178 wd:{qid} .
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }}
        LIMIT 2000
        """
        if qid:
            results = run_sparql(query_bare)
            for r in results:
                q = r.get("item", {}).get("value", "").split("/")[-1]
                label = r.get("itemLabel", {}).get("value", "")
                if not label or slug(label) in seen_qids:
                    continue
                all_chips.append({
                    "id": slug(label),
                    "name": label,
                    "vendor": vendor_name,
                    "description": r.get("itemDescription", {}).get("value", ""),
                    "model": label,
                    "source": "wikidata",
                })
                seen_qids.add(slug(label))
    
    print(f"{len(all_chips)} chips")
    return all_chips


def main():
    print("=== Wikidata SPARQL Scraper ===")
    print()
    
    # Only scrape vendors not already covered by Wikipedia
    # or new vendors we haven't covered at all
    target_vendors = [
        "Unisoc",
        "Broadcom",
        "Realtek",
        "Marvell",
        "Renesas",
        "STMicroelectronics",
        "Microchip",
        "Xilinx",
        "NXP i.MX",  # Wikipedia only gave 6
        "Nvidia",     # Wikipedia gave 14, likely more
    ]
    
    total = 0
    for vendor in target_vendors:
        if vendor in MANUFACTURERS:
            chips = scrape_vendor(vendor, MANUFACTURERS[vendor])
            if chips:
                write_vendor_file(vendor, chips)
            total += len(chips)
        else:
            print(f"  {vendor}: no manufacturer info")
    
    print(f"\n  Total new chips: {total}")


if __name__ == "__main__":
    main()
