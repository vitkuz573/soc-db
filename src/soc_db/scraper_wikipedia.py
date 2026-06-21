#!/usr/bin/env python3
"""Enterprise Wikipedia SoC scraper — extracts all infobox fields."""

import logging
import re
import sys

from bs4 import BeautifulSoup

from soc_db.common import clean, extract_model, fetch, slug, write_vendor_file
from soc_db.parsers import (
    detect_columns,
    parse_camera,
    parse_cell,
    parse_connectivity,
    parse_cpu,
    parse_display,
    parse_gpu,
    parse_memory,
    parse_modem,
    parse_process,
    parse_video,
)

logger = logging.getLogger(__name__)

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
    "RK", "RV", "MR", "Allwinner",
    "OMAP", "AM", "DM", "Atom", "Celeron", "Pentium", "Xeon",
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


NON_CHIP_NAMES = {
    "armv7", "armv8", "armv9", "android", "linux", "windows",
    "unknown", "n/a", "samsung", "intel", "nvidia", "apple",
    "bluetooth", "wifi", "wi-fi", "ethernet", "usb", "pcie",
    "lpddr3", "lpddr4", "lpddr4x", "lpddr5", "lpddr5x",
    "ddr3", "ddr4", "ddr5", "ufs", "nvme", "emmc",
    "gps", "gnss", "nfc", "isp", "dsp", "npu", "gpu", "cpu",
    "tbd", "tbc", "announced", "released", "launch",
    "october", "november", "december", "january", "february",
    "march", "april", "may", "june", "july", "august", "september",
    "pixel", "device", "devices", "feature", "features",
}


def is_valid_chip_name(name):
    if not name or name in ("?", "", "-", "—", "TBC", "TBD"):
        return False
    low = name.lower()
    if len(name) < 2 or re.match(r'^\d+[\s.]', name) or not re.search(r'[a-zA-Z]', name):
        return False
    if low in NON_CHIP_NAMES:
        return False
    if re.match(r'armv\d', low):
        return False
    if re.match(r'^\d+\s*nm', low):
        return False
    if re.match(r'^\d+x\d+', low):
        return False
    if re.match(r'^[\d.]+[\s]*(mhz|ghz|mb/s|gb/s|gflops|tops)', low):
        return False
    if len(name) >= 5 and re.match(r'^[A-Z][a-z]+$', name) and not re.search(r'\d', name):
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
    header_cells = rows[0].find_all(["th", "td"])
    columns = detect_columns(header_cells)
    data_rows = [tr for tr in rows[1:] if tr.find_all("td")]
    seen_ids = set()

    for tr in data_rows:
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
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
        model = extract_model(tds[0].get_text(" ", strip=True))
        if model:
            chip["model"] = model
        for ci, (field_name, parser) in enumerate(columns):
            if ci >= len(tds):
                continue
            text = clean(tds[ci].get_text(" ", strip=True)) or ""
            parsed = parse_cell(text, field_name, parser)
            for k, v in parsed.items():
                if k not in chip or not chip[k]:
                    chip[k] = v
        chip["vendor"] = "?"
        if "year" not in chip:
            for src in [chip_name, chip.get("model", ""), section_heading]:
                ym = re.search(r'(20[0-2]\d)', src)
                if ym:
                    y = int(ym.group(1))
                    if 2007 <= y <= 2030:
                        chip["year"] = y
                        break
                    if len(chips) > 1 and "year" in chips[-1]:
                        y = chips[-1]["year"]
                        if 2007 <= y <= 2030:
                            chip["year"] = y
                            break
        chips.append(chip)
    return chips


def _sub_label(text: str) -> bool:
    t = text.strip().lower()
    labels = {"launch date", "type", "frequency", "speed", "bandwidth", "bit width",
              "bus width", "model number", "part number", "codename", "μarch",
              "isa", "fabrication", "manufacturer"}
    return t in labels


def _align_cell(row_cells, chip_col, num_chips):
    tds = [c for c in row_cells if c.name == "td"]
    data_cells = [c for c in tds if not _sub_label(c.get_text(" ", strip=True))]
    if len(data_cells) == num_chips:
        return data_cells[chip_col]
    start = 0
    for c in row_cells:
        if c.name == "th" or _sub_label(c.get_text(" ", strip=True)):
            start += 1
        else:
            break
    idx = start + chip_col
    return row_cells[idx] if idx < len(row_cells) else None


