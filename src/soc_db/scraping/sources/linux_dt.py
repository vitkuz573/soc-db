"""LinuxDTScraper — BaseScraper implementation for Linux Device Tree sources.

Uses the GitHub API to recursively list DTS files from the Linux kernel
tree, extracts SoC model numbers from DTS filenames, and produces chip
records with vendor+model identity.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from typing import Any

from soc_db.common import slug
from soc_db.scraping.base import BaseScraper, ChipScrapeResult
from soc_db.scraping.source import HTTPSource

logger = logging.getLogger(__name__)

# Architecture → DT path
ARCH_PATHS: list[tuple[str, str]] = [
    ("arm64", "arch/arm64/boot/dts"),
    ("arm", "arch/arm/boot/dts"),
]

# Vendor directory name → our vendor name
VENDOR_MAP: dict[str, str] = {
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

# Known ARM 32-bit vendor dirs whose arm64 counterparts are preferred
ARM32_VENDOR_DIRS: set[str] = {
    "broadcom", "marvell", "st", "renesas", "sprd", "realtek",
    "ti", "microchip", "xilinx", "actions", "nxp", "imx",
}

# Regex for extracting SoC model number from DTS filename per vendor
VENDOR_SOC_PATTERNS: dict[str, str] = {
    "Qualcomm": r"^(s[dm]\w*|msm\w+|apq\w+|ipq\w+)",
    "MediaTek": r"^(mt\d+)",
    "Samsung": r"^(exynos\d+)",
    "HiSilicon": r"^(hi\d+)",
    "Apple": r"^(t?\d+)",
    "Rockchip": r"^(rk\d+)",
    "Allwinner": r"^(sun\d+)",
    "Amlogic": r"^(meson\d+)",
    "Nvidia": r"^(tegra\d+)",
    "TI OMAP": r"^(omap\d+|am\d+|dra\d+|k3-\w+|dm\d+)",
    "Intel Atom": r"^(atom\w+)",
    "Ingenic": r"^(jz\d+|xburst\w+)",
    "NXP i.MX": r"^(imx\d+)",
    "Unisoc": r"^(sc\d+|sp\d+|ums\d+)",
    "Realtek": r"^(rtd\d+)",
    "Broadcom": r"^(bcm\d+|cygnus|hr2|nsp|ns2)",
    "Marvell": r"^(armada-\d+|dove|kirkwood|orion5x|pxa\d+|mmp\d+|berlin|ac5|cn\d+|ac5x)",
    "Renesas": r"^(r[78w]\w+|emev\d+)",
    "STMicroelectronics": r"^(stm32mp\d+|stih\d+|spear\d+|u[0-9]+)",
    "Microchip": r"^(lan\d+|sparx\d+|sam\d+|sama\d+|at91\d+)",
    "Xilinx": r"^(zynq\w+|versal\w+)",
    "Actions": r"^(s\d+|owl-s\d+)",
    "SigmaStar": r"^(ssd\d+|msc\d+)",
    "VIA WonderMedia": r"^(vt\d+|wm\d+)",
    "Cirrus Logic": r"^(ep\d+)",
}


class LinuxDTScraper(BaseScraper):
    """Scraper for SoC identifiers from the Linux kernel Device Tree.

    Fetches the full DTS file tree from the Linux GitHub repo, extracts
    model numbers from filenames, and produces basic chip records for
    the enrichment pipeline.
    """

    SOURCE_ID = "linux_dt"
    VENDORS = list({v for v in VENDOR_MAP.values()})
    PRIORITY = 60

    RATE_LIMIT_CONFIG: dict[str, float | int] = {
        "requests_per_sec": 1.0,
        "burst": 1,
        "backoff_factor": 2.0,
        "max_retries": 3,
    }

    def __init__(self, robots_checker=None, rate_limiter=None) -> None:
        super().__init__(robots_checker, rate_limiter)
        self._http = HTTPSource(rate_limiter=self._rate_limiter)
        self._git_tree: list[dict[str, Any]] = []

    # ── fetch ───────────────────────────────────────────────────────────

    def fetch(self) -> list[dict[str, Any]]:
        """Fetch the full Linux kernel git tree via GitHub API.

        Returns:
            List of tree entry dicts with ``path``, ``type``, ``mode``.
        """
        github_url = "https://api.github.com/repos/torvalds/linux/git/trees/master?recursive=1"
        self.check_robots(github_url)
        raw = self._http.fetch(github_url, user_agent=self.user_agent)
        data = json.loads(raw)
        self._git_tree = data.get("tree", [])
        logger.info("[LinuxDTScraper] Fetched %d tree entries", len(self._git_tree))
        return self._git_tree

    # ── parse ───────────────────────────────────────────────────────────

    def parse(self, tree: list[dict[str, Any]]) -> list[ChipScrapeResult]:
        """Parse git tree entries into ChipScrapeResults.

        Args:
            tree: List of tree entries from the GitHub API.

        Returns:
            List of parsed chip results.
        """
        results: list[ChipScrapeResult] = []
        seen_models: dict[str, set[str]] = defaultdict(set)

        for entry in tree:
            path = entry.get("path", "")
            if not (path.endswith(".dts") or path.endswith(".dtsi")):
                continue

            m = re.match(r"arch/(arm64|arm)/boot/dts/([^/]+)/", path)
            if not m:
                continue

            arch, vendor_dir = m.group(1), m.group(2)
            vendor_name = VENDOR_MAP.get(vendor_dir)
            if not vendor_name:
                continue

            # Skip arm/ directory if arm64 already handles this vendor
            if arch == "arm" and vendor_dir in ARM32_VENDOR_DIRS:
                continue

            filename = path.split("/")[-1]
            soc_model = dts_to_soc_name(filename, vendor_dir, vendor_name)
            if not soc_model:
                continue

            # Deduplicate within parse (same vendor+model combinations)
            model_key = soc_model.upper()
            if model_key in seen_models.get(vendor_name, set()):
                continue
            seen_models[vendor_name].add(model_key)

            marketing = dts_to_marketing_name(soc_model, vendor_name)
            chip_id = slug(soc_model)

            chip = {
                "id": chip_id,
                "name": marketing,
                "vendor": vendor_name,
                "model": model_key,
                "source": "linux_dt",
            }

            results.append(
                ChipScrapeResult(
                    name=marketing,
                    vendor=vendor_name,
                    model=model_key,
                    fields=dict(chip),
                    source_id=self.SOURCE_ID,
                )
            )

        logger.info("[LinuxDTScraper] Parsed %d unique chip(s)", len(results))
        return results


# ── helper functions ──────────────────────────────────────────────────


def dts_to_soc_name(filename: str, vendor_dir: str, vendor_name: str) -> str | None:
    """Extract the SoC model number from a DTS filename.

    Examples:
        ``"bcm2711-rpi-4-b.dts"`` → ``"BCM2711"``
        ``"imx6q-sabresd.dts"``   → ``"i.MX6Q"``
        ``"armada-3720-db.dts"``  → ``"Armada 3720"``
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
