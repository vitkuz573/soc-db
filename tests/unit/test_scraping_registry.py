"""Unit tests for SourceRegistry."""

from __future__ import annotations

import pytest

from soc_db.scraping.base import BaseScraper, ChipScrapeResult
from soc_db.scraping.registry import SourceRegistry


# Concrete scraper for testing
class TestScraperA(BaseScraper):
    SOURCE_ID = "test_a"
    VENDORS = ["VendorA"]

    def fetch(self) -> str:
        return ""
    def parse(self, raw: str) -> list[ChipScrapeResult]:
        return []


class TestScraperB(BaseScraper):
    SOURCE_ID = "test_b"
    VENDORS = ["VendorB"]

    def fetch(self) -> str:
        return ""
    def parse(self, raw: str) -> list[ChipScrapeResult]:
        return []


class TestSourceRegistry:
    def setup_method(self):
        SourceRegistry.clear()

    def teardown_method(self):
        SourceRegistry.clear()

    def test_register(self):
        SourceRegistry.register(TestScraperA)
        assert SourceRegistry.get("test_a") is TestScraperA

    def test_register_duplicate_overwrites(self):
        SourceRegistry.register(TestScraperA)

        class TestScraperA2(BaseScraper):
            SOURCE_ID = "test_a"
            VENDORS = ["NewVendor"]
            def fetch(self) -> str:
                return ""
            def parse(self, raw: str) -> list[ChipScrapeResult]:
                return []

        SourceRegistry.register(TestScraperA2)
        # Last registration wins
        assert SourceRegistry.get("test_a") is TestScraperA2

    def test_register_non_scraper_raises(self):
        class NotAScraper:
            SOURCE_ID = "not_scraper"

        with pytest.raises(TypeError, match="not a subclass of BaseScraper"):
            SourceRegistry.register(NotAScraper)  # type: ignore[type-abstract]

    def test_register_empty_source_id_raises(self):
        class EmptyIDScraper(BaseScraper):
            SOURCE_ID = ""
            VENDORS = []
            def fetch(self) -> str:
                return ""
            def parse(self, raw: str) -> list[ChipScrapeResult]:
                return []

        with pytest.raises(ValueError, match="empty SOURCE_ID"):
            SourceRegistry.register(EmptyIDScraper)

    def test_get_registered(self):
        SourceRegistry.register(TestScraperA)
        assert SourceRegistry.get("test_a") is TestScraperA

    def test_get_not_found(self):
        assert SourceRegistry.get("nonexistent") is None

    def test_all(self):
        SourceRegistry.register(TestScraperA)
        SourceRegistry.register(TestScraperB)
        all_scrapers = SourceRegistry.all()
        assert len(all_scrapers) == 2
        # Should be sorted by SOURCE_ID
        assert all_scrapers[0].SOURCE_ID == "test_a"
        assert all_scrapers[1].SOURCE_ID == "test_b"

    def test_discover_empty(self):
        """If sources/ package doesn't exist, discover returns empty dict."""
        reg = SourceRegistry.discover()
        assert isinstance(reg, dict)

    def test_clear(self):
        SourceRegistry.register(TestScraperA)
        assert SourceRegistry.get("test_a") is not None
        SourceRegistry.clear()
        assert SourceRegistry.get("test_a") is None

    def test_re_discover_after_clear(self):
        SourceRegistry.register(TestScraperA)
        SourceRegistry.clear()
        reg = SourceRegistry.discover()
        assert isinstance(reg, dict)