def parse_transposed_table(tbl, section_heading="", vendor=""):
    chips = []
    rows = tbl.find_all("tr")
    if not rows:
        return chips
    header_cells = rows[0].find_all(["th", "td"])
    chip_specs = []
    for cell in header_cells[1:]:
        orig = clean(cell.get_text(" ", strip=True))
        if not orig:
            continue
        if not is_valid_chip_name(orig):
            display = f"{vendor} {orig}".strip()
        elif len(orig) <= 4 or re.match(r'^G\d', orig) or re.match(r'^[A-Z]\d\s*\(', orig):
            prefix = vendor or section_heading.replace("series", "").strip()
            display = f"{prefix} {orig}".strip()
        else:
            display = orig
        if is_valid_chip_name(display):
            chip_specs.append((display, orig))

    num_chips = len(chip_specs)

    for display_name, orig_name in chip_specs:
        chip_id = slug(display_name)
        chip = {"id": chip_id, "name": display_name, "vendor": "?", "cores": 8, "architecture": "ARMv8.2-A"}

        for ci, cell in enumerate(header_cells[1:], 1):
            cn = clean(cell.get_text(" ", strip=True))
            if cn == orig_name:
                chip_col = ci - 1
                for row in rows[1:]:
                    row_cells = row.find_all(["th", "td"])
                    dc = _align_cell(row_cells, chip_col, num_chips)
                    if dc is None:
                        continue
                    cell_text = clean(dc.get_text(" ", strip=True)) or ""
                    row_label = clean(row_cells[0].get_text(" ", strip=True)) or ""
                    rl = row_label.lower()

                    if "cpu" in rl or "core" in rl:
                        chip.update(parse_cpu(cell_text))
                    elif "gpu" in rl or "graphic" in rl:
                        chip.update(parse_gpu(cell_text))
                    elif "process" in rl or "fab" in rl or "node" in rl:
                        chip.update(parse_process(cell_text))
                    elif "memory" in rl or "ram" in rl:
                        chip.update(parse_memory(cell_text))
                    elif "modem" in rl:
                        chip.update(parse_modem(cell_text))
                    elif "connect" in rl or "wifi" in rl or "bluetooth" in rl or "wireless" in rl:
                        chip.update(parse_connectivity(cell_text))
                    elif "video" in rl:
                        chip.update(parse_video(cell_text))
                    elif "display" in rl or "screen" in rl:
                        chip.update(parse_display(cell_text))
                    elif "camera" in rl or "isp" in rl:
                        chip.update(parse_camera(cell_text))
                    elif "year" not in chip and ("launch" in rl or "released" in rl or "announced" in rl or "date" in rl or "soc" in rl):
                        ym = re.search(r'(20\d{2})', cell_text)
                        if ym:
                            y = int(ym.group(1))
                            if 2007 <= y <= 2030:
                                chip["year"] = y
                    elif "model" in rl and "number" in rl:
                        m = re.search(r'([A-Z0-9]{3,}(?:\([A-Z0-9]+\))?)', cell_text)
                        if m:
                            chip["model"] = m.group(1)
                    elif "codename" in rl:
                        chip["codename"] = cell_text
                    elif "npu" in rl or "ai" in rl or "tpu" in rl:
                        chip["npu"] = cell_text[:80]
                    elif "charge" in rl or "battery" in rl:
                        chip["charging"] = cell_text[:80]
                    elif "storage" in rl or "ufs" in rl:
                        chip["storage_type"] = cell_text[:80]
                break

        if "year" not in chip:
            for src in [display_name, section_heading]:
                ym = re.search(r'(20[0-2]\d)', src)
                if ym:
                    y = int(ym.group(1))
                    if 2007 <= y <= 2030:
                        chip["year"] = y
                        break
        chips.append(chip)

    return chips


SPEC_LABEL_PATTERNS = [
    r'armv\d', r'^\d+\s*(nm|bit|gb|mb|ghz|mhz|gflops|tops|core)',
    r'(mhz|ghz|gb/s|mb/s|gflops|tops|nm)$',
    r'^(october|november|december|january|february|march|april|may|june|july|august|september)\b',
    r'^\d{4}-\d{2}-\d{2}', r'octa.nucleo|nona.core|hexa.core|quad.core|dual.core',
    r'^64.bits?|^32.bits?', r'\d×\d+\s*bit',
    r'lpddr|ddr\d', r'ufs\s*\d\.', r'wifi|bluetooth|gnss|nfc',
    r'^(feature|device|model number|part number|codename|fabrication|manufacturer|memory|storage|connectivity|charging|video|camera|display)',
    r'^trustzone|^trusty\s+os',
    r'^edge\s+tpu', r'^gen\s+\d+\s+edge\s+tpu',
    r'exynos\s+\d+\w?\b', r'^mali\b',
    r'^\d+x\s+\d+-bit', r'^quad-channel',
    r'^1st\s+gen|^2nd\s+gen|^3rd\s+gen|^\d+th\s+gen',
]


def _is_spec_label(text: str) -> bool:
    low = text.lower().strip()
    if not low or not re.search(r'[a-zA-Z]', low):
        return True
    if re.search(r'(mhz|ghz|tops|gflops|fps|gbps|mbps)\b', low):
        return True
    for pat in SPEC_LABEL_PATTERNS:
        if re.search(pat, low):
            return True
    return False


def _is_transposed_table(tbl) -> bool:
    rows = tbl.find_all("tr")
    if len(rows) < 3:
        return False
    header_cells = rows[0].find_all(["th", "td"])
    first_header = header_cells[0].get_text(" ", strip=True) if header_cells else ""
    if first_header:
        return False
    data_rows = [r for r in rows[1:] if r.find_all("td")]
    if len(data_rows) < 2:
        return False
    n_cols = len(header_cells)
    if len(data_rows) > n_cols * 2:
        return True
    first_col_values = []
    for r in data_rows[:5]:
        tds = r.find_all("td")
        if tds:
            first_col_values.append(tds[0].get_text(" ", strip=True))
    if not first_col_values:
        return False
    non_chip = sum(1 for v in first_col_values if _is_spec_label(v))
    return non_chip >= len(first_col_values) * 0.5


def scrape_vendor(vendor):
    url = WIKI_PAGES.get(vendor)
    if not url:
        return []
    logger.info("Fetching %s", url)
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

        if is_amlogic or _is_transposed_table(tbl):
            chips = parse_transposed_table(tbl, heading, vendor)
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
            logger.warning("Unknown vendor: %s", vendor)
            continue
        if not WIKI_PAGES[vendor]:
            logger.info("Skipping %s", vendor)
            continue
        logger.info("--- %s ---", vendor)
        chips = scrape_vendor(vendor)
        if chips:
            logger.info("Extracted %d chips, enriching...", len(chips))
            write_vendor_file(vendor, chips)
        logger.info("Total: %d chips", len(chips))


if __name__ == "__main__":
    main()
