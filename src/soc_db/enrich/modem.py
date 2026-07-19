"""Modem inference per vendor and year.

Functions:
    infer_modem: Infer modem for a chip.
"""

from __future__ import annotations

import re
from typing import Any

from soc_db.enrich._vendor_data import VENDOR_KNOWLEDGE


def infer_modem(chip: dict[str, Any]) -> dict[str, Any]:
    """Infer the modem for a chip based on vendor and year.

    Covers Qualcomm Snapdragon X-series, MediaTek Dimensity/MT,
    Samsung Exynos, Apple, and HiSilicon Kirin.

    Mutates *chip* in-place and returns it.

    Args:
        chip: The chip record.

    Returns:
        The same chip dict with ``modem`` set if inferred.
    """
    if not chip.get("modem") and chip.get("year"):
        vendor = chip.get("vendor", "")
        model_u = chip.get("model", "").upper()
        name_u = chip.get("name", "").upper()
        yr = chip["year"]
        if vendor == "Qualcomm":
            sm_match = re.search(r"(SM|SDM)(\d{4})", model_u)
            if sm_match:
                sm_num = int(sm_match.group(2))
                modem_map = {8750: "X80", 8650: "X75", 8550: "X70", 8450: "X65", 8350: "X60", 8250: "X55", 8150: "X50", 8000: "X24"}
                for num, modem_name in modem_map.items():
                    if sm_num >= num:
                        chip["modem"] = f"Snapdragon {modem_name} 5G"
                        break
            gen_match = re.search(r"SNAPDRAGON\s*(\d+)\s*GEN\s*(\d+)", model_u)
            if gen_match and not chip.get("modem"):
                gen_num = int(gen_match.group(2))
                if int(gen_match.group(1)) >= 8:
                    modem_by_gen = {3: "X70", 2: "X65", 1: "X60"}
                    if gen_num in modem_by_gen:
                        chip["modem"] = f"Snapdragon {modem_by_gen[gen_num]} 5G"
            if not chip.get("modem") and chip["year"] >= 2019:
                chip["modem"] = "Snapdragon 5G"
            elif not chip.get("modem") and chip["year"] >= 2013:
                chip["modem"] = "Snapdragon 4G LTE"
        elif vendor == "MediaTek":
            if re.search(r"DIMENSITY", model_u) or re.search(r"MT\d{4}", model_u):
                if chip["year"] >= 2020:
                    chip["modem"] = "MediaTek 5G"
                elif chip["year"] >= 2015:
                    chip["modem"] = "MediaTek 4G LTE"
        elif vendor == "Samsung" and re.search(r"EXYNOS", model_u):
            if chip["year"] >= 2020:
                chip["modem"] = "Exynos 5G"
            elif chip["year"] >= 2014:
                chip["modem"] = "Exynos 4G LTE"
        elif vendor == "Apple" and chip["year"] >= 2019:
            chip["modem"] = "Apple 5G"
        elif vendor == "HiSilicon" and re.search(r"KIRIN", model_u):
            if chip["year"] >= 2019:
                chip["modem"] = "Balong 5G"
            elif chip["year"] >= 2014:
                chip["modem"] = "Balong 4G LTE"
    return chip
