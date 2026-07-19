"""Schema drift detection for scraper sources.

``SchemaDriftDetector`` monitors whether scraped results still cover the
expected set of fields for each source.  If the coverage drops below a
configurable threshold (default 80 %), a warning is logged so that
maintainers can investigate page structure changes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from soc_db.scraping.base import ChipScrapeResult

logger = logging.getLogger(__name__)


@dataclass
class DriftReport:
    """Report produced by :meth:`SchemaDriftDetector.check`.

    Attributes:
        source_id: The source that was checked.
        drift_detected: ``True`` if coverage fell below threshold.
        coverage: Fraction of expected fields actually found (0.0 – 1.0).
        expected_fields: Set of field names the source should produce.
        actual_fields: Set of field names found in the results.
        missing_fields: Expected fields not found in any result.
        new_fields: Fields found in results but not expected.
        message: Human-readable summary.
    """

    source_id: str
    drift_detected: bool
    coverage: float = 1.0
    expected_fields: set[str] = field(default_factory=set)
    actual_fields: set[str] = field(default_factory=set)
    missing_fields: set[str] = field(default_factory=set)
    new_fields: set[str] = field(default_factory=set)
    message: str = ""


class SchemaDriftDetector:
    """Detects when a source's page structure changes.

    Each source registers the set of fields it expects to find.  After
    each scrape run, the detector compares actual vs expected fields.
    If the intersection is below *threshold*, a warning is logged.

    Args:
        threshold: Minimum coverage fraction (0.0 – 1.0) before drift is
            reported.  Default 0.8 (80 %).
    """

    def __init__(self, threshold: float = 0.8) -> None:
        self._threshold = max(0.0, min(1.0, threshold))
        self._expected: dict[str, set[str]] = {}

    # ── registration ────────────────────────────────────────────────────

    def register_expected(self, source_id: str, fields: set[str]) -> None:
        """Register the set of fields *source_id* is expected to produce.

        If *source_id* already has registered fields and the new set
        differs by more than 10 %, log an info message with the diff.

        Args:
            source_id: Unique source identifier.
            fields: Set of expected field names.
        """
        if source_id in self._expected:
            old = self._expected[source_id]
            added = fields - old
            removed = old - fields
            if len(added) + len(removed) > 0:
                change_ratio = (len(added) + len(removed)) / max(len(old), 1)
                if change_ratio > 0.1:
                    logger.info(
                        "Expected fields for %s changed by %.0f%% "
                        "(added=%s, removed=%s)",
                        source_id,
                        change_ratio * 100,
                        sorted(added),
                        sorted(removed),
                    )

        self._expected[source_id] = set(fields)
        logger.debug("Registered %d expected fields for %s", len(fields), source_id)

    # ── checking ────────────────────────────────────────────────────────

    def check(self, source_id: str, results: list[ChipScrapeResult]) -> DriftReport:
        """Compare actual fields in *results* against expected fields.

        Args:
            source_id: The source to check.
            results: Parsed chip results from the scrape run.

        Returns:
            A :class:`DriftReport` summarising the comparison.
        """
        # Unknown source → return conservative result
        if source_id not in self._expected:
            logger.warning("No expected fields registered for %s", source_id)
            return DriftReport(
                source_id=source_id,
                drift_detected=False,
                message=f"No expected fields registered for {source_id}",
            )

        # Empty results → likely drift
        if not results:
            logger.warning("Zero results for %s — possible drift", source_id)
            return DriftReport(
                source_id=source_id,
                drift_detected=True,
                message=f"Zero results for {source_id} — possible drift",
            )

        expected = self._expected[source_id]
        actual: set[str] = set()
        for r in results:
            actual.update(r.fields.keys())

        intersection = expected & actual
        coverage = len(intersection) / len(expected) if expected else 1.0
        missing = expected - actual
        new = actual - expected

        drift = coverage < self._threshold
        message_parts = []
        if drift:
            message_parts.append(
                f"Drift detected for {source_id}: "
                f"{coverage:.0%} coverage (< {self._threshold:.0%} threshold)"
            )
        if missing:
            message_parts.append(f"Missing fields: {sorted(missing)}")
        if new:
            message_parts.append(f"New fields: {sorted(new)}")
        message = "; ".join(message_parts) if message_parts else "OK"

        if drift:
            logger.warning(
                "[%s] Schema drift: %.0f%% coverage (expected %d, actual %d, "
                "missing=%s, new=%s)",
                source_id,
                coverage * 100,
                len(expected),
                len(actual),
                sorted(missing),
                sorted(new),
            )

        return DriftReport(
            source_id=source_id,
            drift_detected=drift,
            coverage=coverage,
            expected_fields=expected,
            actual_fields=actual,
            missing_fields=missing,
            new_fields=new,
            message=message,
        )

    # ── queries ─────────────────────────────────────────────────────────

    def expected_fields(self, source_id: str) -> set[str]:
        """Return the expected fields for *source_id*, or an empty set."""
        return set(self._expected.get(source_id, set()))

    # ── lifecycle ───────────────────────────────────────────────────────

    def clear(self) -> None:
        """Clear all registered expected fields (for testing)."""
        self._expected.clear()
