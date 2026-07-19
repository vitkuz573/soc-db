"""Unit tests for QualcommScraper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from soc_db.scraping.base import BaseScraper, ChipScrapeResult
from soc_db.scraping.sources.qualcomm import QualcommScraper

# ===========================================================================
# Fixture HTML — simplified Qualcomm product page HTML
# ===========================================================================

SAMPLE_HTML = {
    "https://www.qualcomm.com/products/application/smartphones/snapdragon-8-series": """
<html><body>
<article class="product-card">
  <h2>Snapdragon 8 Gen 2</h2>
  <div class="specs">
    <p>CPU: 1x Cortex-X3 @ 3.2 GHz + 4x Cortex-A715 + 3x Cortex-A510</p>
    <p>GPU: Adreno 740</p>
    <p>Process: 4 nm</p>
    <p>AI: Qualcomm AI Engine</p>
    <p>Memory: LPDDR5X</p>
    <p>Modem: Snapdragon X70 5G</p>
    <p>Wi-Fi: Wi-Fi 7, Bluetooth 5.3</p>
  </div>
</article>
<article class="product-card">
  <h2>Snapdragon 8 Gen 3</h2>
  <div class="specs">
    <p>CPU: 1x Cortex-X4 @ 3.3 GHz + 5x Cortex-A720 + 2x Cortex-A520</p>
    <p>GPU: Adreno 750</p>
    <p>Process: 4 nm</p>
    <p>AI: Qualcomm AI Engine with 45 TOPS</p>
    <p>Memory: LPDDR5X</p>
    <p>Modem: Snapdragon X75 5G</p>
    <p>Wi-Fi: Wi-Fi 7, Bluetooth 5.4</p>
  </div>
</article>
</body></html>
""",
}

EMPTY_HTML = {"https://test.com": "<html><body></body></html>"}
INVALID_HTML = {"https://test.com": "<html><body><div>no chip data here</div></body></html>"}


class TestQualcommScraper:
    def test_source_id(self):
        assert QualcommScraper.SOURCE_ID == "qualcomm"

    def test_vendors(self):
        assert QualcommScraper.VENDORS == ["Qualcomm"]

    def test_priority(self):
        assert QualcommScraper.PRIORITY == 30

    def test_rate_limiter_configured(self):
        scraper = QualcommScraper()
        assert scraper.rate_limiter is not None
        assert scraper.rate_limiter._burst == 2

    def test_parse_valid_html(self):
        scraper = QualcommScraper()
        results = scraper.parse(SAMPLE_HTML)
        assert len(results) >= 1

        # Check first result
        r = results[0]
        assert r.vendor == "Qualcomm"
        assert "Snapdragon" in r.fields.get("name", "")
        assert r.fields.get("gpu") == "Adreno 740"
        assert r.fields.get("architecture") == "ARMv8.2-A"

    def test_parse_empty_html(self):
        scraper = QualcommScraper()
        results = scraper.parse(EMPTY_HTML)
        assert len(results) == 0

    def test_parse_invalid_html(self):
        scraper = QualcommScraper()
        results = scraper.parse(INVALID_HTML)
        assert len(results) == 0

    def test_produces_chip_scrape_result(self):
        scraper = QualcommScraper()
        results = scraper.parse(SAMPLE_HTML)
        for r in results:
            assert isinstance(r, ChipScrapeResult)
            assert r.source_id == "qualcomm"

    def test_dedup_works(self):
        scraper = QualcommScraper()
        results = scraper.parse(SAMPLE_HTML)
        deduped = scraper.dedup(results + results)  # Duplicate
        assert len(deduped) == len(results)

    def test_is_base_scraper_subclass(self):
        assert issubclass(QualcommScraper, BaseScraper)

    @patch("soc_db.scraping.sources.qualcomm.HTTPSource")
    def test_fetch_calls_robots(self, mock_http_cls):
        mock_http = MagicMock()
        mock_http.fetch.return_value = "<html></html>"
        mock_http_cls.return_value = mock_http

        scraper = QualcommScraper()
        scraper._robots_checker = MagicMock()
        scraper._robots_checker.can_fetch.return_value = True

        scraper.fetch()
        assert scraper._robots_checker.can_fetch.call_count >= 1

    def test_parse_with_ai_ops(self):
        """Verify AI TOPS parsing from text."""
        scraper = QualcommScraper()
        results = scraper.parse(SAMPLE_HTML)
        for r in results:
            name = r.fields.get("name", "")
            if "8 Gen 3" in name:
                assert "45 TOPS" in r.fields.get("ai_ops", "")
                break
