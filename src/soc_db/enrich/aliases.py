"""Codename alias generation from chip model.

Functions:
    infer_aliases: Generate codename aliases for a chip.
"""

from __future__ import annotations

from typing import Any


def infer_aliases(chip: dict[str, Any]) -> dict[str, Any]:
    """Generate codename aliases for a chip.

    Creates a combined ``Name (Model)`` alias and checks known
    Qualcomm SM codenames.

    Mutates *chip* in-place and returns it.

    Args:
        chip: The chip record.

    Returns:
        The same chip dict with ``aliases`` set if inferred.
    """
    if not chip.get("aliases"):
        aliases: set[str] = set()
        name = chip.get("name", "")
        model = chip.get("model", "")
        model_upper = model.upper()
        if name and model and model not in name:
            aliases.add(f"{name} ({model})")
        codenames = {
            "SM8250": ["Kona"],
            "SM8350": ["Lahaina"],
            "SM8450": ["Waipio"],
            "SM8475": ["Waipio"],
            "SM8550": ["Kalama"],
            "SM8650": ["Pineapple"],
            "SM8750": ["Pineapple"],
        }
        for key, alist in codenames.items():
            if key.upper() in model_upper:
                for a in alist:
                    aliases.add(a)
        if aliases:
            chip["aliases"] = sorted(aliases)
    return chip
