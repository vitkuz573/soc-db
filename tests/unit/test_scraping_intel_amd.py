"""Unit tests for IntelAMDScraper and shared parsing utilities."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from soc_db.scraping.base import BaseScraper, ChipScrapeResult
from soc_db.scraping.sources.intel_amd import (
    IntelAMDScraper,
    detect_vendor,
    parse_core_thread,
    parse_clock,
    parse_tdp,
    parse_cache_size,
    parse_memory_max,
    parse_process_node,
)

# ===========================================================================
# Fixture HTML — simplified Intel/AMD product page HTML
# ===========================================================================

SAMPLE_HTML = {
    "intel": """
<html><body>
<article class="product">
  <h2>Intel Core i7-13700K</h2>
  <div class="specs">
    <p>Cores: 16 / 24</p>
    <p>Clock: 3.4 GHz / 5.4 GHz</p>
    <p>TDP: 125 W</p>
    <p>Process: 10 nm</p>
    <p>L2 Cache: 2 MB, L3 Cache: 30 MB</p>
    <p>Memory: DDR5-5600, 128 GB</p>
    <p>Graphics: Intel UHD Graphics 770</p>
    <p>Socket: LGA1700</p>
  </div>
</article>
</body></html>
""",
    "amd": """
<html><body>
<article class="product">
  <h2>AMD Ryzen 9 7950X</h2>
  <div class="specs">
    <p>Cores: 16 / 32</p>
    <p>Clock: 4.5 GHz / 5.7 GHz</p>
    <p>TDP: 170 W</p>
    <p>Process: 5 nm</p>
    <p>L2 Cache: 16 MB, L3 Cache: 64 MB</p>
    <p>Memory: DDR5-5200, 128 GB</p>
    <p>Socket: AM5</p>
  </div>
</article>
</body></html>
""",
}

EMPTY_HTML = {"intel": "<html><body></body></html>"}
INVALID_HTML = {"intel": "<html><body><div>no data</div></body></html>"}


# ===========================================================================
# Shared helper tests
# ===========================================================================


class TestHelpers:
    def test_detect_vendor_intel(self):
        assert detect_vendor("Intel Core i7-13700K") == "Intel"
        assert detect_vendor("Core Ultra 9 285K") == "Intel"

    def test_detect_vendor_amd(self):
        assert detect_vendor("AMD Ryzen 9 7950X") == "AMD"
        assert detect_vendor("Ryzen 7 7800X3D") == "AMD"

    def test_detect_vendor_unknown(self):
        assert detect_vendor("Some Unknown CPU") == "Unknown"

    def test_parse_core_thread(self):
        assert parse_core_thread("16 / 24") == (16, 24)
        assert parse_core_thread("8") == (8, 8)
        assert parse_core_thread("") == (None, None)

    def test_parse_clock(self):
        base, boost = parse_clock("3.4 GHz / 5.4 GHz")
        assert base == 3.4
        assert boost == 5.4

        base2, boost2 = parse_clock("3.2 GHz")
        assert base2 == 3.2
        assert boost2 is None

        assert parse_clock("N/A") == (None, None)

    def test_parse_tdp(self):
        assert parse_tdp("125 W") == 125
        assert parse_tdp("15W") == 15
        assert parse_tdp("N/A") is None

    def test_parse_cache_size(self):
        val = parse_cache_size("30 MB")
        assert val == "30 MB"
        assert parse_cache_size("16 MB (per core)") == "16 MB"
        assert parse_cache_size("N/A") is None

    def test_parse_memory_max(self):
        val = parse_memory_max("128 GB")
        assert val == "128 GB"
        val2 = parse_memory_max("Up to 128 GB")
        assert val2 == "128 GB"
        assert parse_memory_max("N/A") is None

    def test_parse_process_node(self):
        assert parse_process_node("7 nm") == 7
        assert parse_process_node("5 nm") == 5
        assert parse_process_node("N/A") is None


# ===========================================================================
# IntelAMDScraper tests
# ===========================================================================


class TestIntelAMDScraper:
    def test_source_id(self):
        assert IntelAMDScraper.SOURCE_ID == "intel_amd"

    def test_vendors(self):
        assert "Intel" in IntelAMDScraper.VENDORS
        assert "AMD" in IntelAMDScraper.VENDORS

    def test_priority(self):
        assert IntelAMDScraper.PRIORITY == 30

    def test_rate_limiter_configured(self):
        scraper = IntelAMDScraper()
        assert scraper.rate_limiter is not None
        assert scraper.rate_limiter._burst == 3

    def test_parse_valid_html_intel(self):
        scraper = IntelAMDScraper()
        results = scraper.parse(SAMPLE_HTML)
        assert len(results) >= 1

        intel_results = [r for r in results if r.vendor == "Intel"]
        assert len(intel_results) >= 1
        r = intel_results[0]
        assert "Core i7" in r.fields.get("name", "")
        assert r.fields.get("cores") == 16
        assert r.fields.get("tdp") == 125

    def test_parse_valid_html_amd(self):
        scraper = IntelAMDScraper()
        results = scraper.parse(SAMPLE_HTML)
        amd_results = [r for r in results if r.vendor == "AMD"]
        assert len(amd_results) >= 1
        r = amd_results[0]
        assert "Ryzen" in r.fields.get("name", "")
        assert r.fields.get("cores") == 16
        assert r.fields.get("tdp") == 170

    def test_parse_empty_html(self):
        scraper = IntelAMDScraper()
        results = scraper.parse(EMPTY_HTML)
        assert len(results) == 0

    def test_parse_invalid_html(self):
        scraper = IntelAMDScraper()
        results = scraper.parse(INVALID_HTML)
        assert len(results) == 0

    def test_produces_chip_scrape_result(self):
        scraper = IntelAMDScraper()
        results = scraper.parse(SAMPLE_HTML)
        for r in results:
            assert isinstance(r, ChipScrapeResult)
            assert r.source_id == "intel_amd"

    def test_dedup_works(self):
        scraper = IntelAMDScraper()
        results = scraper.parse(SAMPLE_HTML)
        deduped = scraper.dedup(results + results)
        assert len(deduped) == len(results)

    def test_is_base_scraper_subclass(self):
        assert issubclass(IntelAMDScraper, BaseScraper)

    @patch("soc_db.scraping.sources.intel_amd.HTTPSource")
    def test_fetch_calls_robots(self, mock_http_cls):
        mock_http = MagicMock()
        mock_http.fetch.return_value = "<html></html>"
        mock_http_cls.return_value = mock_http

        scraper = IntelAMDScraper()
        scraper._robots_checker = MagicMock()
        scraper._robots_checker.can_fetch.return_value = True

        scraper.fetch()
        assert scraper._robots_checker.can_fetch.call_count >= 1

    def test_result_has_expected_fields(self):
        scraper = IntelAMDScraper()
        results = scraper.parse(SAMPLE_HTML)
        for r in results:
            fields = r.fields
            assert "name" in fields
            # At least one of these should be present
            has_core_spec = bool(fields.get("cores")) or bool(fields.get("tdp"))
            assert has_core_spec
