"""CPU / architecture inference from vendor knowledge.

Functions:
    infer_cpu: Infer CPU architecture for a chip.
"""

from __future__ import annotations

from typing import Any

from soc_db.enrich._vendor_data import VENDOR_KNOWLEDGE


def infer_cpu(chip: dict[str, Any]) -> dict[str, Any]:
    """Infer the CPU architecture for a chip from vendor knowledge.

    Looks up ``VENDOR_KNOWLEDGE`` for the chip's vendor and sets
    ``architecture`` if a default is known.

    Mutates *chip* in-place and returns it.

    Args:
        chip: The chip record.

    Returns:
        The same chip dict with ``architecture`` set if inferred.
    """
    if not chip.get("architecture"):
        vk = VENDOR_KNOWLEDGE.get(chip.get("vendor", ""), {})
        if vk.get("architecture"):
            chip["architecture"] = vk["architecture"]
    return chip
