"""Data quality scoring for vendor chip records.

The ``QualityScorer`` computes per-vendor and per-field quality metrics:

- **fill_rate**: fraction of chips that have a non-empty value for each field.
- **source_diversity**: number of unique provenance sources per vendor.
- **conflict_rate**: fraction of fields with conflicting source provenance.

Usage::

    scorer = QualityScorer()
    report = scorer.generate_report(chips)
    print(report.markdown_summary())
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any

from soc_db.enrich._helpers import _has
from soc_db.enrich._vendor_data import FIELD_GROUPS

logger = logging.getLogger(__name__)

# Fields that are system-generated and not meaningful for fill-rate computation
_SYSTEM_FIELDS = frozenset({
    "id",
    "uuid",
    "completeness",
    "sources",
    "updated",
    "provenance",
    "_dedup_strategy",
    "rating",
    "benchmarks",
    "cache",
})


class QualityScorer:
    """Compute data quality metrics across chip records.

    Attributes:
        chips: The full list of chip records to analyse.
        vendors: Sorted list of vendor names present in *chips*.
    """

    def __init__(self, chips: list[dict[str, Any]] | None = None) -> None:
        self.chips = chips or []
        self._vendors: list[str] | None = None

    @property
    def vendors(self) -> list[str]:
        if self._vendors is None:
            seen: set[str] = set()
            for c in self.chips:
                v = c.get("vendor", "Unknown")
                seen.add(v)
            self._vendors = sorted(seen)
        return self._vendors

    # ------------------------------------------------------------------
    # Fill rate
    # ------------------------------------------------------------------

    def fill_rate(self, chips: list[dict[str, Any]] | None = None) -> dict[str, float]:
        """Compute the fill rate for every field across a set of chips.

        The fill rate is the fraction of chips where a field has a
        non-empty value (not None, "", [], 0, or 0.0).

        Args:
            chips: Chip subset to analyse.  Defaults to ``self.chips``.

        Returns:
            Dict mapping field names to fill-rate floats (0.0 – 1.0).
        """
        chips = chips or self.chips
        if not chips:
            return {}

        # Collect all unique fields across all chips (excluding system fields)
        all_fields: set[str] = set()
        for c in chips:
            all_fields.update(k for k in c if k not in _SYSTEM_FIELDS)

        counts: dict[str, int] = defaultdict(int)
        total = len(chips)
        for c in chips:
            for f in all_fields:
                if _has(c, f):
                    counts[f] += 1

        return {f: round(counts[f] / total, 4) for f in sorted(all_fields)}

    def vendor_fill_rates(
        self,
    ) -> dict[str, dict[str, float]]:
        """Compute fill rates per vendor.

        Returns:
            Nested dict: ``{vendor: {field: fill_rate}}``.
        """
        result: dict[str, dict[str, float]] = {}
        for vendor in self.vendors:
            v_chips = [c for c in self.chips if c.get("vendor") == vendor]
            result[vendor] = self.fill_rate(v_chips)
        return result

    # ------------------------------------------------------------------
    # Source diversity
    # ------------------------------------------------------------------

    def source_diversity(self) -> dict[str, dict[str, Any]]:
        """Compute source diversity metrics per vendor.

        Returns:
            Nested dict: ``{vendor: {unique_sources: N, total_fields: N}}``.
        """
        result: dict[str, dict[str, Any]] = {}
        for vendor in self.vendors:
            v_chips = [c for c in self.chips if c.get("vendor") == vendor]
            all_sources: set[str] = set()
            total_fields = 0
            for c in v_chips:
                prov = c.get("provenance") or {}
                for _field, src in prov.items():
                    if src:
                        all_sources.add(src)
                        total_fields += 1
            result[vendor] = {
                "unique_sources": len(all_sources),
                "source_list": sorted(all_sources),
                "total_fields": total_fields,
                "chip_count": len(v_chips),
            }
        return result

    # ------------------------------------------------------------------
    # Conflict rate
    # ------------------------------------------------------------------

    def conflict_rate(self) -> dict[str, dict[str, Any]]:
        """Compute conflict metrics per vendor.

        A conflict occurs when provenance shows multiple different sources
        for the same field across chips of the same vendor.  Because
        ``provenance`` is per-chip, we detect conflict when the same field
        has different source values across different chips.

        Returns:
            Nested dict: ``{vendor: {conflict_rate, conflicts_count,
            total_sourceable_fields}}``.
        """
        result: dict[str, dict[str, Any]] = {}
        for vendor in self.vendors:
            v_chips = [c for c in self.chips if c.get("vendor") == vendor]

            # Track per-field source sets across all chips
            field_sources: dict[str, set[str]] = defaultdict(set)
            for c in v_chips:
                prov = c.get("provenance") or {}
                for field, src in prov.items():
                    if src:
                        field_sources[field].add(src)

            conflict_count = 0
            total_fields_with_source = 0
            for field, sources in field_sources.items():
                if len(sources) > 1:
                    conflict_count += 1
                total_fields_with_source += 1

            rate = round(conflict_count / max(total_fields_with_source, 1), 4)
            result[vendor] = {
                "conflict_rate": rate,
                "conflicts": conflict_count,
                "total_fields_with_source": total_fields_with_source,
                "chip_count": len(v_chips),
            }
        return result

    # ------------------------------------------------------------------
    # Field group summary
    # ------------------------------------------------------------------

    def field_group_summary(
        self, chips: list[dict[str, Any]] | None = None
    ) -> dict[str, float]:
        """Compute average fill rate per field group.

        Args:
            chips: Chip subset to analyse.  Defaults to ``self.chips``.

        Returns:
            Dict mapping group name to average fill rate.
        """
        chips = chips or self.chips
        if not chips:
            return {}
        rates = self.fill_rate(chips)
        group_rates: dict[str, list[float]] = defaultdict(list)
        for group, fields in FIELD_GROUPS.items():
            for f in fields:
                if f in rates:
                    group_rates[group].append(rates[f])
        return {
            g: round(sum(v) / max(len(v), 1), 4) for g, v in sorted(group_rates.items()) if v
        }

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def generate_report(
        self, chips: list[dict[str, Any]] | None = None
    ) -> QualityReport:
        """Generate a structured quality report for all vendors.

        Args:
            chips: Optional chip subset.  Defaults to ``self.chips``.

        Returns:
            A :class:`QualityReport` instance.
        """
        if chips is not None:
            self.chips = chips
            self._vendors = None

        return QualityReport(
            chips=self.chips,
            vendors=self.vendors,
            fill_rates=self.vendor_fill_rates(),
            source_diversity=self.source_diversity(),
            conflict_rates=self.conflict_rate(),
            field_group_summary=self.field_group_summary(),
        )


class QualityReport:
    """Structured quality report with rendering helpers.

    Attributes:
        chips: The analysed chip list.
        vendors: Sorted vendor names.
        fill_rates: Per-vendor per-field fill rates.
        source_diversity: Per-vendor source diversity metrics.
        conflict_rates: Per-vendor conflict metrics.
        field_group_summary: Average fill rate per field group.
    """

    def __init__(
        self,
        chips: list[dict[str, Any]],
        vendors: list[str],
        fill_rates: dict[str, dict[str, float]],
        source_diversity: dict[str, dict[str, Any]],
        conflict_rates: dict[str, dict[str, Any]],
        field_group_summary: dict[str, float],
    ) -> None:
        self.chips = chips
        self.vendors = vendors
        self.fill_rates = fill_rates
        self.source_diversity = source_diversity
        self.conflict_rates = conflict_rates
        self.field_group_summary = field_group_summary

    @property
    def total_chips(self) -> int:
        return len(self.chips)

    def to_dict(self) -> dict[str, Any]:
        """Return the full report as a JSON-serialisable dict."""
        return {
            "summary": {
                "total_chips": self.total_chips,
                "total_vendors": len(self.vendors),
            },
            "field_group_summary": self.field_group_summary,
            "vendors": {
                v: {
                    "fill_rates": self.fill_rates.get(v, {}),
                    "source_diversity": self.source_diversity.get(v, {}),
                    "conflict": self.conflict_rates.get(v, {}),
                }
                for v in self.vendors
            },
        }

    def markdown_summary(self) -> str:
        """Render a human-readable markdown quality summary.

        Returns:
            A formatted markdown string.
        """
        lines: list[str] = [
            "# Quality Report",
            "",
            f"**Total chips:** {self.total_chips}",
            f"**Total vendors:** {len(self.vendors)}",
            "",
        ]

        # Field group summary
        lines.append("## Field Group Coverage")
        lines.append("")
        lines.append("| Group | Avg Fill Rate |")
        lines.append("|-------|--------------:|")
        for group, rate in sorted(self.field_group_summary.items()):
            pct = round(rate * 100, 1)
            bar = _bar(rate)
            lines.append(f"| {group} | {pct}% {bar} |")
        lines.append("")

        # Per-vendor overview
        lines.append("## Per-Vendor Overview")
        lines.append("")
        lines.append("| Vendor | Chips | Sources | Conflict Rate | Top Fields |")
        lines.append("|--------|------:|--------:|--------------:|-----------:|")
        for v in self.vendors:
            sd = self.source_diversity.get(v, {})
            cr = self.conflict_rates.get(v, {})
            num_sources = sd.get("unique_sources", 0)
            conf_rate = cr.get("conflict_rate", 0.0)
            conf_pct = round(conf_rate * 100, 1)
            chip_count = sd.get("chip_count", 0)

            # Show top-5 fields by fill rate
            fr = self.fill_rates.get(v, {})
            top_fields = sorted(fr.items(), key=lambda x: -x[1])[:5]
            top_str = ", ".join(f"{f}={round(r*100,0):.0f}%" for f, r in top_fields)

            lines.append(
                f"| {v} | {chip_count} | {num_sources} | {conf_pct}% | {top_str} |"
            )
        lines.append("")

        return "\n".join(lines)

    def to_json(self) -> str:
        """Return the report as a pretty-printed JSON string."""
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


def _bar(rate: float, width: int = 10) -> str:
    """Render a simple ASCII bar for a 0.0-1.0 ratio."""
    filled = round(rate * width)
    return "█" * filled + "░" * (width - filled)
