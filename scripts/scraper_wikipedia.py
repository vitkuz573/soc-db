#!/usr/bin/env python3
"""Enterprise Wikipedia SoC scraper — extracts all infobox fields."""

import re
import sys
from bs4 import BeautifulSoup
from common import fetch, clean, extract_model, slug, write_vendor_file
from parsers import detect_columns, parse_cell, parse_cpu, parse_gpu, parse_process, parse_memory, parse_modem, parse_connectivity, parse_video, parse_display, parse_camera

WIKI_PAGES = {
    "Qualcomm": "https://en.wikipedia.org/wiki/List_of_Qualcomm_Snapdragon_processors",
    "MediaTek": "https://en.wikipedia.org/wiki/List_of_MediaTek_processors",
    "Samsung": "https://en.wikipedia.org/wiki/Exynos",
    "HiSilicon": "https://en.wikipedia.org/wiki/HiSilicon",
    "Google": "https://en.wikipedia.org/wiki/Google_Tensor",
    "Apple": None,
    "Rockchip": "https://en.wikipedia.org/wiki/Rockchip",
    "Allwinner": "https://en.wikipedia.org/wiki/Allwinner_Technology",
    "Amlogic": "https://en.wikipedia.org/wiki/Amlogic",
    "Nvidia": "https://en.wikipedia.org/wiki/Tegra",
    "TI OMAP": "https://en.wikipedia.org/wiki/OMAP",
    "Intel Atom": "https://en.wikipedia.org/wiki/List_of_Intel_Atom_processors",
    "Ingenic": "https://en.wikipedia.org/wiki/Ingenic",
    "NXP i.MX": "https://en.wikipedia.org/wiki/NXP_i.MX",
}

KNOWN_PREFIXES = [
    "Snapdragon", "Qualcomm", "Microsoft", "Dimensity", "Helio", "Kompanio",
    "Pentonic", "Exynos", "Kirin", "Tensor", "Apple",
    "RK", "RV", "R", "A", "H", "F", "V", "T", "MR", "Allwinner",
    "S", "OMAP", "AM", "DM", "Atom", "Celeron", "Pentium", "Xeon",
    "Jz", "JZ", "i.MX", "IMX", "MCIMX", "SC", "SL", "SP",
]

SKIP_SECTIONS = [
    "features of", "comparison", "acronym", "bluetooth", "qcc",
    "finances", "acquisitions", "products", "history",
]


