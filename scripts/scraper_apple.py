#!/usr/bin/env python3
"""Apple Silicon scraper - model-to-name mapping fallback."""

import re
from bs4 import BeautifulSoup
from common import fetch, clean, slug, write_vendor_file
from parsers import parse_cpu, parse_process, parse_gpu

WIKI_A = "https://en.wikipedia.org/wiki/Apple_A_series"
WIKI_M = "https://en.wikipedia.org/wiki/Apple_M_series"

APPLE_CHIPS = {
    "APL1102_T8103": ("Apple A14 Bionic", "T8103", 2020, "5nm", "6-core (2x Firestorm + 4x Icestorm)", "Apple A14 GPU"),
    "APL1W82_T8006": ("Apple A12Z Bionic", "T8006", 2020, "7nm", "8-core", "Apple A12Z GPU"),
    "APL1W86_T8301": ("Apple A13 Bionic", "T8301", 2019, "7nm", "6-core (2x Lightning + 4x Thunder)", "Apple A13 GPU"),
    "APL1W15_T8310": ("Apple A15 Bionic", "T8310", 2021, "5nm", "6-core (2x Avalanche + 4x Blizzard)", "Apple A15 GPU"),
    "APL_0778": ("Apple A11 Bionic", "", 2017, "10nm", "6-core (2x Monsoon + 4x Mistral)", "Apple A11 GPU"),
    "APL_1023": ("Apple A12 Bionic", "", 2018, "7nm", "6-core (2x Vortex + 4x Tempest)", "Apple A12 GPU"),
    "APL_1027": ("Apple A12X Bionic", "", 2018, "7nm", "8-core", "Apple A12X GPU"),
    "APL1102": ("Apple A14 Bionic", "T8103", 2020, "5nm", "6-core (2x Firestorm + 4x Icestorm)", "Apple A14 GPU"),
    "T8103": ("Apple M1", "APL1102", 2020, "5nm", "8-core (4x Firestorm + 4x Icestorm)", "Apple M1 GPU"),
    "T8112": ("Apple M1 Pro", "APL1103", 2021, "5nm", "8/10-core", "Apple M1 Pro GPU"),
    "T8116": ("Apple M1 Max", "APL1104", 2021, "5nm", "10-core", "Apple M1 Max GPU"),
    "T6000": ("Apple M2", "APL1109", 2022, "5nm", "8-core (4x Avalanche + 4x Blizzard)", "Apple M2 GPU"),
    "T6020": ("Apple M2 Pro", "APL1113", 2023, "5nm", "10/12-core", "Apple M2 Pro GPU"),
    "T6021": ("Apple M2 Max", "APL1114", 2023, "5nm", "12-core", "Apple M2 Max GPU"),
    "T8120": ("Apple A16 Bionic", "APL1110", 2022, "4nm", "6-core (2x Avalanche + 4x Blizzard)", "Apple A16 GPU"),
    "T8130": ("Apple A17 Pro", "APL1201", 2023, "3nm", "6-core (2x Everest + 4x Sawtooth)", "Apple A17 Pro GPU"),
    "T9500": ("Apple A18 Pro", "APL1210", 2024, "3nm", "6-core (2x Everest + 4x Sawtooth)", "Apple A18 Pro GPU"),
    "T9515": ("Apple M4", "", 2024, "3nm", "10-core (4x Everest + 6x Sawtooth)", "Apple M4 GPU"),
    "T9520": ("Apple M4 Pro", "", 2024, "3nm", "12-core", "Apple M4 Pro GPU"),
    "T9522": ("Apple M4 Max", "", 2024, "3nm", "16-core", "Apple M4 Max GPU"),
}


def parse_tables(html, series):
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
            clean_name = name_text.strip()
            clean_model = model_text.strip()
            keys = [f"{clean_name}_{clean_model}", clean_name, clean_model]
            chip_info = None
            for key in keys:
                if key in APPLE_CHIPS:
                    chip_info = APPLE_CHIPS[key]
                    break
            if not chip_info:
                continue
            name, model, year, proc, cpu_desc, gpu_desc = chip_info
            chip_id = slug(name, model)
            if chip_id in seen:
                continue
            seen.add(chip_id)
            chip = {"id": chip_id, "name": name, "vendor": "Apple", "model": model or name, "year": year}
            chip.update(parse_process(f"{proc}"))
            chip.update(parse_cpu(cpu_desc))
            chip.update(parse_gpu(gpu_desc))
            if not chip.get("architecture"):
                chip["architecture"] = "ARMv8.6-A"
            chips.append(chip)

    return chips


def scrape():
    print("  Fetching Apple A-series...")
    a_chips = parse_tables(fetch(WIKI_A), "A")
    print("  Fetching Apple M-series...")
    m_chips = parse_tables(fetch(WIKI_M), "M")
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
