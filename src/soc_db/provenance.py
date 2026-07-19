"""Field-level provenance tracking for chip records.

Every value in a chip record should carry information about *where* it came
from. This module provides:

* :class:`ProvenanceTracker` — records the source identifier for each field
  when a chip dict is constructed or updated.
* :class:`ConflictResolver` — logs disagreements when multiple sources provide
  different values for the same field, without last-writer-wins.
* :func:`apply_provenance` — convenience function that stamps a chip dict with
  a ``provenance`` entry for every non-empty field.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Fields that are never tracked for provenance (system-managed).
_SYSTEM_FIELDS: set[str] = {
    "id",
    "provenance",
    "sources",
    "completeness",
    "updated",
    "rating",
    "benchmarks",
}

_PROVENANCE_LEGACY = "legacy_v2"


class ProvenanceTracker:
    """Records the source identifier for each field on a chip record.

    Usage::

        tracker = ProvenanceTracker()
        chip = {"name": "Snapdragon 8 Gen 2", "cores": 8}
        tracker.record(chip, "wikipedia")
        # chip["provenance"] == {"name": "wikipedia", "cores": "wikipedia"}
    """

    def record(
        self,
        chip: dict[str, Any],
        source_id: str,
        *,
        force: bool = False,
    ) -> dict[str, str]:
        """Stamp *chip* with provenance entries for every present field.

        Args:
            chip: The chip record to annotate (modified in place).
            source_id: The source identifier (e.g. ``"wikipedia"``).
            force: If True, overwrite existing provenance entries.

        Returns:
            The ``provenance`` dict that was written to the chip.
        """
        prov: dict[str, str] = chip.get("provenance") or {}
        for key, value in chip.items():
            if key in _SYSTEM_FIELDS:
                continue
            if value is None or value == "" or value == [] or value == 0 or value == 0.0:
                continue
            if key not in prov or force:
                prov[key] = source_id
        chip["provenance"] = prov
        return prov

    def record_field(
        self,
        chip: dict[str, Any],
        field: str,
        source_id: str,
        *,
        force: bool = False,
    ) -> None:
        """Record provenance for a single field.

        Args:
            chip: The chip record to annotate (modified in place).
            field: The field name.
            source_id: The source identifier.
            force: If True, overwrite existing provenance.
        """
        if field in _SYSTEM_FIELDS:
            return
        prov: dict[str, str] = chip.get("provenance") or {}
        if field not in prov or force:
            prov[field] = source_id
        chip["provenance"] = prov

    def bulk_record(
        self,
        chip: dict[str, Any],
        fields: dict[str, str],
        *,
        force: bool = False,
    ) -> None:
        """Record provenance for multiple fields at once.

        Args:
            chip: The chip record to annotate (modified in place).
            fields: Mapping of field name to source_id.
            force: If True, overwrite existing provenance.
        """
        prov: dict[str, str] = chip.get("provenance") or {}
        for field, source_id in fields.items():
            if field in _SYSTEM_FIELDS:
                continue
            if field not in prov or force:
                prov[field] = source_id
        chip["provenance"] = prov

    def get_source(self, chip: dict[str, Any], field: str) -> str | None:
        """Return the source identifier for a given field.

        Args:
            chip: The chip record.
            field: The field name.

        Returns:
            The source string, or None if not tracked.
        """
        prov: dict[str, str] = chip.get("provenance") or {}
        return prov.get(field)


class ConflictResolver:
    """Logs field-level conflicts between multiple sources.

    Unlike a naive last-writer-wins approach, this resolver records
    disagreements so they can be audited or manually resolved later.
    """

    def __init__(self) -> None:
        self._conflicts: list[dict[str, Any]] = []

    @property
    def conflicts(self) -> list[dict[str, Any]]:
        """Return the list of recorded conflicts (read-only)."""
        return list(self._conflicts)

    def resolve(
        self,
        chip: dict[str, Any],
        field: str,
        current_value: Any,
        new_value: Any,
        current_source: str | None,
        new_source: str,
    ) -> Any:
        """Resolve a potential field-level conflict between two sources.

        If the values agree, no conflict is logged. If they disagree, the
        conflict is recorded and the *existing* value is kept (no
        last-writer-wins).

        Args:
            chip: The chip record.
            field: The field name being evaluated.
            current_value: The value already on the chip.
            new_value: The value proposed by the new source.
            current_source: The source of the existing value (may be None).
            new_source: The identifier of the new source.

        Returns:
            The value that should be kept (either current_value or new_value).
        """
        if current_value == new_value:
            return current_value

        if current_value is None or current_value == "" or current_value == [] or current_value == 0 or current_value == 0.0:
            # Current is empty — accept the new value
            return new_value

        if new_value is None or new_value == "" or new_value == [] or new_value == 0 or new_value == 0.0:
            # New value is empty — keep current
            return current_value

        conflict: dict[str, Any] = {
            "chip_id": chip.get("id"),
            "field": field,
            "current_value": current_value,
            "new_value": new_value,
            "current_source": current_source,
            "new_source": new_source,
        }
        self._conflicts.append(conflict)
        logger.warning(
            "Conflict on %s.%s: '%s' (%s) vs '%s' (%s)",
            chip.get("id"),
            field,
            current_value,
            current_source,
            new_value,
            new_source,
        )
        return current_value

    def clear(self) -> None:
        """Clear all recorded conflicts."""
        self._conflicts.clear()


def apply_provenance(
    chip: dict[str, Any],
    source_id: str = "legacy_v2",
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Convenience function: stamp provenance entries on a chip record.

    This is the primary public API for assigning provenance. Creates or
    updates the ``provenance`` dict on the chip for every non-empty,
    non-system field.

    Args:
        chip: The chip record (modified in place).
        source_id: The source identifier.
        force: If True, overwrite existing provenance entries.

    Returns:
        The chip dict with provenance applied.
    """
    tracker = ProvenanceTracker()
    tracker.record(chip, source_id, force=force)
    return chip
