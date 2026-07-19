"""Unit tests for GeekbenchScraper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from soc_db.scraping.base import ChipScrapeResult
from soc_db.scraping.sources.geekbench import GeekbenchScraper, detect_vendor, parse_score

# ===========================================================================
# Fixture HTML — simplified Geekbench Browser results page
# ===========================================================================

SAMPLE_HTML = """
<html><body>
<div class="result">
  <a href="/v6/cpu/12345">Intel Core i9-13900K</a>
  <span>2,345</span>
  <span>18,765</span>
  <span>12,345</span>
</div>
<div class="result">
  <a href="/v6/cpu/12346">AMD Ryzen 9 7950X</a>
  <span>2,567</span>
  <span>20,123</span>
  <span>14,567</span>
</div>
<div class="result">
  <a href="/v6/cpu/12347">Apple M3 Max</a>
  <span>3,123</span>
  <span>21,456</span>
  <span>18,901</span>
</div>
</body></html>
"""

# HTML with JSON-LD
JSONLD_HTML = """
<html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "ItemList",
  "itemListElement": [
    {
      "@type": "ListItem",
      "name": "Intel Core i9-13900K Processor",
      "description": "Single-Core Score: 2345, Multi-Core Score: 18765",
      "singleCoreScore": 2345,
      "multiCoreScore": 18765
    },
    {
      "@type": "ListItem",
      "name": "AMD Ryzen 9 7950X Processor",
      "description": "Single-Core Score: 2567, Multi-Core Score: 20123",
      "singleCoreScore": 2567,
      "multiCoreScore": 20123
    }
  ]
}
</script>
</head><body></body></html>
"""

EMPTY_HTML = "<html><body></body></html>"


# ===========================================================================
# Helper function tests
# ===========================================================================


class TestHelpers:
    def test_detect_vendor_intel(self):
        assert detect_vendor("Intel Core i9-13900K") == "Intel"
        assert detect_vendor("Core i9-13900K") == "Intel"

    def test_detect_vendor_amd(self):
        assert detect_vendor("AMD Ryzen 9 7950X") == "AMD"

    def test_detect_vendor_apple(self):
        assert detect_vendor("Apple M3 Max") == "Apple"
        # M3 without "Apple" prefix still matches
        assert detect_vendor("M3 Max") == "Apple"

    def test_parse_score(self):
        assert parse_score("2,345") == 2345
        assert parse_score("18,765") == 18765
        assert parse_score("—") is None
        assert parse_score("N/A") is None
        assert parse_score("") is None


# ===========================================================================
# GeekbenchScraper tests
# ===========================================================================


class TestGeekbenchScraper:
    def test_source_id(self):
        assert GeekbenchScraper.SOURCE_ID == "geekbench"

    def test_vendors(self):
        assert len(GeekbenchScraper.VENDORS) >= 5
        assert "Intel" in GeekbenchScraper.VENDORS
        assert "AMD" in GeekbenchScraper.VENDORS

    def test_priority(self):
        assert GeekbenchScraper.PRIORITY == 35

    def test_rate_limiter_configured(self):
        scraper = GeekbenchScraper()
        assert scraper.rate_limiter is not None
        assert scraper.rate_limiter._requests_per_sec == 0.3
        assert scraper.rate_limiter._burst == 1

    def test_expected_fields(self):
        fields = GeekbenchScraper.expected_fields()
        assert len(fields) >= 6
        assert "name" in fields
        assert "single_core_score" in fields
        assert "multi_core_score" in fields
        assert "gpu_compute_score" in fields

    def test_parse_html_result_rows(self):
        """Parse HTML div.result rows with benchmark scores."""
        scraper = GeekbenchScraper()
        results = scraper.parse(SAMPLE_HTML)
        assert len(results) >= 1

        # Check Intel result
        intel_results = [r for r in results if "Intel" in r.vendor or "i9" in r.fields.get("name", "")]
        if intel_results:
            r = intel_results[0]
            assert isinstance(r, ChipScrapeResult)
            assert r.source_id == "geekbench"
            fields = r.fields
            assert "single_core_score" in fields or "multi_core_score" in fields

    def test_parse_jsonld(self):
        """Parse JSON-LD structured data."""
        scraper = GeekbenchScraper()
        results = scraper.parse(JSONLD_HTML)
        assert len(results) >= 2

        # Check results
        for r in results:
            assert isinstance(r, ChipScrapeResult)
            assert r.source_id == "geekbench"
            fields = r.fields
            assert "vendor" in fields
            assert fields["vendor"] in ("Intel", "AMD")

    def test_parse_empty_html(self):
        scraper = GeekbenchScraper()
        results = scraper.parse(EMPTY_HTML)
        assert len(results) == 0

    def test_parse_invalid_html(self):
        scraper = GeekbenchScraper()
        results = scraper.parse("<html><body><div>no data</div></body></html>")
        assert len(results) == 0

    def test_produces_chip_scrape_result(self):
        scraper = GeekbenchScraper()
        results = scraper.parse(JSONLD_HTML)
        for r in results:
            assert isinstance(r, ChipScrapeResult)
            assert r.source_id == "geekbench"

    @patch("soc_db.scraping.sources.geekbench.HTTPSource")
    def test_fetch_calls_robots(self, mock_http_cls):
        """fetch() should check robots.txt."""
        mock_http = MagicMock()
        mock_http.fetch.return_value = "<html></html>"
        mock_http_cls.return_value = mock_http

        scraper = GeekbenchScraper()
        scraper._robots_checker = MagicMock()
        scraper._robots_checker.can_fetch.return_value = True

        scraper.fetch()
        scraper._robots_checker.can_fetch.assert_called_once()
