#!/usr/bin/env python3
"""Universal Wikipedia SoC scraper. Handles standard wikitable layouts,
section-heading-based chip names (Tegra, NXP), and transposed tables (Amlogic)."""

import re
import sys
from bs4 import BeautifulSoup
from common import (
    fetch, clean, extract_int, extract_freq, extract_process,
    slug, write_vendor_file,
)

WIKI_PAGES = {
    "Qualcomm": "https://en.wikipedia.org/wiki/List_of_Qualcomm_Snapdragon_processors",
    "MediaTek": "https://en.wikipedia.org/wiki/List_of_MediaTek_processors",
    "Samsung": "https://en.wikipedia.org/wiki/Exynos",
    "HiSilicon": "https://en.wikipedia.org/wiki/HiSilicon",
    "Google": "https://en.wikipedia.org/wiki/Google_Tensor",
    "Apple": None,  # handled by scraper_apple.py
    "Rockchip": "https://en.wikipedia.org/wiki/Rockchip",
    "Allwinner": "https://en.wikipedia.org/wiki/Allwinner_Technology",
    "Amlogic": "https://en.wikipedia.org/wiki/Amlogic",
    "Nvidia": "https://en.wikipedia.org/wiki/Tegra",
    "TI OMAP": "https://en.wikipedia.org/wiki/OMAP",
    "Intel Atom": "https://en.wikipedia.org/wiki/List_of_Intel_Atom_processors",
    "Ingenic": "https://en.wikipedia.org/wiki/Ingenic",
    "NXP i.MX": "https://en.wikipedia.org/wiki/NXP_i.MX",
}

# All known SoC/processor brand prefixes for name validation
KNOWN_PREFIXES = [
    "Snapdragon", "Qualcomm", "Microsoft", "Dimensity", "Helio", "Kompanio",
    "Pentonic", "Exynos", "Kirin", "Tensor", "Apple",
    "RK", "RV", "R", "A", "H", "F", "V", "T", "MR", "Allwinner",
    "S", "S905", "S912", "S922", "S805", "S802", "S812",
    "T", "T20", "T30", "T114", "APX",
    "OMAP", "AM", "DM",
    "Atom", "Celeron", "Pentium", "Xeon",
    "Jz", "JZ",
    "i.MX", "IMX", "MCIMX",
    "SC", "SL", "SP",
]

# Section keywords to skip as non-chip
SKIP_SECTIONS = [
    "features of", "comparison", "acronym", "bluetooth", "qcc",
    "finances", "acquisitions", "products", "history",
]


def extract_chip_name(first_cell_text: str, section_heading: str = "") -> str | None:
    """Extract clean chip name from first cell or fallback to section heading."""
    text = clean(first_cell_text)
    if text:
        text = re.sub(r"\s*\[.*?\]\s*", " ", text).strip()

    # Known prefixes
    for prefix in KNOWN_PREFIXES:
        if text and text.startswith(prefix):
            return text.split("[")[0].strip()

    # Model-number-only cells (e.g., "OMAP3410", "RK3399", "S905X2")
    if text and re.match(r'^[A-Z][A-Za-z0-9]{2,}\d{2,}', text):
        return text.split("[")[0].strip()[:60]

    # Check section heading as fallback
    if section_heading:
        for prefix in KNOWN_PREFIXES:
            if section_heading.startswith(prefix):
                return section_heading.split("[")[0].strip()
        # Extract chip name from "Tegra 2" or "i.MX 6 series"
        m = re.search(r'(Tegra\s+\d\w*|i\.MX\s+[\d\w]+|Atom\s+\w+)', section_heading, re.IGNORECASE)
        if m:
            return m.group(1)

    return None


def is_valid_chip_name(name: str) -> bool:
    if not name or name in ("?", "", "-", "—", "TBC", "TBD"):
        return False
    if len(name) < 3:
        return False
    if re.match(r'^\d+[\s.]', name):
        return False
    if not re.search(r'[a-zA-Z]', name):
        return False
    if re.match(r'^[\d+]+[xX]\s*', name):
        return False
    if name.lower() in ("armv7", "armv8", "armv9", "android", "linux", "windows", "unknown", "n/a"):
        return False
    if re.match(r'^ARMv\d', name, re.IGNORECASE):
        return False
    # Must contain digit or be a known brand
    if not re.search(r'\d', name):
        for prefix in KNOWN_PREFIXES:
            if name.startswith(prefix):
                break
        else:
            return False
    return True


