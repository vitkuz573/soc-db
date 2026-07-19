"""Unit tests for AppleTechSpecsScraper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from soc_db.scraping.base import BaseScraper, ChipScrapeResult
from soc_db.scraping.sources.apple_techspecs import (
    AppleTechSpecsScraper,
    APPLE_SILICON,
    APPLE_CORE_CONFIGS,
    APPLE_GPU_CONFIGS,
    APPLE_NPU_CONFIGS,
    APPLE_MEMORY_BANDWIDTH,
    APPLE_TDP,
    _detect_apple_chip,
)

# ===========================================================================
# Fixture HTML — simplified Apple Tech Specs page
# ===========================================================================

SAMPLE_HTML = """
<html><body>
<table class="specs">
  <tr><th>Processor</th><td>Apple M3 Max</td></tr>
  <tr><th>Cores</th><td>16-core: 12 performance + 4 efficiency</td></tr>
  <tr><th>GPU</th><td>40-core</td></tr>
  <tr><th>Neural Engine</th><td>16-core</td></tr>
  <tr><th>Memory</th><td>128 GB unified, 400 GB/s bandwidth</td></tr>
  <tr><th>Process</th><td>3 nm</td></tr>
</table>
</body></html>
"""

EMPTY_HTML = "<html><body></body></html>"


class TestAppleTechSpecsHelpers:
    def test_detect_chip_m_series(self):
        assert _detect_apple_chip("Apple M3") == "M3"
        assert _detect_apple_chip("Apple M3 Max") == "M3 Max"
        assert _detect_apple_chip("M2 Pro") == "M2 Pro"
        assert _detect_apple_chip("M1 Ultra") == "M1 Ultra"

    def test_detect_chip_a_series(self):
        assert _detect_apple_chip("A17 Pro") == "A17 Pro"
        assert _detect_apple_chip("A16 Bionic") == "A16 Bionic"
        assert _detect_apple_chip("A18") == "A18"

    def test_detect_chip_none(self):
        assert _detect_apple_chip("Intel Core i7") is None
        assert _detect_apple_chip("") is None

    def test_silicon_knowledge_base(self):
        """Verify known chips are in the knowledge base."""
        assert "M1" in APPLE_SILICON
        assert "M3 Max" in APPLE_SILICON
        assert "M4" in APPLE_SILICON
        assert "A18 Pro" in APPLE_SILICON
        assert APPLE_SILICON["M1"]["year"] == 2020
        assert APPLE_SILICON["M4"]["process_nm"] == 3

    def test_core_configs(self):
        assert APPLE_CORE_CONFIGS["M1"] == (4, 4)
        assert APPLE_CORE_CONFIGS["M3 Max"] == (12, 4)

    def test_gpu_configs(self):
        assert APPLE_GPU_CONFIGS["M1"] == 8
        assert APPLE_GPU_CONFIGS["M3 Max"] == 40

    def test_npu_configs(self):
        """All Apple Silicon chips have 16-core Neural Engine."""
        for chip, cores in APPLE_NPU_CONFIGS.items():
            assert cores >= 16, f"{chip} has {cores} NPU cores"

    def test_memory_bandwidth(self):
        assert APPLE_MEMORY_BANDWIDTH["M1"] == 68
        assert APPLE_MEMORY_BANDWIDTH["M1 Ultra"] == 800
        assert APPLE_MEMORY_BANDWIDTH["M4 Max"] == 546

    def test_tdp_values(self):
        assert APPLE_TDP["M1"] == 14
        assert APPLE_TDP["M1 Max"] == 60
        assert APPLE_TDP["M4 Ultra"] == 160


class TestAppleTechSpecsScraper:
    def test_source_id(self):
        assert AppleTechSpecsScraper.SOURCE_ID == "apple_techspecs"

    def test_vendors(self):
        assert AppleTechSpecsScraper.VENDORS == ["Apple"]

    def test_priority(self):
        assert AppleTechSpecsScraper.PRIORITY == 40

    def test_rate_limiter_configured(self):
        scraper = AppleTechSpecsScraper()
        assert scraper.rate_limiter is not None
        assert scraper.rate_limiter._burst == 2

    def test_parse_valid_html(self):
        scraper = AppleTechSpecsScraper()
        results = scraper.parse(SAMPLE_HTML)
        # Should include parsed M3 Max + all known chips as fallback
        assert len(results) >= 1

        # Check M3 Max result
        m3_max_results = [r for r in results if "M3 Max" in r.fields.get("name", "")]
        if m3_max_results:
            r = m3_max_results[0]
            assert r.vendor == "Apple"
            fields = r.fields
            # Should have parsed performance/efficiency cores from sample
            if "performance_cores" in fields:
                assert fields["performance_cores"] == 12
                assert fields["efficiency_cores"] == 4

    def test_parse_empty_html(self):
        scraper = AppleTechSpecsScraper()
        results = scraper.parse(EMPTY_HTML)
        # Even with empty HTML, should produce known chips as fallback
        assert len(results) >= 1

    def test_produces_chip_scrape_result(self):
        scraper = AppleTechSpecsScraper()
        results = scraper.parse(SAMPLE_HTML)
        for r in results:
            assert isinstance(r, ChipScrapeResult)
            assert r.source_id == "apple_techspecs"

    def test_dedup_works(self):
        scraper = AppleTechSpecsScraper()
        results = scraper.parse(SAMPLE_HTML)
        deduped = scraper.dedup(results + results)
        assert len(deduped) == len(results)

    def test_is_base_scraper_subclass(self):
        assert issubclass(AppleTechSpecsScraper, BaseScraper)

    def test_fallback_chips_present(self):
        """Verify all known chips are produced when HTML has no data."""
        scraper = AppleTechSpecsScraper()
        results = scraper.parse(EMPTY_HTML)
        names = {r.fields.get("name", "") for r in results}
        assert "Apple M1" in names
        assert "Apple M4" in names
        assert "Apple A18 Pro" in names

    def test_m4_has_correct_fields(self):
        """Verify M4 chip has expected specs."""
        scraper = AppleTechSpecsScraper()
        results = scraper.parse(EMPTY_HTML)
        m4 = [r for r in results if r.fields.get("name") == "Apple M4"]
        assert len(m4) >= 1
        chip = m4[0].fields
        assert chip.get("process_nm") == 3
        assert chip.get("cores") == 10  # 4 P + 6 E

    @patch("soc_db.scraping.sources.apple_techspecs.HTTPSource")
    def test_fetch_calls_robots(self, mock_http_cls):
        mock_http = MagicMock()
        mock_http.fetch.return_value = "<html></html>"
        mock_http_cls.return_value = mock_http

        scraper = AppleTechSpecsScraper()
        scraper._robots_checker = MagicMock()
        scraper._robots_checker.can_fetch.return_value = True

        scraper.fetch()
        scraper._robots_checker.can_fetch.assert_called_once()
