"""Integration tests for WikipediaScraper through the full framework lifecycle.

These tests mock HTTP responses but exercise the real framework lifecycle
(fetch → parse → dedup → drift check → write).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from soc_db.common import write_vendor_file
from soc_db.scraping.base import ChipScrapeResult
from soc_db.scraping.drift import SchemaDriftDetector
from soc_db.scraping.registry import SourceRegistry
from soc_db.scraping.source import HTTPSource

# ── Fixture HTML ──────────────────────────────────────────────────────────────

FIXTURE_HTML = """<table class="wikitable">
<tbody>
<tr><th>SoC</th><th>CPU</th><th>GPU</th><th>Process</th><th>Memory</th><th>Modem</th><th>Year</th></tr>
<tr>
<td>Snapdragon 8 Gen 1 (SM8450)</td>
<td>1x 3.0 GHz Cortex-X2 + 3x 2.5 GHz Cortex-A710 + 4x 1.8 GHz Cortex-A510</td>
<td>Adreno 730</td>
<td>4 nm</td>
<td>LPDDR5</td>
<td>Snapdragon X65</td>
<td>2021</td>
</tr>
<tr>
<td>Snapdragon 8 Gen 2 (SM8550)</td>
<td>1x 3.2 GHz Cortex-X3 + 2x 2.8 GHz Cortex-A715 + 2x 2.8 GHz Cortex-A710 + 3x 2.0 GHz Cortex-A510</td>
<td>Adreno 740</td>
<td>4 nm</td>
<td>LPDDR5X</td>
<td>Snapdragon X70</td>
<td>2022</td>
</tr>
</tbody></table>"""


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def wikipedia_scraper(monkeypatch):
    """WikipediaScraper with all external calls mocked."""
    from soc_db.scraping.sources.wikipedia import WikipediaScraper

    mock_source = MagicMock(spec=HTTPSource)
    mock_source.fetch.return_value = FIXTURE_HTML

    mock_robots = MagicMock()
    mock_robots.can_fetch.return_value = True

    scraper = WikipediaScraper()
    scraper._http = mock_source
    scraper._robots_checker = mock_robots

    mock_rl = MagicMock()
    scraper._rate_limiter = mock_rl

    return scraper


@pytest.fixture(autouse=True)
def clear_registry():
    """Ensure clean registry before/after each test."""
    SourceRegistry.clear()
    yield
    SourceRegistry.clear()


# ── Tests ────────────────────────────────────────────────────────────────────


class TestWikipediaScraperFramework:
    def test_source_id_and_priority(self):
        from soc_db.scraping.sources.wikipedia import WikipediaScraper

        assert WikipediaScraper.SOURCE_ID == "wikipedia"
        assert WikipediaScraper.PRIORITY == 30

    def test_expected_fields_count(self):
        from soc_db.scraping.sources.wikipedia import WikipediaScraper

        fields = WikipediaScraper.expected_fields()
        assert len(fields) >= 10, f"Only {len(fields)} expected fields"
        assert "gpu" in fields
        assert "cores" in fields
        assert "year" in fields
        assert "process_nm" in fields

    def test_fetch_calls_http_source(self, wikipedia_scraper):
        """fetch() should populate _raw_pages via HTTPSource."""
        pages = wikipedia_scraper.fetch()
        assert len(pages) > 0
        assert wikipedia_scraper._raw_pages is pages
        # Should have fetched at least active vendors
        for vendor in ["Qualcomm", "MediaTek"]:
            assert vendor in pages

    def test_parse_returns_chip_results(self, wikipedia_scraper):
        """Parse fixture HTML should produce ChipScrapeResults."""
        pages = {"Qualcomm": FIXTURE_HTML}
        results = wikipedia_scraper.parse(pages)
        assert len(results) == 2
        for r in results:
            assert r.name
            assert r.vendor == "Qualcomm"
            assert r.source_id == "wikipedia"
            assert isinstance(r.fields, dict)
            assert len(r.fields) > 3

    def test_parse_chip_fields(self, wikipedia_scraper):
        """Parsed ChipScrapeResults should have meaningful fields."""
        pages = {"Qualcomm": FIXTURE_HTML}
        results = wikipedia_scraper.parse(pages)
        for r in results:
            assert "gpu" in r.fields or "cores" in r.fields
        # Check specific chip
        chip1 = [r for r in results if "8 Gen 1" in r.name]
        assert len(chip1) > 0
        assert chip1[0].fields.get("gpu") == "Adreno 730"

    def test_dedup_removes_duplicates(self, wikipedia_scraper):
        """Dedup with same data reduces 2->2 (no dups in fixture)."""
        pages = {"Qualcomm": FIXTURE_HTML}
        results = wikipedia_scraper.parse(pages)
        deduped = wikipedia_scraper.dedup(results)
        assert len(deduped) == len(results)  # no duplicates

    def test_drift_detection_cover_threshold(self, wikipedia_scraper):
        """Drift check should show good coverage for fixture data."""
        pages = {"Qualcomm": FIXTURE_HTML}
        results = wikipedia_scraper.parse(pages)
        detector = SchemaDriftDetector(threshold=0.8)
        detector.register_expected("wikipedia", wikipedia_scraper.expected_fields())
        report = detector.check("wikipedia", results)
        # Wikipedia fixture covers gp, cpu, process, memory, modem, year
        # out of 20 expected fields -> ~6/20 = 30%, but we have parsed
        # fields like id, name, vendor too
        assert report.drift_detected is True  # fixture is small
        assert report.coverage > 0

    def test_write_calls_write_vendor_file(self, wikipedia_scraper, monkeypatch):
        """write() should call write_vendor_file for each vendor."""
        written = []

        def fake_write(vendor, chips):
            written.append((vendor, chips))

        monkeypatch.setattr(
            "soc_db.scraping.sources.wikipedia.write_vendor_file", fake_write
        )

        results = [
            ChipScrapeResult(
                name="Snapdragon 8 Gen 1",
                vendor="Qualcomm",
                fields={"id": "sd8g1", "name": "Snapdragon 8 Gen 1", "cores": 8},
            ),
            ChipScrapeResult(
                name="Snapdragon 8 Gen 2",
                vendor="Qualcomm",
                fields={"id": "sd8g2", "name": "Snapdragon 8 Gen 2", "cores": 8},
            ),
        ]

        wikipedia_scraper.write(results)
        assert len(written) == 1  # both same vendor
        assert written[0][0] == "Qualcomm"
        assert len(written[0][1]) == 2

    def test_run_full_lifecycle(self, wikipedia_scraper, monkeypatch):
        """Full lifecycle produces results with all steps mocked."""
        written = []

        def fake_write(vendor, chips):
            written.append((vendor, chips))

        monkeypatch.setattr(
            "soc_db.scraping.sources.wikipedia.write_vendor_file", fake_write
        )

        results = wikipedia_scraper.run()
        assert len(results) > 0
        assert len(written) > 0
        for r in results:
            assert r.name
            assert r.vendor in wikipedia_scraper.VENDORS

    def test_auto_registration(self):
        """WikipediaScraper should be discoverable via SourceRegistry."""
        SourceRegistry.clear()
        reg = SourceRegistry.discover()
        assert "wikipedia" in reg
        cls = reg["wikipedia"]
        from soc_db.scraping.sources.wikipedia import WikipediaScraper

        assert cls is WikipediaScraper

    def test_legacy_backward_compat(self):
        """Legacy module functions still work."""
        from soc_db.scraper_wikipedia import (
            WIKI_PAGES,
            extract_chip_name,
            is_valid_chip_name,
            parse_standard_table,
            scrape_vendor,
        )

        assert "Qualcomm" in WIKI_PAGES
        # extract_chip_name preserves text if no brackets are present
        name = extract_chip_name("Snapdragon 8 Gen 1 (SM8450)")
        assert name and "Snapdragon" in name
        assert is_valid_chip_name("Snapdragon 8 Gen 2") is True
        assert is_valid_chip_name("n/a") is False