def extract_model(text: str) -> str | None:
    patterns = [
        r'\b(SM\d{3,}|SDM\d{3,}|MSM\d{3,}|APQ\d{3,}|SC\d{4}|QCS\d{3})\b',
        r'\b(MT\d{4,})\b',
        r'\b(Exynos\s*\d{4,})\b',
        r'\b(Kirin\s*\d{3,})\b',
        r'\b(GS\d{3})\b',
        r'\b(RK\d{3,})\b',
        r'\b(OMAP\d{4,})\b',
        r'\b(AM\d{3,}|DM\d{3,})\b',
        r'\b(APL\w+|T\d{4})\b',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).upper()
    return None


def extract_cores_and_arch(text: str) -> tuple[int | None, str | None]:
    cores = None
    arch = None
    if not text:
        return cores, arch
    if "ARMv9" in text:
        arch = "ARMv9-A"
    elif "ARMv8" in text or "A72" in text or "A53" in text or "A55" in text or "A76" in text or "A78" in text:
        arch = "ARMv8.2-A"
    elif "ARMv7" in text:
        arch = "ARMv7-A"
    m = re.search(r'(\d+)\s*(?:x\s*|core|cores?|\-core)', text, re.IGNORECASE)
    if m:
        cores = int(m.group(1))
    else:
        clusters = re.findall(r'(\d+)[xX*]\s*(?:Cortex|Kryo|Gold|Silver|A\-?\d+)', text)
        if clusters:
            cores = sum(int(c) for c in clusters)
        else:
            ci = extract_int(text)
            if ci and ci <= 16:
                cores = ci
    return cores, arch


def parse_standard_table(tbl, section_heading: str = "",
                         name_col: int = 0, model_col: int = 0,
                         chip_name_override: str = "") -> list[dict]:
    """Parse a standard wikitable where chip names are in the first column."""
    chips = []
    rows = tbl.find_all("tr")
    data_rows = [tr for tr in rows if tr.find_all("td")]
    if not data_rows:
        return chips

    seen_ids = set()

    for tr in data_rows:
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue

        # Get chip name
        if chip_name_override:
            chip_name = chip_name_override
        else:
            name_raw = clean(tds[name_col].get_text(" ", strip=True)) if name_col < len(tds) else ""
            chip_name = extract_chip_name(name_raw or "", section_heading)

        if not chip_name or not is_valid_chip_name(chip_name):
            continue

        chip_id = slug(chip_name)
        if chip_id in seen_ids:
            continue
        seen_ids.add(chip_id)

        chip = {"id": chip_id, "name": chip_name, "vendor": "?", "cores": 8, "architecture": "ARMv8.2-A"}

        # Model
        for ci in [model_col, 0, 1]:
            if ci < len(tds):
                model = extract_model(tds[ci].get_text(" ", strip=True))
                if model:
                    chip["model"] = model
                    break

        # Scan remaining cells for process, cores, GPU, freq, year
        for i, td in enumerate(tds[1:], 1):
            ct = clean(td.get_text(" ", strip=True)) or ""
            if "process" not in chip:
                proc = extract_process(ct)
                if proc:
                    chip["process"] = proc
            if "cores" not in chip or chip["cores"] == 8:
                cores, arch = extract_cores_and_arch(ct)
                if cores and cores > 1:
                    chip["cores"] = cores
                if arch:
                    chip["architecture"] = arch
            if "gpu" not in chip:
                if any(kw in ct.lower() for kw in ("mali", "adreno", "geforce", "powervr", "xclipse", "vivante")):
                    chip["gpu"] = ct[:80]
            if "max_freq" not in chip:
                freq = extract_freq(ct)
                if freq:
                    chip["max_freq"] = freq

        # Year from section heading
        if "year" not in chip:
            ym = re.search(r'(20\d\d)', section_heading)
            if ym:
                chip["year"] = int(ym.group(1))

        chips.append(chip)

    return chips


