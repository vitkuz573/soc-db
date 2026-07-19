"""Unit tests for SchemaDriftDetector."""

from __future__ import annotations

import pytest

from soc_db.scraping.base import ChipScrapeResult
from soc_db.scraping.drift import SchemaDriftDetector


class TestSchemaDriftDetector:
    def test_default_threshold(self):
        d = SchemaDriftDetector()
        assert d._threshold == 0.8

    def test_threshold_clamping(self):
        d = SchemaDriftDetector(threshold=1.5)
        assert d._threshold == 1.0

        d = SchemaDriftDetector(threshold=-0.5)
        assert d._threshold == 0.0

    def test_register_expected(self):
        d = SchemaDriftDetector()
        d.register_expected("wiki", {"cores", "gpu", "year", "process_nm", "model"})
        assert d.expected_fields("wiki") == {"cores", "gpu", "year", "process_nm", "model"}

    def test_check_all_fields_present(self):
        d = SchemaDriftDetector(threshold=0.8)
        d.register_expected("wiki", {"a", "b", "c"})
        r = ChipScrapeResult(name="chip1", vendor="V", fields={"a": "1", "b": "2", "c": "3"})
        report = d.check("wiki", [r])
        assert report.coverage == 1.0
        assert report.drift_detected is False
        assert report.message == "OK"

    def test_check_80_percent_coverage(self):
        """4/5 = 80% is exactly at threshold → no drift."""
        d = SchemaDriftDetector(threshold=0.8)
        d.register_expected("wiki", {"a", "b", "c", "d", "e"})
        r = ChipScrapeResult(
            name="chip1", vendor="V", fields={"a": "1", "b": "2", "c": "3", "d": "4"}
        )
        report = d.check("wiki", [r])
        assert report.coverage == pytest.approx(0.8)
        assert report.drift_detected is False

    def test_check_below_threshold(self):
        """3/5 = 60% < 80% → drift detected."""
        d = SchemaDriftDetector(threshold=0.8)
        d.register_expected("wiki", {"a", "b", "c", "d", "e"})
        r = ChipScrapeResult(name="chip1", vendor="V", fields={"a": "1", "b": "2", "c": "3"})
        report = d.check("wiki", [r])
        assert report.coverage == pytest.approx(0.6)
        assert report.drift_detected is True

    def test_check_empty_results(self):
        """Empty results list returns drift_detected=True."""
        d = SchemaDriftDetector()
        d.register_expected("wiki", {"a", "b"})
        report = d.check("wiki", [])
        assert report.drift_detected is True
        assert "Zero results" in report.message

    def test_check_unregistered_source(self):
        """Unknown source_id logs warning and returns drift_detected=False."""
        d = SchemaDriftDetector()
        report = d.check("unknown", [ChipScrapeResult(name="chip1", vendor="V")])
        assert report.drift_detected is False
        assert "No expected fields registered" in report.message

    def test_missing_and_new_fields_in_report(self):
        d = SchemaDriftDetector(threshold=0.8)
        d.register_expected("wiki", {"a", "b", "c"})
        r = ChipScrapeResult(name="chip1", vendor="V", fields={"a": "1", "d": "4", "e": "5"})
        report = d.check("wiki", [r])
        assert report.missing_fields == {"b", "c"}
        assert report.new_fields == {"d", "e"}

    def test_clear(self):
        d = SchemaDriftDetector()
        d.register_expected("wiki", {"a", "b"})
        assert len(d.expected_fields("wiki")) == 2
        d.clear()
        assert len(d.expected_fields("wiki")) == 0

    def test_register_update_detects_change(self, caplog):
        caplog.set_level("INFO")
        d = SchemaDriftDetector()
        d.register_expected("wiki", {"a", "b", "c"})
        d.register_expected("wiki", {"a", "b", "c", "d", "e"})
        # Change ratio: 2/3 = 67% > 10%, should log
        assert len(caplog.messages) > 0, f"caplog is empty (level={caplog.handler.level})"
        assert any("changed" in msg.lower() for msg in caplog.messages), f"messages: {caplog.messages}"

    def test_drift_logs_warning(self, caplog):
        caplog.set_level("WARNING")
        d = SchemaDriftDetector(threshold=0.6)
        d.register_expected("wiki", {"a", "b", "c", "d"})
        r = ChipScrapeResult(name="chip1", vendor="V", fields={"a": "1", "b": "2"})
        d.check("wiki", [r])
        # 2/4 = 50% < 60% → drift detected → warning logged
        assert any("drift" in msg.lower() for msg in caplog.messages)
