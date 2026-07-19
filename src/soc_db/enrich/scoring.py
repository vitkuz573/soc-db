"""Completeness scoring for chip records.

Functions:
    compute_completeness: Calculate the completeness score for a chip.
"""

from __future__ import annotations

from typing import Any

from soc_db.enrich._helpers import _has
from soc_db.enrich._vendor_data import FIELD_GROUPS, FIELD_WEIGHTS
from soc_db.provenance import apply_provenance


def compute_completeness(chip: dict[str, Any]) -> dict[str, Any]:
    """Calculate the completeness score for a chip record.

    Uses weighted fill ratio of ``FIELD_GROUPS`` entries. Also ensures
    ``sources``, ``updated``, and ``provenance`` metadata are set.

    Mutates *chip* in-place and returns it.

    Args:
        chip: The chip record.

    Returns:
        The same chip dict with ``completeness``, ``sources``,
        ``updated``, and ``provenance`` set.
    """
    w_total = sum(FIELD_WEIGHTS.get(f, 1) for _, flist in FIELD_GROUPS.items() for f in flist)
    w_filled = sum(FIELD_WEIGHTS.get(f, 1) for _, flist in FIELD_GROUPS.items() for f in flist if _has(chip, f))
    chip["completeness"] = round(w_filled / max(w_total, 1), 4)
    if not chip.get("sources"):
        chip["sources"] = {}
    chip["updated"] = "2026-06-21"
    if not chip.get("provenance"):
        apply_provenance(chip)
    return chip