def parse_transposed_table(tbl, section_heading: str = "") -> list[dict]:
    """Parse Amlogic-style transposed tables (chips as column headers, specs as rows)."""
    chips = []
    rows = tbl.find_all("tr")
    if not rows:
        return chips

    # First row contains chip names
    header_cells = rows[0].find_all(["th", "td"])
    chip_names = []
    for cell in header_cells[1:]:  # skip first (empty) header
        name = clean(cell.get_text(" ", strip=True))
        if name and is_valid_chip_name(name):
            chip_names.append(name)

    # Data rows
    for name in chip_names:
        chip_id = slug(name)
        chip = {
            "id": chip_id,
            "name": name,
            "vendor": "?",
            "cores": 8,
            "architecture": "ARMv8.2-A",
        }
        # Find which column this chip is in
        for ci, cell in enumerate(header_cells[1:], 1):
            cn = clean(cell.get_text(" ", strip=True))
            if cn == name:
                # Extract data from this column across all rows
                for row in rows[1:]:
                    cells = row.find_all(["th", "td"])
                    if ci < len(cells):
                        cell_text = clean(cells[ci].get_text(" ", strip=True)) or ""
                        row_label = clean(cells[0].get_text(" ", strip=True)) or ""
                        if "CPU" in row_label and "cores" not in chip and "arch" not in chip:
                            cores, arch = extract_cores_and_arch(cell_text)
                            if cores:
                                chip["cores"] = cores
                            if arch:
                                chip["architecture"] = arch
                        if "GPU" in row_label and "gpu" not in chip:
                            chip["gpu"] = cell_text[:80]
                        if "process" in row_label.lower() or "fab" in row_label.lower():
                            proc = extract_process(cell_text)
                            if proc:
                                chip["process"] = proc
                        if "freq" in row_label.lower() or "clock" in row_label.lower() or "speed" in row_label.lower():
                            freq = extract_freq(cell_text)
                            if freq:
                                chip["max_freq"] = freq
                break

        if "year" not in chip:
            ym = re.search(r'(20\d\d)', section_heading)
            if ym:
                chip["year"] = int(ym.group(1))

        chips.append(chip)

    return chips


def scrape_vendor(vendor: str) -> list[dict]:
    url = WIKI_PAGES.get(vendor)
    if not url:
        return []

    print(f"  Fetching {url}")
    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")

    # Find all wikitables
    tables = soup.find_all("table", class_="wikitable")
    if not tables:
        tables = soup.find_all("table")
        # Filter to only tables with th elements (data tables, not layout)
        tables = [t for t in tables if t.find("th")]

    all_chips = []
    seen_ids = set()
    is_amlogic = vendor == "Amlogic"

    for tbl in tables:
        # Skip non-chip sections
        prev = tbl.find_previous(["h2", "h3", "h4"])
        heading = prev.get_text(" ", strip=True) if prev else ""
        hl = heading.lower()
        if any(kw in hl for kw in SKIP_SECTIONS):
            continue

        # Determine chip name override from section heading (e.g., "Tegra 3")
        chip_override = None
        if vendor == "Nvidia":
            m = re.search(r'(Tegra\s+\d+\w*)', heading, re.IGNORECASE)
            if m:
                chip_override = m.group(1)

        if vendor == "NXP i.MX":
            m = re.search(r'(i\.MX[\s-]*\d[\w]*)', heading, re.IGNORECASE)
            if m:
                chip_override = m.group(1).replace("-", " ")

        if vendor == "Intel Atom":
            m = re.search(r'Atom\s+\w+', heading)
            if m:
                chip_override = f"Atom {m.group(0)}"

        # Parse table
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
        url = WIKI_PAGES[vendor]
        if not url:
            print(f"Skipping {vendor} (no Wikipedia URL)")
            continue
        print(f"\n--- {vendor} ---")
        chips = scrape_vendor(vendor)
        if chips:
            write_vendor_file(vendor, chips)
        print(f"  Total: {len(chips)} chips")


if __name__ == "__main__":
    main()
