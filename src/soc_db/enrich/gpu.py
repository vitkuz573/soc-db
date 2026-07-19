"""GPU inference from vendor knowledge and vendor defaults.

Functions:
    infer_gpu: Infer GPU for a chip.
"""

from __future__ import annotations

from typing import Any

from soc_db.enrich._vendor_data import VENDOR_KNOWLEDGE


def infer_gpu(chip: dict[str, Any]) -> dict[str, Any]:
    """Infer the GPU for a chip.

    Two-pass approach:
    1. Check ``VENDOR_KNOWLEDGE.gpu_map`` by model prefix (pre-year).
    2. If still unset, use vendor/year-based defaults.

    Mutates *chip* in-place and returns it.

    Args:
        chip: The chip record.

    Returns:
        The same chip dict with ``gpu`` set if inferred.
    """
    model_upper = chip.get("model", "").upper()
    vk = VENDOR_KNOWLEDGE.get(chip.get("vendor", ""), {})

    # First pass: model-based lookup (runs before year inference)
    if not chip.get("gpu") and vk.get("gpu_map"):
        for key, gpu_name in vk["gpu_map"].items():
            if key.upper() in model_upper:
                chip["gpu"] = gpu_name
                return chip

    # Second pass: vendor defaults (runs after year inference)
    if not chip.get("gpu") and chip.get("year"):
        vendor = chip.get("vendor", "")
        yr = chip["year"]
        gpu_by_vendor = {
            "Allwinner": "Mali-400 MP" if yr < 2015 else "Mali-450 MP",
            "Amlogic": "Mali-450 MP" if yr < 2017 else "Mali-G31 MP2",
            "Rockchip": "Mali-400 MP" if yr < 2014 else "Mali-T760 MP4" if yr < 2017 else "Mali-G52 MP2",
            "Nvidia": "Nvidia GPU",
            "Intel Atom": "Intel HD Graphics",
            "TI OMAP": "PowerVR SGX",
            "Ingenic": "GC400" if yr < 2014 else "GC800",
            "Actions": "Mali-400 MP",
        }
        if vendor in gpu_by_vendor:
            chip["gpu"] = gpu_by_vendor[vendor]
        elif vendor == "MediaTek":
            chip["gpu"] = "Mali GPU"
        elif vendor == "Qualcomm":
            chip["gpu"] = "Adreno GPU"
        elif vendor == "Samsung" or vendor == "HiSilicon" or vendor == "Unisoc":
            chip["gpu"] = "Mali GPU"
        elif vendor == "NXP i.MX":
            chip["gpu"] = "Vivante GC"
        elif vendor == "Xilinx":
            chip["gpu"] = "Mali GPU"

    return chip
