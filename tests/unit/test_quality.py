"""Tests for QualityScorer and QualityReport — fill rates, source diversity, conflict detection."""

from __future__ import annotations

import pytest

from soc_db.quality import QualityScorer, QualityReport


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def sample_chips():
    return [
        {"id": "a1", "name": "A1", "vendor": "VendorA", "cores": 8, "gpu": "G1", "year": 2023, "provenance": {"cores": "wiki", "name": "wiki"}},
        {"id": "a2", "name": "A2", "vendor": "VendorA", "cores": 8, "gpu": "G1", "year": 2023, "provenance": {"cores": "wiki", "name": "wiki"}},
        {"id": "a3", "name": "A3", "vendor": "VendorA", "cores": 4, "gpu": "", "year": None, "provenance": {"cores": "wiki", "name": "wiki"}},
        {"id": "b1", "name": "B1", "vendor": "VendorB", "cores": 8, "gpu": "G2", "year": 2024, "provenance": {"cores": "techpowerup", "name": "techpowerup", "gpu": "techpowerup"}},
        {"id": "b2", "name": "B2", "vendor": "VendorB", "cores": 8, "gpu": "G2", "year": 2024, "provenance": {"cores": "techpowerup", "name": "techpowerup"}},
    ]


@pytest.fixture
def conflicting_chips():
    """Chips with conflicting provenance for the same field."""
    return [
        {"id": "x1", "name": "X1", "vendor": "VendorX", "cores": 8, "provenance": {"cores": "wiki", "name": "wiki"}},
        {"id": "x2", "name": "X2", "vendor": "VendorX", "cores": 8, "provenance": {"cores": "techpowerup", "name": "wiki"}},
        {"id": "x3", "name": "X3", "vendor": "VendorX", "cores": 4, "provenance": {"cores": "wiki", "name": "wiki"}},
    ]


# ===========================================================================
# QualityScorer — fill_rate
# ===========================================================================


class TestFillRate:
    def test_empty_chips(self):
        scorer = QualityScorer([])
        assert scorer.fill_rate([]) == {}

    def test_all_fields_filled(self):
        chips = [{"id": "a", "name": "A", "vendor": "V", "cores": 8}]
        scorer = QualityScorer(chips)
        rates = scorer.fill_rate()
        assert rates.get("name", 0) == 1.0
        assert rates.get("vendor", 0) == 1.0

    def test_partial_fill(self):
        chips = [
            {"id": "a", "name": "A", "vendor": "V", "cores": 8},
            {"id": "b", "name": "B", "vendor": "V", "cores": None},
        ]
        scorer = QualityScorer(chips)
        rates = scorer.fill_rate()
        assert rates.get("name", 0) == 1.0
        assert rates.get("cores", 0) == 0.5  # Only 1 of 2 has cores

    def test_system_fields_excluded(self):
        """System/private fields are not counted in fill rate."""
        chips = [{"id": "a", "name": "A", "vendor": "V", "completeness": 0.8, "_hidden": "x"}]
        scorer = QualityScorer(chips)
        rates = scorer.fill_rate()
        # 'completeness' and '_hidden' should be excluded
        assert "completeness" not in rates


class TestVendorFillRates:
    def test_per_vendor(self, sample_chips):
        scorer = QualityScorer(sample_chips)
        rates = scorer.vendor_fill_rates()
        assert "VendorA" in rates
        assert "VendorB" in rates
        # VendorA: 3 chips, 2 have cores=8, 1 has cores=4 -> all have cores -> 1.0
        assert rates["VendorA"].get("cores", 0) == 1.0
        # VendorA: only 2 of 3 have gpu -> 0.6667
        assert rates["VendorA"].get("gpu", 0) == pytest.approx(0.6667, rel=0.01)

    def test_unknown_vendors(self):
        chips = [{"id": "a", "name": "A", "vendor": "V1"}, {"id": "b", "name": "B", "vendor": "V2"}]
        scorer = QualityScorer(chips)
        rates = scorer.vendor_fill_rates()
        assert "V1" in rates
        assert "V2" in rates


