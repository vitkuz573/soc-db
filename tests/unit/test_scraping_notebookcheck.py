"""Unit tests for NotebookCheckScraper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from soc_db.scraping.base import ChipScrapeResult
from soc_db.scraping.sources.notebookcheck import (
    NotebookCheckScraper,
    detect_vendor,
    parse_benchmark_value,
)

# ===========================================================================
# Fixture HTML — simplified NotebookCheck benchmark table
# ===========================================================================

SAMPLE_HTML = """
<html><body>
<table>
<tr>
  <th>Processor</th><th>Cores</th><th>Clock Speed</th><th>TDP</th>
  <th>Cinebench R23 Multi</th><th>Cinebench R23 Single</th>
  <th>Geekbench 6 Multi</th><th>Geekbench 6 Single</th>
  <th>x265</th><th>Blender</th><th>7-Zip</th>
  <th>AI Performance (NPU TOPS)</th>
</tr>
<tr>
  <td><a href="/review/xyz">Intel Core i9-13900HX</a></td>
  <td>24</td><td>2.2 GHz</td><td>55 W</td>
  <td>22,543</td><td>2,134</td><td>15,432</td><td>2,891</td>
  <td>78.5</td><td>342</td><td>89,123</td>
  <td>—</td>
</tr>
<tr>
  <td><a href="/review/abc">AMD Ryzen 9 7945HX</a></td>
  <td>16</td><td>2.5 GHz</td><td>55 W</td>
  <td>18,432</td><td>1,987</td><td>14,321</td><td>2,654</td>
  <td>65.2</td><td>298</td><td>76,543</td>
  <td>—</td>
</tr>
<tr>
  <td><a href="/review/def">Intel Core Ultra 7 155H</a></td>
  <td>16</td><td>1.4 GHz</td><td>28 W</td>
  <td>12,345</td><td>1,765</td><td>11,234</td><td>2,345</td>
  <td>45.1</td><td>198</td><td>54,321</td>
  <td>11</td>
</tr>
<tr>
  <td>Qualcomm Snapdragon X Elite</td>
  <td>12</td><td>3.8 GHz</td><td>23 W</td>
  <td>10,987</td><td>1,654</td><td>13,456</td><td>2,765</td>
  <td>55.3</td><td>256</td><td>67,890</td>
  <td>45</td>
</tr>
</table>
</body></html>
"""

EMPTY_HTML = "<html><body></body></html>"


# ===========================================================================
# Helper function tests
# ===========================================================================


class TestHelpers:
    def test_detect_vendor_intel(self):
        assert detect_vendor("Intel Core i9-13900HX") == "Intel"
        assert detect_vendor("Core Ultra 7 155H") == "Intel"

    def test_detect_vendor_amd(self):
        assert detect_vendor("AMD Ryzen 9 7945HX") == "AMD"

    def test_detect_vendor_qualcomm(self):
        assert detect_vendor("Qualcomm Snapdragon X Elite") == "Qualcomm"

    def test_parse_benchmark_value(self):
        assert parse_benchmark_value("22,543") == 22543
        assert parse_benchmark_value("78.5") == 78.5
        assert parse_benchmark_value("—") is None
        assert parse_benchmark_value("N/A") is None
        assert parse_benchmark_value("") is None


# ===========================================================================
# NotebookCheckScraper tests
# ===========================================================================


class TestNotebookCheckScraper:
    def test_source_id(self):
        assert NotebookCheckScraper.SOURCE_ID == "notebookcheck"

    def test_vendors(self):
        assert len(NotebookCheckScraper.VENDORS) >= 5
        assert "Intel" in NotebookCheckScraper.VENDORS
        assert "AMD" in NotebookCheckScraper.VENDORS

    def test_priority(self):
        assert NotebookCheckScraper.PRIORITY == 25

    def test_rate_limiter_configured(self):
        scraper = NotebookCheckScraper()
        assert scraper.rate_limiter is not None
        assert scraper.rate_limiter._requests_per_sec == 0.5

    def test_expected_fields(self):
        fields = NotebookCheckScraper.expected_fields()
        assert len(fields) >= 15
        assert "name" in fields
        assert "cinebench_r23_mt" in fields
        assert "geekbench_6_mt" in fields
        assert "ai_tops_npu" in fields

    def test_parse_valid_html(self):
        scraper = NotebookCheckScraper()
        results = scraper.parse(SAMPLE_HTML)
        assert len(results) == 4

        # Check first result (Intel)
        r = results[0]
        assert "Intel" in r.vendor
        assert r.fields.get("name") == "Intel Core i9-13900HX"
        assert r.fields.get("cores") == 24
        assert r.fields.get("cinebench_r23_mt") == 22543
        assert r.fields.get("geekbench_6_mt") is not None

        # Check first result is ChipScrapeResult
        assert isinstance(r, ChipScrapeResult)
        assert r.source_id == "notebookcheck"

    def test_parse_empty_html(self):
        scraper = NotebookCheckScraper()
        results = scraper.parse(EMPTY_HTML)
        assert len(results) == 0

    def test_parse_invalid_html(self):
        scraper = NotebookCheckScraper()
        results = scraper.parse("<html><body><div>no table</div></body></html>")
        assert len(results) == 0

    def test_produces_chip_scrape_result(self):
        scraper = NotebookCheckScraper()
        results = scraper.parse(SAMPLE_HTML)
        for r in results:
            assert isinstance(r, ChipScrapeResult)
            assert r.source_id == "notebookcheck"

    def test_expected_fields_in_results(self):
        """Verify parsed results contain benchmark data."""
        scraper = NotebookCheckScraper()
        results = scraper.parse(SAMPLE_HTML)
        for r in results:
            fields = r.fields
            assert "name" in fields
            # At least some benchmark data should be present
            has_benchmark = any(
                k in fields
                for k in ("cinebench_r23_mt", "geekbench_6_mt", "cinebench_r23_st")
            )
            assert has_benchmark, f"No benchmark data in {fields.get('name')}"

    @patch("soc_db.scraping.sources.notebookcheck.HTTPSource")
    def test_fetch_calls_robots(self, mock_http_cls):
        """fetch() should check robots.txt."""
        mock_http = MagicMock()
        mock_http.fetch.return_value = "<html></html>"
        mock_http_cls.return_value = mock_http

        scraper = NotebookCheckScraper()
        scraper._robots_checker = MagicMock()
        scraper._robots_checker.can_fetch.return_value = True

        scraper.fetch()
        scraper._robots_checker.can_fetch.assert_called_once()
