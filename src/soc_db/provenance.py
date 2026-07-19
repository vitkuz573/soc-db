from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

LEGACY_SOURCE = "legacy_v2"


class ProvenanceTracker:
    def __init__(self, source_id: str = "unknown"):
        self._source_id = source_id

    SYSTEM_FIELDS = {"id", "provenance", "sources", "updated", "completeness", "_provenance", "rating", "benchmarks", "cache"}

    def record(self, chip: dict[str, Any], source_id: str | None = None, force: bool = False) -> dict[str, Any]:
        if source_id:
            self._source_id = source_id
        return self.track(chip, force=force)

    def record_field(self, chip: dict[str, Any], field: str, source_id: str) -> dict[str, Any]:
        if field in self.SYSTEM_FIELDS:
            return chip
        prov = chip.get("provenance") or {}
        prov[field] = source_id
        chip["provenance"] = prov
        return chip

    def bulk_record(self, chip: dict[str, Any], mapping: dict[str, str], force: bool = False) -> dict[str, Any]:
        prov = chip.get("provenance") or {}
        for field, source_id in mapping.items():
            if field in self.SYSTEM_FIELDS:
                continue
            if force or field not in prov:
                prov[field] = source_id
        chip["provenance"] = prov
        return chip

    def get_source(self, chip: dict[str, Any], field: str) -> str | None:
        prov = chip.get("provenance") or {}
        return prov.get(field)

    def track(self, chip: dict[str, Any], fields: list[str] | None = None, force: bool = False) -> dict[str, Any]:
        prov: dict[str, str] = chip.get("provenance") or {}
        target = fields or [k for k in chip if k not in self.SYSTEM_FIELDS and not k.startswith("_")]
        for f in target:
            if f in chip and chip[f] not in (None, "", [], 0, 0.0):
                if force or f not in prov:
                    prov[f] = self._source_id
        chip["provenance"] = prov
        return chip


class ConflictResolver:
    def __init__(self, priority: list[str] | None = None):
        self._priority = priority or []
        self.conflicts: list[dict[str, Any]] = []

    def clear(self) -> None:
        self.conflicts.clear()

    def resolve(self, chip: dict[str, Any], field: str, current_val: Any, incoming_val: Any, current_source: str | None, incoming_source: str) -> Any:
        if current_val in (None, 0, 0.0, "", []) or current_val == incoming_val:
            return incoming_val
        if incoming_val in (None, 0, 0.0, "", []):
            return current_val
        if current_source and (current_source in self._priority or incoming_source in self._priority):
            winner = incoming_source if self._priority.index(incoming_source) < self._priority.index(current_source) else current_source
            self.conflicts.append({"field": field, "current_value": current_val, "new_value": incoming_val, "current_source": current_source, "new_source": incoming_source, "winner": winner})
            return incoming_val if winner == incoming_source else current_val
        self.conflicts.append({"field": field, "current_value": current_val, "new_value": incoming_val, "current_source": current_source, "new_source": incoming_source})
        return current_val


def apply_provenance(chips: list[dict[str, Any]] | dict[str, Any], source_id: str = LEGACY_SOURCE, force: bool = False) -> list[dict[str, Any]] | dict[str, Any]:
    if isinstance(chips, dict):
        tracker = ProvenanceTracker(source_id)
        tracker.track(chips, force=force)
        return chips
    tracker = ProvenanceTracker(source_id)
    for chip in chips:
        prov = chip.get("provenance") or {}
        if prov and not force:
            continue
        tracker.track(chip, force=force)
    return chips
