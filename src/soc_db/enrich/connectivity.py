"""Wi-Fi and Bluetooth version inference from year.

Functions:
    infer_wifi: Infer Wi-Fi standard from chip year.
    infer_bluetooth: Infer Bluetooth version from chip year.
"""

from __future__ import annotations

from typing import Any


def infer_wifi(chip: dict[str, Any]) -> dict[str, Any]:
    """Infer the Wi-Fi standard from the chip's release year.

    Mutates *chip* in-place and returns it.

    Args:
        chip: The chip record.

    Returns:
        The same chip dict with ``wifi`` set if inferred.
    """
    yr = chip.get("year")
    if not chip.get("wifi") and yr:
        wifi_by_year = [
            (2025, "Wi-Fi 7"),
            (2023, "Wi-Fi 7"),
            (2021, "Wi-Fi 6E"),
            (2019, "Wi-Fi 6"),
            (2015, "Wi-Fi 5"),
            (2010, "Wi-Fi 4"),
            (2005, "Wi-Fi 3"),
            (0, "Wi-Fi 2"),
        ]
        for yr_wifi, w_name in wifi_by_year:
            if yr >= yr_wifi:
                chip["wifi"] = w_name
                break
    return chip


def infer_bluetooth(chip: dict[str, Any]) -> dict[str, Any]:
    """Infer the Bluetooth version from the chip's release year.

    Mutates *chip* in-place and returns it.

    Args:
        chip: The chip record.

    Returns:
        The same chip dict with ``bluetooth`` set if inferred.
    """
    yr = chip.get("year")
    if not chip.get("bluetooth") and yr:
        bt_by_year = [
            (2025, "5.4"),
            (2023, "5.3"),
            (2021, "5.2"),
            (2019, "5.0"),
            (2017, "4.2"),
            (2015, "4.1"),
            (2012, "4.0"),
            (2010, "3.0"),
            (2007, "2.1"),
            (0, "2.0"),
        ]
        for yr_bt, b_name in bt_by_year:
            if yr >= yr_bt:
                chip["bluetooth"] = b_name
                break
    return chip