def extract_chip_name(first_cell_text: str, section_heading: str = "") -> str | None:
    text = clean(first_cell_text)
    if text:
        text = re.sub(r"\s*\[.*?\]\s*", " ", text).strip()
    for prefix in KNOWN_PREFIXES:
        if text and text.startswith(prefix):
            return text.split("[")[0].strip()
    if text and re.match(r'^[A-Z][A-Za-z0-9]{2,}\d{2,}', text):
        return text.split("[")[0].strip()[:60]
    if section_heading:
        for prefix in KNOWN_PREFIXES:
            if section_heading.startswith(prefix):
                return section_heading.split("[")[0].strip()
        m = re.search(r'(Tegra\s+\d\w*|i\.MX\s+[\d\w]+|Atom\s+\w+)', section_heading, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def is_valid_chip_name(name):
    if not name or name in ("?", "", "-", "—", "TBC", "TBD"):
        return False
    if len(name) < 3 or re.match(r'^\d+[\s.]', name) or not re.search(r'[a-zA-Z]', name):
        return False
    if name.lower() in ("armv7", "armv8", "armv9", "android", "linux", "windows", "unknown", "n/a"):
        return False
    if not re.search(r'\d', name):
        for prefix in KNOWN_PREFIXES:
            if name.startswith(prefix):
                return True
        return False
    return True


def parse_standard_table(tbl, section_heading="", chip_name_override=""):
    chips = []
    rows = tbl.find_all("tr")
    if len(rows) < 2:
        return chips

    # Detect column headers from first row
    header_cells = rows[0].find_all(["th", "td"])
    columns = detect_columns(header_cells)

    data_rows = [tr for tr in rows[1:] if tr.find_all("td")]
    seen_ids = set()

    for tr in data_rows:
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue

        # Chip name from first column
        if chip_name_override:
            chip_name = chip_name_override
        else:
            name_raw = clean(tds[0].get_text(" ", strip=True)) if tds else ""
            chip_name = extract_chip_name(name_raw or "", section_heading)
        if not chip_name or not is_valid_chip_name(chip_name):
            continue

        chip_id = slug(chip_name, "")
        if chip_id in seen_ids:
            continue
        seen_ids.add(chip_id)

        chip = {"id": chip_id, "name": chip_name, "vendor": "?", "cores": 8, "architecture": "ARMv8.2-A"}

        # Model from first cell
        model = extract_model(tds[0].get_text(" ", strip=True))
        if model:
            chip["model"] = model

        # Process column-aligned cells
        for ci, (field_name, parser) in enumerate(columns):
            if ci >= len(tds):
                continue
            text = clean(tds[ci].get_text(" ", strip=True)) or ""
            parsed = parse_cell(text, field_name, parser)
            for k, v in parsed.items():
                if k not in chip or not chip[k]:
                    chip[k] = v

        # Override vendor
        chip["vendor"] = "?"

        # Year from section heading
        if "year" not in chip:
            ym = re.search(r'(20\d\d)', section_heading)
            if ym:
                chip["year"] = int(ym.group(1))

        chips.append(chip)

    return chips


def parse_transposed_table(tbl, section_heading=""):
    """Amlogic-style: chips are column headers, specs are rows."""
    chips = []
    rows = tbl.find_all("tr")
    if not rows:
        return chips

    header_cells = rows[0].find_all(["th", "td"])
    chip_names = []
    for cell in header_cells[1:]:
        name = clean(cell.get_text(" ", strip=True))
        if name and is_valid_chip_name(name):
            chip_names.append(name)

    for name in chip_names:
        chip_id = slug(name)
        chip = {"id": chip_id, "name": name, "vendor": "?", "cores": 8, "architecture": "ARMv8.2-A"}

        for ci, cell in enumerate(header_cells[1:], 1):
            cn = clean(cell.get_text(" ", strip=True))
            if cn == name:
                for row in rows[1:]:
                    cells = row.find_all(["th", "td"])
                    if ci < len(cells):
                        cell_text = clean(cells[ci].get_text(" ", strip=True)) or ""
                        row_label = clean(cells[0].get_text(" ", strip=True)) or ""
                        rl = row_label.lower()

                        if "cpu" in rl:
                            chip.update(parse_cpu(cell_text))
                        elif "gpu" in rl:
                            chip.update(parse_gpu(cell_text))
                        elif "process" in rl or "fab" in rl:
                            chip.update(parse_process(cell_text))
                        elif "memory" in rl or "ram" in rl:
                            chip.update(parse_memory(cell_text))
                        elif "modem" in rl:
                            chip.update(parse_modem(cell_text))
                        elif "connect" in rl or "wifi" in rl or "bluetooth" in rl:
                            chip.update(parse_connectivity(cell_text))
                        elif "video" in rl:
                            chip.update(parse_video(cell_text))
                        elif "display" in rl:
                            chip.update(parse_display(cell_text))
                        elif "camera" in rl:
                            chip.update(parse_camera(cell_text))
                break

        if "year" not in chip:
            ym = re.search(r'(20\d\d)', section_heading)
            if ym:
                chip["year"] = int(ym.group(1))
        chips.append(chip)

    return chips


def scrape_vendor(vendor):
    url = WIKI_PAGES.get(vendor)
    if not url:
        return []

    print(f"  Fetching {url}")
    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")

    tables = soup.find_all("table", class_="wikitable")
    if not tables:
        tables = soup.find_all("table")
        tables = [t for t in tables if t.find("th")]

    all_chips = []
    seen_ids = set()
    is_amlogic = vendor == "Amlogic"

    for tbl in tables:
        prev = tbl.find_previous(["h2", "h3", "h4"])
        heading = prev.get_text(" ", strip=True) if prev else ""
        hl = heading.lower()
        if any(kw in hl for kw in SKIP_SECTIONS):
            continue

        chip_override = None
        if vendor == "Nvidia":
            m = re.search(r'(Tegra\s+\d+\w*)', heading, re.IGNORECASE)
            if m:
                chip_override = m.group(1)
        elif vendor == "NXP i.MX":
            m = re.search(r'(i\.MX[\s-]*\d[\w]*)', heading, re.IGNORECASE)
            if m:
                chip_override = m.group(1).replace("-", " ")
        elif vendor == "Intel Atom":
            m = re.search(r'Atom\s+\w+', heading)
            if m:
                chip_override = f"Atom {m.group(0)}"

        if is_amlogic:
            chips = parse_transposed_table(tbl, heading)
        else:
            chips = parse_standard_table(tbl, heading, chip_name_override=chip_override or "")

        for c in chips:
            c["vendor"] = vendor
            if c["id"] not in seen_ids:
                seen_ids.add(c["id"])
                all_chips.append(c)

    return all_chips


def main():
    vendors = sys.argv[1:] if len(sys.argv) > 1 else [v for v, u in WIKI_PAGES.items() if u]
    for vendor in vendors:
        if vendor not in WIKI_PAGES:
            print(f"Unknown vendor: {vendor}")
            continue
        if not WIKI_PAGES[vendor]:
            print(f"Skipping {vendor}")
            continue
        print(f"\n--- {vendor} ---")
        chips = scrape_vendor(vendor)
        if chips:
            print(f"  Extracted {len(chips)} chips, enriching...")
            write_vendor_file(vendor, chips)
        print(f"  Total: {len(chips)} chips")


if __name__ == "__main__":
    main()
