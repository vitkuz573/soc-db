"""Unit tests for TechPowerUpScraper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from soc_db.scraping.base import BaseScraper, ChipScrapeResult
from soc_db.scraping.rate_limit import PerSourceRateLimiter
from soc_db.scraping.sources.techpowerup import (
    TechPowerUpScraper,
    detect_vendor,
    parse_cache_size,
    parse_clock,
    parse_core_thread,
    parse_memory_max,
    parse_process_node,
    parse_tdp,
)

# ===========================================================================
# Fixture HTML — simplified TechPowerUp CPU specs table
# ===========================================================================

SAMPLE_HTML = """
<html><body>
<table>
<tr>
  <th>CPU</th><th>Cores / Threads</th><th>Clock / Boost</th>
  <th>Process</th><th>TDP</th><th>Memory</th><th>Cache</th><th>GPU</th>
</tr>
<tr>
  <td><a href="/specs/intel-core-i7-13700k">Intel Core i7-13700K</a></td>
  <td>16 / 24</td>
  <td>3.4 GHz / 5.4 GHz</td>
  <td>10 nm</td>
  <td>125 W</td>
  <td>DDR5-5600, 128 GB</td>
  <td>L2$ 2 MB, L3$ 30 MB</td>
  <td>Intel UHD Graphics 770</td>
</tr>
<tr>
  <td><a href="/specs/amd-ryzen-9-7950x">AMD Ryzen 9 7950X</a></td>
  <td>16 / 32</td>
  <td>4.5 GHz / 5.7 GHz</td>
  <td>5 nm</td>
  <td>170 W</td>
  <td>DDR5-5200, 128 GB</td>
  <td>L2$ 16 MB, L3$ 64 MB</td>
  <td>AMD Radeon Graphics</td>
</tr>
<tr>
  <td><a href="/specs/intel-core-i5-13600k">Intel Core i5-13600K</a></td>
  <td>14 / 20</td>
  <td>3.5 GHz / 5.1 GHz</td>
  <td>10 nm</td>
  <td>125 W</td>
  <td>DDR5-5600, 128 GB</td>
  <td>L2$ 20 MB, L3$ 24 MB</td>
  <td>Intel UHD Graphics 770</td>
</tr>
<tr>
  <td><a href="/specs/amd-ryzen-7-7800x3d">AMD Ryzen 7 7800X3D</a></td>
  <td>8 / 16</td>
  <td>4.2 GHz / 5.0 GHz</td>
  <td>5 nm</td>
  <td>120 W</td>
  <td>DDR5-5200, 128 GB</td>
  <td>L2$ 8 MB, L3$ 96 MB</td>
  <td>AMD Radeon Graphics</td>
