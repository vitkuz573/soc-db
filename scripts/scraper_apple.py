#!/usr/bin/env python3
"""Apple Silicon scraper - Wikipedia uses images for names, so we use structured data.

Apple SoCs on Wikipedia don't have marketing names in plain text (they use images).
This scraper works around that by using the known model-to-name mapping for recent chips.
"""

import re
from bs4 import BeautifulSoup
from common import fetch, clean, extract_int, slug, write_vendor_file

WIKI_A = "https://en.wikipedia.org/wiki/Apple_A_series"
WIKI_M = "https://en.wikipedia.org/wiki/Apple_M_series"

# Known Apple chip name mapping
APPLE_CHIPS = {
    # A-series (iPhone/iPad)
    "APL1102_T8103": ("Apple A14 Bionic", "T8103", 2020, "5nm"),
    "APL1W82_T8006": ("Apple A12Z Bionic", "T8006", 2020, "7nm"),
    "APL1W86_T8301": ("Apple A13 Bionic", "T8301", 2019, "7nm"),
    "APL1W15_T8310": ("Apple A15 Bionic", "T8310", 2021, "5nm"),
    "APL_0778": ("Apple A11 Bionic", "", 2017, "10nm"),
    "APL_1023": ("Apple A12 Bionic", "", 2018, "7nm"),
    "APL_1027": ("Apple A12X Bionic", "", 2018, "7nm"),
    "APL1102": ("Apple A14 Bionic", "T8103", 2020, "5nm"),
    # M-series (Mac)
    "T8103": ("Apple M1", "APL1102", 2020, "5nm"),
    "T8112": ("Apple M1 Pro", "APL1103", 2021, "5nm"),
    "T8116": ("Apple M1 Max", "APL1104", 2021, "5nm"),
    "T6000": ("Apple M2", "APL1109", 2022, "5nm"),
    "T6020": ("Apple M2 Pro", "APL1113", 2023, "5nm"),
    "T6021": ("Apple M2 Max", "APL1114", 2023, "5nm"),
    "T8120": ("Apple A16 Bionic", "APL1110", 2022, "4nm"),
    "T8130": ("Apple A17 Pro", "APL1201", 2023, "3nm"),
    "T9500": ("Apple A18 Pro", "APL1210", 2024, "3nm"),
    "T9515": ("Apple M4", "", 2024, "3nm"),
}


def parse_tables(html: str, series: str) -> list[dict]:
    """Parse Apple Wikipedia tables, using internal model numbers to map names."""
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table", class_="wikitable")
    chips = []
    seen = set()

    for tbl in tables:
        rows = tbl.find_all("tr")
        for tr in rows:
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue

            name_text = tds[0].get_text(" ", strip=True)
            model_text = tds[1].get_text(" ", strip=True) if len(tds) > 1 else ""
            tech_text = ""

            # Find process node if available
            for td in tds[2:]:
                t = td.get_text(" ", strip=True)
                if "nm" in t:
                    m = re.search(r'(\d+)\s*nm', t, re.IGNORECASE)
                    if m:
                        tech_text = m.group(0)
                    break

            # Build lookup key
            clean_name = name_text.strip()
            clean_model = model_text.strip()
            keys = [
                f"{clean_name}_{clean_model}",
                clean_name,
                clean_model,
            ]

            chip_info = None
            for key in keys:
                if key in APPLE_CHIPS:
                    chip_info = APPLE_CHIPS[key]
                    break

            if chip_info:
                name, model, year, proc = chip_info
                chip_id = slug(name, model)
                if chip_id in seen:
                    continue
                seen.add(chip_id)

                chip = {
                    "id": chip_id,
                    "name": name,
                    "vendor": "Apple",
                    "cores": 8,
                    "architecture": "ARMv8.6-A",
                    "year": year,
                }
                if model:
                    chip["model"] = model
                if not tech_text and proc:
                    chip["process"] = proc
                elif tech_text:
                    chip["process"] = tech_text

                chips.append(chip)

    return chips


def scrape() -> list[dict]:
    print("  Fetching Apple A-series...")
    a_html = fetch(WIKI_A)
    a_chips = parse_tables(a_html, "A")

    print("  Fetching Apple M-series...")
    m_html = fetch(WIKI_M)
    m_chips = parse_tables(m_html, "M")

    # Deduplicate
    seen = set()
    all_chips = []
    for c in a_chips + m_chips:
        if c["id"] not in seen:
            seen.add(c["id"])
            all_chips.append(c)

    return all_chips


def main():
    print("Apple Silicon scraper")
    chips = scrape()
    if chips:
        write_vendor_file("Apple", chips)
    print(f"  Total: {len(chips)} chips")


if __name__ == "__main__":
    main()
