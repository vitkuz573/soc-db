#!/usr/bin/env python3
"""Linux Kernel Device Tree Scraper.

Extracts SoC model numbers from Linux kernel DTS file listings.
Uses GitHub API to recursively list all DTS files in a vendor directory.
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from urllib.request import urlopen, Request

from common import slug, write_vendor_file, DATA_DIR

# Architecture → DT path
ARCH_PATHS = [
    ("arm64", "arch/arm64/boot/dts"),
    ("arm", "arch/arm/boot/dts"),
]

# Vendor directory name → our vendor name
VENDOR_MAP = {
    "qcom": "Qualcomm",
    "mediatek": "MediaTek",
    "exynos": "Samsung",
    "samsung": "Samsung",
    "hisilicon": "HiSilicon",
    "apple": "Apple",
    "rockchip": "Rockchip",
    "allwinner": "Allwinner",
    "sunxi": "Allwinner",
    "amlogic": "Amlogic",
    "meson": "Amlogic",
    "nvidia": "Nvidia",
    "tegra": "Nvidia",
    "ti": "TI OMAP",
    "omap": "TI OMAP",
    "intel": "Intel Atom",
    "ingenic": "Ingenic",
    "nxp": "NXP i.MX",
    "freescale": "NXP i.MX",
    "imx": "NXP i.MX",
    "sprd": "Unisoc",
    "realtek": "Realtek",
    "realtek": "Realtek",
    "broadcom": "Broadcom",
    "brcm": "Broadcom",
    "marvell": "Marvell",
    "mvebu": "Marvell",
    "renesas": "Renesas",
    "rcar": "Renesas",
    "rza1": "Renesas",
    "rza2": "Renesas",
    "rzg1": "Renesas",
    "rzg2": "Renesas",
    "st": "STMicroelectronics",
    "sti": "STMicroelectronics",
    "stm32": "STMicroelectronics",
    "microchip": "Microchip",
    "atmel": "Microchip",
    "xilinx": "Xilinx",
    "zynq": "Xilinx",
    "actions": "Actions",
    "owl": "Actions",
    "airoha": "Airoha",
    "amazon": "Amazon",
    "altera": "Altera",
    "amd": "AMD",
    "apm": "APM",
    "aspeed": "ASPEED",
    "bitmain": "Bitmain",
    "cavium": "Cavium",
    "socionext": "Socionext",
    "sophgo": "Sophgo",
    "synaptics": "Synaptics",
    "tesla": "Tesla",
    "toshiba": "Toshiba",
    "nuvoton": "Nuvoton",
    "sigmastar": "SigmaStar",
    "vt8500": "VIA WonderMedia",
    "cirrus": "Cirrus Logic",
}

# Known ARM 32-bit vendor dirs that moved to subdirs
ARM32_VENDOR_DIRS = {
    "broadcom": True,
    "marvell": True,
    "st": True,
    "renesas": True,
    "sprd": True,
    "realtek": True,
    "ti": True,
    "microchip": True,
    "xilinx": True,
    "actions": True,
    "nxp": True,
    "imx": True,
}

# Regex for extracting SoC model number from DTS filename
# Each vendor has different naming patterns
VENDOR_SOC_PATTERNS = {
    "Qualcomm": r'^(s[dm]\w*|msm\w+|apq\w+|ipq\w+)',
    "MediaTek": r'^(mt\d+)',
    "Samsung": r'^(exynos\d+)',
    "HiSilicon": r'^(hi\d+)',
    "Apple": r'^(t?\d+)',
    "Rockchip": r'^(rk\d+)',
    "Allwinner": r'^(sun\d+)',
    "Amlogic": r'^(meson\d+)',
    "Nvidia": r'^(tegra\d+)',
    "TI OMAP": r'^(omap\d+|am\d+|dra\d+|k3-\w+|dm\d+)',
    "Intel Atom": r'^(atom\w+)',
    "Ingenic": r'^(jz\d+|xburst\w+)',
    "NXP i.MX": r'^(imx\d+)',
    "Unisoc": r'^(sc\d+|sp\d+|ums\d+)',
    "Realtek": r'^(rtd\d+)',
    "Broadcom": r'^(bcm\d+|cygnus|hr2|nsp|ns2)',
    "Marvell": r'^(armada-\d+|dove|kirkwood|orion5x|pxa\d+|mmp\d+|berlin|ac5|cn\d+|ac5x)',
    "Renesas": r'^(r[78w]\w+|emev\d+)',
    "STMicroelectronics": r'^(stm32mp\d+|stih\d+|spear\d+|u[0-9]+)',
    "Microchip": r'^(lan\d+|sparx\d+|sam\d+|sama\d+|at91\d+)',
    "Xilinx": r'^(zynq\w+|versal\w+)',
    "Actions": r'^(s\d+|owl-s\d+)',
    "SigmaStar": r'^(ssd\d+|msc\d+)',
    "VIA WonderMedia": r'^(vt\d+|wm\d+)',
    "Cirrus Logic": r'^(ep\d+)',
}


def fetch_tree(owner="torvalds", repo="linux", recursive=True) -> list:
    """Fetch the full git tree via GitHub API (recursive)."""
    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/master"
    if recursive:
        url += "?recursive=1"
    req = Request(url, headers={
        "User-Agent": "SOC-DB/1.0",
        "Accept": "application/vnd.github.v3+json"
    })
    with urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    return data.get("tree", [])


def dts_to_soc_name(filename: str, vendor_dir: str, vendor_name: str) -> str | None:
    """Extract the SoC model number from a DTS filename.
    
    e.g. "bcm2711-rpi-4-b.dts" -> "BCM2711"
         "imx6q-sabresd.dts" -> "i.MX6Q"
         "armada-3720-db.dts" -> "Armada 3720"
    """
    name = filename.replace(".dts", "").replace(".dtsi", "")
    
    # Use vendor-specific regex if available
    if vendor_name in VENDOR_SOC_PATTERNS:
        m = re.search(VENDOR_SOC_PATTERNS[vendor_name], name, re.IGNORECASE)
        if m:
            return m.group(1)
    
    # Generic fallback: take the first alphanumeric segment
    parts = name.split("-")
    if parts:
        return parts[0]
    
    return name


def dts_to_marketing_name(soc_model: str | None, vendor_name: str) -> str:
    """Convert kernel model name to a more readable marketing name."""
    if not soc_model:
        return ""
    
    # Generic mapping for known prefixes
    m = soc_model.upper()
    
    if m.startswith("BCM27"):
        return f"BCM{soc_model[3:]}"
    if m.startswith("BCM283"):
        return f"BCM283{soc_model[6:]}"
    if m.startswith("MT") and len(m) > 2:
        return f"MediaTek {m.upper()}"
    if m.startswith("SDM") or m.startswith("SM"):
        return f"Snapdragon {m.upper()}"
    if m.startswith("SC") or m.startswith("SP") or m.startswith("UMS"):
        return f"Unisoc {m.upper()}"
    if m.startswith("RK"):
        return f"Rockchip {m.upper()}"
    if m.startswith("SUN") or m.startswith("SUNXI"):
        return f"Allwinner {m.capitalize()}"
    if m.startswith("IMX"):
        return f"i.MX{m[3:].upper()}"
    if m.startswith("R8A") or m.startswith("R7S"):
        return f"Renesas {m.upper()}"
    if m.startswith("ARMADA"):
        return f"Marvell {m.capitalize().replace('-', ' ')}"
    if m.startswith("STM32"):
        return f"STM32{m[5:].upper()}"
    if m.startswith("AM") or m.startswith("DRA") or m.startswith("OMAP") or m.startswith("K3-"):
        return f"TI {m.upper().replace('-', ' ')}"
    if m.startswith("RTD"):
        return f"Realtek {m.upper()}"
    
    return soc_model


def deduplicate_chips(chips: list[dict]) -> list[dict]:
    """Remove duplicate model numbers, keeping first occurrence."""
    seen = set()
    result = []
    for c in chips:
        key = c.get("model", c["id"])
        if key not in seen:
            seen.add(key)
            result.append(c)
    return result


def scrape(tree: list) -> dict[str, list[dict]]:
    """Main scraping function."""
    vendor_chips: dict[str, list[dict]] = defaultdict(list)
    
    for entry in tree:
        path = entry.get("path", "")
        if not (path.endswith(".dts") or path.endswith(".dtsi")):
            continue
        
        m = re.match(r"arch/(arm64|arm)/boot/dts/([^/]+)/", path)
        if not m:
            continue
        
        # Try arm64 first, then arm directory
        arch, vendor_dir = m.group(1), m.group(2)
        vendor_name = VENDOR_MAP.get(vendor_dir)
        if not vendor_name:
            continue
        
        # Skip arm/ directory if arm64 already handled this vendor
        # (arm64 data is more relevant for modern SoCs)
        if arch == "arm" and vendor_dir in ARM32_VENDOR_DIRS:
            continue
        
        filename = path.split("/")[-1]
        soc_model = dts_to_soc_name(filename, vendor_dir, vendor_name)
        if not soc_model:
            continue
        
        marketing = dts_to_marketing_name(soc_model, vendor_name)
        
        chip = {
            "id": slug(soc_model),
            "name": marketing,
            "vendor": vendor_name,
            "model": soc_model.upper(),
            "source": "linux_dt",
        }
        
        # Check if we already have this chip model
        existing = [c for c in vendor_chips[vendor_name] if c.get("model") == chip["model"]]
        if not existing:
            vendor_chips[vendor_name].append(chip)
    
    # Deduplicate per vendor
    result = {}
    for vendor, chips in vendor_chips.items():
        result[vendor] = deduplicate_chips(chips)
    
    return result


def main():
    print("=== Linux Kernel Device Tree Scraper ===")
    print()
    print("Fetching kernel tree...", end=" ", flush=True)
    tree = fetch_tree()
    print(f"{len(tree)} entries")
    print()
    
    vendor_chips = scrape(tree)
    
    total = 0
    for vendor, chips in sorted(vendor_chips.items()):
        write_vendor_file(vendor, chips)
        total += len(chips)
        print(f"  {vendor:25s}: {len(chips):5d} chips")
    
    print(f"\n  Total: {total} chips across {len(vendor_chips)} vendors")


if __name__ == "__main__":
    main()