# ===========================================================================
# QualityScorer — source_diversity
# ===========================================================================


class TestSourceDiversity:
    def test_unique_sources(self, sample_chips):
        scorer = QualityScorer(sample_chips)
        div = scorer.source_diversity()
        # VendorA has only one source
        assert div["VendorA"]["unique_sources"] >= 1
        # VendorB should have 'techpowerup'
        assert "techpowerup" in div["VendorB"]["source_list"]

    def test_empty_chips(self):
        scorer = QualityScorer([])
        assert scorer.source_diversity() == {}

    def test_chip_count_in_source_diversity(self, sample_chips):
        scorer = QualityScorer(sample_chips)
        div = scorer.source_diversity()
        assert div["VendorA"]["chip_count"] == 3
        assert div["VendorB"]["chip_count"] == 2


# ===========================================================================
# QualityScorer — conflict_rate
# ===========================================================================


class TestConflictRate:
    def test_no_conflicts(self, sample_chips):
        scorer = QualityScorer(sample_chips)
        cr = scorer.conflict_rate()
        # VendorA: all chips come from 'wiki' for their fields -> no conflicts
        assert cr["VendorA"]["conflict_rate"] == 0.0

    def test_conflicts_detected(self, conflicting_chips):
        scorer = QualityScorer(conflicting_chips)
        cr = scorer.conflict_rate()
        # VendorX: 'cores' field has both 'wiki' and 'techpowerup' as sources -> conflict
        assert cr["VendorX"]["conflicts"] >= 1
        assert cr["VendorX"]["conflict_rate"] > 0.0

    def test_empty_chips(self):
        scorer = QualityScorer([])
        assert scorer.conflict_rate() == {}


# ===========================================================================
# QualityScorer — field_group_summary
# ===========================================================================


class TestFieldGroupSummary:
    def test_field_groups_present(self, sample_chips):
        scorer = QualityScorer(sample_chips)
        groups = scorer.field_group_summary()
        # Should have at least identity group (from FIELD_GROUPS)
        assert isinstance(groups, dict)
        assert len(groups) > 0

    def test_empty_chips(self):
        scorer = QualityScorer([])
        assert scorer.field_group_summary() == {}


# ===========================================================================
# QualityReport
# ===========================================================================


class TestQualityReport:
    def test_generate_report(self, sample_chips):
        scorer = QualityScorer(sample_chips)
        report = scorer.generate_report()
        assert isinstance(report, QualityReport)
        assert report.total_chips == 5
        assert len(report.vendors) == 2

    def test_report_to_dict(self, sample_chips):
        scorer = QualityScorer(sample_chips)
        report = scorer.generate_report()
        d = report.to_dict()
        assert "summary" in d
        assert "vendors" in d
        assert d["summary"]["total_chips"] == 5

    def test_report_to_json(self, sample_chips):
        scorer = QualityScorer(sample_chips)
        report = scorer.generate_report()
        json_str = report.to_json()
        assert isinstance(json_str, str)
        assert '"total_chips": 5' in json_str

    def test_report_markdown_summary(self, sample_chips):
        scorer = QualityScorer(sample_chips)
        report = scorer.generate_report()
        md = report.markdown_summary()
        assert "# Quality Report" in md
        assert "VendorA" in md
        assert "VendorB" in md
        assert "Field Group Coverage" in md
        assert "Per-Vendor Overview" in md

    def test_external_chips_override(self, sample_chips):
        """generate_report with explicit chips list overrides internal state."""
        scorer = QualityScorer()
        report = scorer.generate_report(sample_chips)
        assert report.total_chips == 5

    def test_empty_report(self):
        scorer = QualityScorer([])
        report = scorer.generate_report()
        assert report.total_chips == 0
        assert report.vendors == []
