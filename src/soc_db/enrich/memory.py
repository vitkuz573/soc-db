"""Memory type, clock, and bus inference.

Functions:
    infer_memory: Infer memory type, clock speed, and bus width for a chip.
"""

from __future__ import annotations

from typing import Any

from soc_db.enrich._vendor_data import MEMORY_CLOCK_FROM_TYPE


def infer_memory(chip: dict[str, Any]) -> dict[str, Any]:
    """Infer memory type, clock speed, and bus width for a chip.

    Multi-pass approach:
    1. Infer clock speed from memory type (if type already set).
    2. Infer bus width from memory type (if type already set).
    3. Infer memory type from year (if no type set).
    4. Infer clock speed from memory type (second pass).
    5. Infer bus width from memory type (second pass).

    Mutates *chip* in-place and returns it.

    Args:
        chip: The chip record.

    Returns:
        The same chip dict with ``memory_clock``, ``memory_bus``,
        and/or ``memory_type`` set if inferred.
    """
    # First pass: clock from type
    if not chip.get("memory_clock") and chip.get("memory_type"):
        for mtype, clock in MEMORY_CLOCK_FROM_TYPE.items():
            if mtype in chip["memory_type"].upper():
                chip["memory_clock"] = clock
                break

    # First pass: bus from type
    if not chip.get("memory_bus") and chip.get("memory_type") in ("LPDDR5X", "LPDDR5", "LPDDR4X", "LPDDR4"):
        chip["memory_bus"] = 64

    # Second pass: type from year
    yr = chip.get("year")
    if not chip.get("memory_type") and yr:
        mem_by_year = [
            (2023, "LPDDR5X"),
            (2021, "LPDDR5"),
            (2019, "LPDDR4X"),
            (2016, "LPDDR4"),
            (2014, "LPDDR3"),
            (2012, "LPDDR2"),
            (0, "LPDDR"),
        ]
        for yr_mem, mt_name in mem_by_year:
            if yr >= yr_mem:
                chip["memory_type"] = mt_name
                break

    # Third pass: clock from type (re-check after year-based inference)
    mt = chip.get("memory_type", "")
    if not chip.get("memory_clock") and mt:
        clock_map = {
            "LPDDR6": 6400,
            "LPDDR5X": 4266,
            "LPDDR5": 3200,
            "LPDDR4X": 2133,
            "LPDDR4": 1600,
            "LPDDR3": 933,
            "LPDDR2": 533,
            "LPDDR": 400,
        }
        for k, v in clock_map.items():
            if mt.startswith(k):
                chip["memory_clock"] = v
                break

    # Third pass: bus from type
    if not chip.get("memory_bus") and mt:
        if mt.startswith(("LPDDR4", "LPDDR5", "LPDDR6")):
            chip["memory_bus"] = 64
        elif mt.startswith(("LPDDR3", "LPDDR2", "LPDDR")):
            chip["memory_bus"] = 32

    return chip
