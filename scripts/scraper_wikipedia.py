#!/usr/bin/env python3
"""Generic scraper for SoC Wikipedia pages with wikitable parsing."""

import re
import sys
from bs4 import BeautifulSoup
from common import fetch, clean, extract_int, extract_freq, extract_process, slug, write_vendor_file

WIKI_PAGES = {
    "Qualcomm": "https://en.wikipedia.org/wiki/List_of_Qualcomm_Snapdragon_processors",
    "MediaTek": "https://en.wikipedia.org/wiki/List_of_MediaTek_processors",
    "Samsung": "https://en.wikipedia.org/wiki/Exynos",
    "HiSilicon": "https://en.wikipedia.org/wiki/HiSilicon",
    "Google": "https://en.wikipedia.org/wiki/Google_Tensor",
    "Apple": "https://en.wikipedia.org/wiki/Apple_silicon",
}


def extract_chip_name(text: str) -> str | None:
    """Extract clean chip name from table cell text."""
    text = re.sub(r"\s*\[.*?\]\s*", " ", text).strip()
    if not text or text == "?":
        return None

    # Remove leading/trailing parentheses content if it's a footnote
    text = re.sub(r'\(.*?\)\s*$', '', text).strip()

    # Models and known prefixes
    known_prefixes = (
        "Snapdragon", "Dimensity", "Helio", "Kompanio", "Pentonic",
        "Exynos", "Kirin", "Tensor", "Apple ",
        "SM", "SDM", "MSM", "APQ", "MT", "SC", "QCS",
        "M1", "M2", "M3", "M4",
    )

    for prefix in known_prefixes:
        if text.startswith(prefix):
            return text.split("[")[0].strip()

    return text.split("[")[0].strip()[:60]


def is_valid_chip_name(name: str) -> bool:
    """Filter out junk rows."""
    if not name or name in ("?", "", "-", "—"):
        return False
    if re.match(r'^\d+[\s.]', name):
        return False
    if not re.search(r'[a-zA-Z]', name):
        return False
    if len(name) < 3:
        return False
    if re.match(r'^[\d+]+[xX]\s*', name):
        return False
    # Must have a digit or be a known SoC name
    if not re.search(r'\d', name) and not any(kw in name.lower()
          for kw in ("snapdragon", "dimensity", "helio", "exynos", "kirin",
                     "tensor", "apple", "m1", "m2", "m3", "m4", "qualcomm",
                     "mediatek", "samsung", "pentonic", "kompanio")):
        return False
    # Skip known non-chip names
    if name.lower() in ("armv7", "armv8", "armv9", "android", "linux", "windows"):
        return False
    if re.match(r'^ARMv\d', name, re.IGNORECASE):
        return False
    return True


def extract_model(text: str) -> str | None:
    """Extract model number. Supports various vendor formats."""
    patterns = [
        r'\b(SM\d{3,}|SDM\d{3,}|MSM\d{3,}|APQ\d{3,}|SC\d{4}|QCS\d{3})\b',
        r'\b(MT\d{4,})\b',
        r'\b(Exynos\s*\d{4,})\b',
        r'\b(Kirin\s*\d{3,})\b',
        r'\b(GS\d{3})\b',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).upper()
    return None


def extract_cores_and_arch(text: str) -> tuple[int | None, str | None]:
    """Parse CPU cell for cores count and architecture."""
    cores = None
    arch = None
    if not text:
        return cores, arch

    if "ARMv9" in text or "v9" in text:
        arch = "ARMv9-A"
    elif "ARMv8" in text or "v8" in text:
        arch = "ARMv8.2-A"
    elif "ARMv7" in text:
        arch = "ARMv7-A"

    # Cores pattern
    m = re.search(r'(\d+)\s*(?:x\s*|core|cores?|\-core)', text, re.IGNORECASE)
    if m:
        cores = int(m.group(1))
    else:
        # Sum up cluster sizes: "1+3+4" or "2+6" etc.
        clusters = re.findall(r'(\d+)\s*\+', text)
        if clusters:
            cores = sum(int(c) for c in clusters) + int(clusters[0])
        else:
            ci = extract_int(text)
            if ci and ci <= 16:
                cores = ci

    return cores, arch


def scrape_vendor(vendor: str) -> list[dict]:
    """Scrape SoC data for a given vendor from their Wikipedia page."""
    url = WIKI_PAGES.get(vendor)
    if not url:
        print(f"  No Wikipedia URL for {vendor}")
        return []

    print(f"  Fetching {url}")
    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table", class_="wikitable")

    all_chips = []
    seen_ids = set()

    for tbl in tables:
        rows = tbl.find_all("tr")
        data_rows = [tr for tr in rows if tr.find_all("td")]
        if not data_rows:
            continue

        # Get section heading
        prev = tbl.find_previous(["h2", "h3", "h4"])
        heading = prev.get_text(" ", strip=True) if prev else ""
        hl = heading.lower()

        # Skip non-chip sections
        if any(kw in hl for kw in ("features of", "comparison", "acronym", "bluetooth")):
            continue

        # Determine year from heading
        section_year = None
        ym = re.search(r'(20\d\d)', heading)
        if ym:
            section_year = int(ym.group(1))

        for tr in data_rows:
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue

            # First cell usually has the chip name
            name_raw = clean(tds[0].get_text(" ", strip=True))
            if not name_raw:
                continue

            chip_name = extract_chip_name(name_raw)
            if not chip_name or not is_valid_chip_name(chip_name):
                continue

            chip_id = slug(chip_name)
            if chip_id in seen_ids:
                continue
            seen_ids.add(chip_id)

            chip = {
                "id": chip_id,
                "name": chip_name,
                "vendor": vendor,
            }

            # Model number from first couple of cells
            model = extract_model(tds[0].get_text(" ", strip=True))
            if not model and len(tds) > 1:
                model = extract_model(tds[1].get_text(" ", strip=True))
            if model:
                chip["model"] = model

            # Try to find process, cores, GPU from other cells
            for i, td in enumerate(tds[1:], 1):
                cell_text = clean(td.get_text(" ", strip=True)) or ""

                # Process node
                if "process" not in chip:
                    proc = extract_process(cell_text)
                    if proc:
                        chip["process"] = proc

                # Cores + arch
                if "cores" not in chip:
                    cores_text = cell_text
                    cores, arch = extract_cores_and_arch(cores_text)
                    if cores:
                        chip["cores"] = cores
                    if arch:
                        chip["architecture"] = arch

                # GPU
                if "gpu" not in chip:
                    if any(kw in cell_text.lower() for kw in ("adreno", "mali", "xclipse", "apple", "gpu")):
                        chip["gpu"] = cell_text[:60]

                # Frequency
                if "max_freq" not in chip:
                    freq = extract_freq(cell_text)
                    if freq:
                        chip["max_freq"] = freq

                # Year
                if "year" not in chip and section_year:
                    chip["year"] = section_year

            chip.setdefault("cores", 8)
            chip.setdefault("architecture", "ARMv8.2-A")

            all_chips.append(chip)

    return all_chips


def main():
    vendors = sys.argv[1:] if len(sys.argv) > 1 else list(WIKI_PAGES.keys())
    for vendor in vendors:
        if vendor not in WIKI_PAGES:
            print(f"Unknown vendor: {vendor}. Available: {list(WIKI_PAGES.keys())}")
            continue
        print(f"\n--- {vendor} ---")
        chips = scrape_vendor(vendor)
        if chips:
            write_vendor_file(vendor, chips)
        print(f"  Total: {len(chips)} chips")


if __name__ == "__main__":
    main()
