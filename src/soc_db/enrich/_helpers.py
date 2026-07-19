"""Internal helper functions used across enrichment modules.

Functions:
    _has: Check whether a chip dict has a non-empty value for a field.
    clean: Strip HTML tags, references, and extra whitespace from a string.
"""

from __future__ import annotations

import re
from typing import Any


def _has(chip: dict[str, Any], field: str) -> bool:
    """Check whether a chip dict has a non-empty value for *field*.

    Considers ``None``, ``""``, ``[]``, ``0``, and ``0.0`` as empty.

    Args:
        chip: The chip record.
        field: The key to check.

    Returns:
        True if the field is present and non-empty.
    """
    v = chip.get(field)
    return v is not None and v != "" and v != [] and v != 0 and v != 0.0


def clean(text: str | None) -> str | None:
    """Strip HTML tags, references, and extra whitespace from a string.

    Removes HTML tags, bracketed annotations like ``[citation]``,
    normalises whitespace, and strips ``(now ...)`` suffixes.

    Args:
        text: The raw input string.

    Returns:
        The cleaned string, or None if the input was empty.
    """
    if not isinstance(text, str):
        return None
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\[\s*\w+\s*\]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s*\(now\s+[^)]*?\)", "", text)
    return text or None
