"""NPU / AI accelerator inference per vendor and year.

Functions:
    infer_npu: Infer NPU for a chip.
"""

from __future__ import annotations

import re
from typing import Any

from soc_db.enrich._vendor_data import VENDOR_KNOWLEDGE


def infer_npu(chip: dict[str, Any]) -> dict[str, Any]:
    """Infer the NPU / AI accelerator for a chip based on vendor and year.

    Covers Apple Neural Engine, Qualcomm Hexagon NPU, MediaTek APU,
    Samsung NPU, and HiSilicon NPU.

    Mutates *chip* in-place and returns it.

    Args:
        chip: The chip record.

    Returns:
        The same chip dict with ``npu`` set if inferred.
    """
    yr = chip.get("year")
    if not chip.get("npu") and yr and yr >= 2017:
        vendor = chip.get("vendor", "")
        model_u = chip.get("model", "").upper()
        name_u = chip.get("name", "").upper()
        vk = VENDOR_KNOWLEDGE.get(vendor, {})
        vk_npu = vk.get("npu_map", {})
        if not vk_npu:
            if vendor == "Apple" and chip["year"] >= 2017:
                chip["npu"] = "Neural Engine"
            elif vendor == "Qualcomm":
                if any(x in model_u for x in ("SM8", "SM7", "SDM8", "SDM7")) or any(x in model_u for x in ("SM6", "SDM6")):
                    chip["npu"] = "Hexagon NPU"
            elif vendor == "MediaTek":
                if "DIMENSITY" in model_u or "DIMENSITY" in name_u:
                    chip["npu"] = "MediaTek APU"
                elif re.search(r"MT\d{4}", model_u):
                    mt_m = re.search(r"MT(\d{4})", model_u)
                    if mt_m and int(mt_m.group(1)) >= 8000:
                        chip["npu"] = "MediaTek APU"
            elif vendor == "Samsung" and re.search(r"EXYNOS\s*(21|22|24|25)", model_u):
                chip["npu"] = "Samsung NPU"
            elif vendor == "HiSilicon" and re.search(r"KIRIN\s*(9|8|7)", model_u):
                chip["npu"] = "HiSilicon NPU"
    return chip
