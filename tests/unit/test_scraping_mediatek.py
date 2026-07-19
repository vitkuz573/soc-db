"""Unit tests for MediaTekScraper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from soc_db.scraping.base import BaseScraper, ChipScrapeResult
from soc_db.scraping.sources.mediatek import (
    MediaTekScraper,
    parse_npu,
    parse_ai_ops,
)

# ===========================================================================
# Fixture HTML — simplified MediaTek product page HTML
# ===========================================================================

SAMPLE_HTML = {
    "https://www.mediatek.com/products/smartphones/dimensity-5g": """
<html><body>
<article class="product-item">
  <h2>Dimensity 9300</h2>
  <div class="specs">
    <p>CPU: 4x Cortex-X4 @ 3.25 GHz + 4x Cortex-A720</p>
    <p>GPU: Immortalis-G720</p>
    <p>Process: 3 nm</p>
    <p>APU: MediaTek APU 790</p>
    <p>Memory: LPDDR5T</p>
    <p>Display: 4K @ 120Hz</p>
    <p>Connectivity: Wi-Fi 7, Bluetooth 5.4</p>
  </div>
</article>
<article class="product-item">
  <h2>Dimensity 9200</h2>
  <div class="specs">
    <p>CPU: 1x Cortex-X3 @ 3.05 GHz + 3x Cortex-A715 + 4x Cortex-A510</p>
    <p>GPU: Immortalis-G715</p>
    <p>Process: 4 nm</p>
    <p>APU: MediaTek APU 690</p>
    <p>Memory: LPDDR5X</p>
    <p>Display: 4K @ 60Hz</p>
  </div>
</article>
</body></html>
""",
}

EMPTY_HTML = {"https://test.com": "<html><body></body></html>"}
INVALID_HTML = {"https://test.com": "<html><body><div>no chip data</div></body></html>"}


class TestMediaTekParsers:
    def test_parse_npu(self):
        result = parse_npu("MediaTek APU 790 AI Processor")
        assert result is not None
        assert "APU" in result

    def test_parse_npu_none(self):
        assert parse_npu("Just some text") is None

    def test_parse_ai_ops(self):
        assert parse_ai_ops("AI performance: 45 TOPS") == "45 TOPS"

    def test_parse_ai_ops_none(self):
        assert parse_ai_ops("No AI data") is None


class TestMediaTekScraper:
    def test_source_id(self):
        assert MediaTekScraper.SOURCE_ID == "mediatek"

    def test_vendors(self):
        assert MediaTekScraper.VENDORS == ["MediaTek"]

    def test_priority(self):
        assert MediaTekScraper.PRIORITY == 30

    def test_rate_limiter_configured(self):
        scraper = MediaTekScraper()
        assert scraper.rate_limiter is not None
        assert scraper.rate_limiter._burst == 2

    def test_parse_valid_html(self):
        scraper = MediaTekScraper()
        results = scraper.parse(SAMPLE_HTML)
        assert len(results) >= 1

        # Check first result
        r = results[0]
        assert r.vendor == "MediaTek"
        chip_name = r.fields.get("name", "")
        assert "Dimensity" in chip_name

    def test_parse_empty_html(self):
        scraper = MediaTekScraper()
        results = scraper.parse(EMPTY_HTML)
        assert len(results) == 0

    def test_parse_invalid_html(self):
        scraper = MediaTekScraper()
        results = scraper.parse(INVALID_HTML)
        assert len(results) == 0

    def test_produces_chip_scrape_result(self):
        scraper = MediaTekScraper()
        results = scraper.parse(SAMPLE_HTML)
        for r in results:
            assert isinstance(r, ChipScrapeResult)
            assert r.source_id == "mediatek"

    def test_dedup_works(self):
        scraper = MediaTekScraper()
        results = scraper.parse(SAMPLE_HTML)
        deduped = scraper.dedup(results + results)
        assert len(deduped) == len(results)

    def test_is_base_scraper_subclass(self):
        assert issubclass(MediaTekScraper, BaseScraper)

    @patch("soc_db.scraping.sources.mediatek.HTTPSource")
    def test_fetch_calls_robots(self, mock_http_cls):
        mock_http = MagicMock()
        mock_http.fetch.return_value = "<html></html>"
        mock_http_cls.return_value = mock_http

        scraper = MediaTekScraper()
        scraper._robots_checker = MagicMock()
        scraper._robots_checker.can_fetch.return_value = True

        scraper.fetch()
        assert scraper._robots_checker.can_fetch.call_count >= 1

    def test_gpu_extraction(self):
        """Verify GPU names are parsed correctly."""
        scraper = MediaTekScraper()
        results = scraper.parse(SAMPLE_HTML)
        for r in results:
            name = r.fields.get("name", "")
            gpu = r.fields.get("gpu", "")
            if "9300" in name:
                assert "Immortalis" in gpu
                break
