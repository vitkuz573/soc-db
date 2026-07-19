"""Storage type inference from year.

Functions:
    infer_storage: Infer storage type from chip year.
"""

from __future__ import annotations

from typing import Any


def infer_storage(chip: dict[str, Any]) -> dict[str, Any]:
    """Infer the storage interface type from the chip's release year.

    Mutates *chip* in-place and returns it.

    Args:
        chip: The chip record.

    Returns:
        The same chip dict with ``storage_type`` set if inferred.
    """
    yr = chip.get("year")
    if not chip.get("storage_type") and yr:
        st_by_year = [
            (2021, "UFS 3.1"),
            (2019, "UFS 3.0"),
            (2017, "UFS 2.1"),
            (2015, "UFS 2.0"),
            (0, "eMMC 5.0"),
        ]
        for yr_st, st_name in st_by_year:
            if yr >= yr_st:
                chip["storage_type"] = st_name
                break
    return chip