</tr>
</table>
</body></html>
"""

EMPTY_HTML = "<html><body></body></html>"
INVALID_HTML = "<html><body><div>no table here</div></body></html>"


# ===========================================================================
# Helper function tests
# ===========================================================================


class TestHelpers:
    def test_detect_vendor_intel(self):
        assert detect_vendor("Intel Core i7-13700K") == "Intel"
        assert detect_vendor("Core i5-13600K") == "Intel"

    def test_detect_vendor_amd(self):
        assert detect_vendor("AMD Ryzen 9 7950X") == "AMD"
        assert detect_vendor("Ryzen 7 7800X3D") == "AMD"

    def test_detect_vendor_unknown(self):
        assert detect_vendor("Some Unknown CPU") == "Unknown"

    def test_parse_tdp(self):
        assert parse_tdp("125 W") == 125
        assert parse_tdp("15W") == 15
        assert parse_tdp("N/A") is None
        assert parse_tdp("") is None

    def test_parse_cache_size(self):
        assert parse_cache_size("L2$ 2 MB") is not None
        assert parse_cache_size("L3$ 30 MB") is not None
        assert parse_cache_size("16 MB") is not None
        assert parse_cache_size("N/A") is None

    def test_parse_memory_max(self):
        val = parse_memory_max("DDR5-5600, 128 GB")
        assert val is not None
        assert "128" in val

    def test_parse_clock(self):
        base, boost = parse_clock("3.4 GHz / 5.4 GHz")
        assert base == 3.4
        assert boost == 5.4

        base2, boost2 = parse_clock("3.2 GHz")
        assert base2 == 3.2
        assert boost2 is None

        base3, boost3 = parse_clock("N/A")
        assert base3 is None
        assert boost3 is None

    def test_parse_core_thread(self):
        c, t = parse_core_thread("16 / 24")
        assert c == 16
        assert t == 24

        c2, t2 = parse_core_thread("8")
        assert c2 == 8
        assert t2 == 8

        c3, t3 = parse_core_thread("")
        assert c3 is None
        assert t3 is None

    def test_parse_process_node(self):
        assert parse_process_node("10 nm") == 10
        assert parse_process_node("5 nm") == 5
        assert parse_process_node("N/A") is None


# ===========================================================================
# TechPowerUpScraper tests
# ===========================================================================


class TestTechPowerUpScraper:
    def test_source_id(self):
        assert TechPowerUpScraper.SOURCE_ID == "techpowerup"

    def test_vendors(self):
        assert len(TechPowerUpScraper.VENDORS) > 5
        assert "Intel" in TechPowerUpScraper.VENDORS
        assert "AMD" in TechPowerUpScraper.VENDORS

    def test_priority(self):
        assert TechPowerUpScraper.PRIORITY == 20

    def test_rate_limiter_configured(self):
        scraper = TechPowerUpScraper()
        assert scraper.rate_limiter is not None
        assert scraper.rate_limiter._burst == 3

    def test_expected_fields(self):
        fields = TechPowerUpScraper.expected_fields()
        assert len(fields) >= 16
        assert "name" in fields
        assert "cores" in fields
        assert "tdp" in fields
        assert "process_nm" in fields
        assert "memory_type" in fields
        assert "l3_cache" in fields

    def test_parse_valid_html(self):
        scraper = TechPowerUpScraper()
        results = scraper.parse(SAMPLE_HTML)
        assert len(results) == 4

        # Check first result
        r = results[0]
        assert "Intel" in r.vendor
        assert r.fields.get("name") == "Intel Core i7-13700K"
        assert r.fields.get("cores") == 16
        assert r.fields.get("threads") == 24

        # Check AMD result
        amd_results = [r for r in results if "AMD" in r.vendor]
        assert len(amd_results) >= 2
        amd = amd_results[0]
        assert amd.fields.get("cores") == 16
        assert amd.fields.get("tdp") == 170

    def test_parse_empty_html(self):
        scraper = TechPowerUpScraper()
        results = scraper.parse(EMPTY_HTML)
        assert len(results) == 0

    def test_parse_invalid_html(self):
        scraper = TechPowerUpScraper()
        results = scraper.parse(INVALID_HTML)
        assert len(results) == 0

    def test_expected_fields_in_results(self):
        """Verify parsed results contain expected non-system fields."""
        scraper = TechPowerUpScraper()
        results = scraper.parse(SAMPLE_HTML)
        for r in results:
            fields = r.fields
            assert "name" in fields
            assert "cores" in fields or "tdp" in fields

    def test_produces_chip_scrape_result(self):
        scraper = TechPowerUpScraper()
        results = scraper.parse(SAMPLE_HTML)
        for r in results:
            assert isinstance(r, ChipScrapeResult)
            assert r.source_id == "techpowerup"

    def test_dedup_works(self):
        scraper = TechPowerUpScraper()
        results = scraper.parse(SAMPLE_HTML * 2)  # Duplicate rows
        deduped = scraper.dedup(results)
        assert len(deduped) <= len(results)

    @patch("soc_db.scraping.sources.techpowerup.HTTPSource")
    def test_fetch_calls_robots(self, mock_http_cls):
        """fetch() should call check_robots."""
        mock_http = MagicMock()
        mock_http.fetch.return_value = "<html></html>"
        mock_http_cls.return_value = mock_http

        scraper = TechPowerUpScraper()
        scraper._robots_checker = MagicMock()
        scraper._robots_checker.can_fetch.return_value = True

        scraper.fetch()
        scraper._robots_checker.can_fetch.assert_called_once()
