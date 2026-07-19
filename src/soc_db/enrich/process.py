"""Process node inference from vendor knowledge and year-based fallback.

Functions:
    infer_process: Infer process node for a chip.
"""

from __future__ import annotations

from typing import Any

from soc_db.enrich._vendor_data import VENDOR_KNOWLEDGE


def infer_process(chip: dict[str, Any]) -> dict[str, Any]:
    """Infer the fabrication process node for a chip.

    Two-pass approach:
    1. Check ``VENDOR_KNOWLEDGE.process_map`` by model prefix.
    2. If still unset, use a year-based threshold table.

    Mutates *chip* in-place and returns it.

    Args:
        chip: The chip record.

    Returns:
        The same chip dict with ``process_nm`` and ``process_name`` set if inferred.
    """
    model_upper = chip.get("model", "").upper()
    vk = VENDOR_KNOWLEDGE.get(chip.get("vendor", ""), {})

    # First pass: model-based lookup
    if not chip.get("process_nm") and vk.get("process_map"):
        for key, nm in vk["process_map"].items():
            if key.upper() in model_upper:
                chip["process_nm"] = nm
                chip["process_name"] = f"{nm}nm"
                break

    # Second pass: year-based fallback
    yr = chip.get("year")
    if not chip.get("process_nm") and yr:
        proc_by_year = [
            (2024, 3),
            (2023, 4),
            (2021, 5),
            (2019, 7),
            (2017, 10),
            (2015, 14),
            (2013, 20),
            (2011, 28),
            (2009, 40),
            (0, 65),
        ]
        for yr_proc, nm in proc_by_year:
            if yr >= yr_proc:
                chip["process_nm"] = nm
                chip["process_name"] = f"{nm}nm"
                break
    return chip
