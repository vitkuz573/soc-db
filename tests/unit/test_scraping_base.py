"""Unit tests for BaseScraper ABC and ChipScrapeResult dataclass."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from soc_db.common import USER_AGENT
from soc_db.robots import RobotsChecker
from soc_db.scraping.base import BaseScraper, ChipScrapeResult, SCRAPER_USER_AGENTS
from soc_db.scraping.rate_limit import PerSourceRateLimiter


# ===========================================================================
# ChipScrapeResult
# ===========================================================================


class TestChipScrapeResult:
    def test_construction(self):
        r = ChipScrapeResult(
            name="Snapdragon 8 Gen 1",
            vendor="Qualcomm",
            model="SM8450",
            fields={"cpu": "Cortex-X2", "gpu": "Adreno 730", "year": 2021},
            source_id="wikipedia",
            raw_html="<html>...</html>",
        )
        assert r.name == "Snapdragon 8 Gen 1"
        assert r.vendor == "Qualcomm"
        assert r.model == "SM8450"
        assert r.fields["cpu"] == "Cortex-X2"
        assert r.source_id == "wikipedia"
        assert r.raw_html == "<html>...</html>"

    def test_defaults(self):
        r = ChipScrapeResult(name="Test Chip", vendor="TestVendor")
        assert r.model is None
        assert r.fields == {}
        assert r.source_id == ""
        assert r.raw_html is None

    def test_source_id_passthrough(self):
        r = ChipScrapeResult(name="Chip A", vendor="Vendor A", source_id="custom")
        assert r.source_id == "custom"


# ===========================================================================
# BaseScraper
# ===========================================================================


class TestBaseScraper:
    def test_cannot_instantiate_abc(self):
        """BaseScraper() should raise TypeError (abstract methods)."""
        with pytest.raises(TypeError):
            BaseScraper()  # type: ignore[abstract]

    def test_concrete_subclass(self):
        """A minimal subclass with fetch+parse can be instantiated."""
        class ConcreteScraper(BaseScraper):
            SOURCE_ID = "test"
            VENDORS = ["TestVendor"]

            def fetch(self) -> str:
                return "raw"

            def parse(self, raw: str) -> list[ChipScrapeResult]:
                return [ChipScrapeResult(name="Chip1", vendor="TestVendor")]

        scraper = ConcreteScraper()
        assert scraper.SOURCE_ID == "test"
        assert scraper.VENDORS == ["TestVendor"]
        assert scraper.source_name == "test"

    def test_run_calls_lifecycle(self, monkeypatch):
        """Verify run() calls expected lifecycle steps in order."""
        calls = []

        class LifecycleScraper(BaseScraper):
            SOURCE_ID = "lifecycle"
            VENDORS = ["TestVendor"]

            def fetch(self) -> str:
                calls.append("fetch")
                return "<html/>"

            def parse(self, raw: str) -> list[ChipScrapeResult]:
                calls.append("parse")
                return [ChipScrapeResult(name="Chip1", vendor="TestVendor")]

            def dedup(self, results: list[ChipScrapeResult]) -> list[ChipScrapeResult]:
                calls.append("dedup")
                return results

            def write(self, results: list[ChipScrapeResult]) -> None:
                calls.append("write")

        monkeypatch.setattr("time.sleep", lambda s: None)
        scraper = LifecycleScraper()
        results = scraper.run()

        assert calls == ["fetch", "parse", "dedup", "write"]
        assert len(results) == 1

    def test_check_robots_passes(self, monkeypatch):
        """check_robots returns True when robots.txt allows."""

        class AllowScraper(BaseScraper):
            SOURCE_ID = "test"
            VENDORS = ["TestVendor"]

            def fetch(self) -> str:
                return ""
            def parse(self, raw: str) -> list[ChipScrapeResult]:
                return []

        mock_checker = MagicMock(spec=RobotsChecker)
        mock_checker.can_fetch.return_value = True
        scraper = AllowScraper(robots_checker=mock_checker)
        assert scraper.check_robots("http://example.com/page") is True
        mock_checker.can_fetch.assert_called_once()

    def test_check_robots_blocked(self, monkeypatch):
        """check_robots raises PermissionError when disallowed."""

        class DenyScraper(BaseScraper):
            SOURCE_ID = "test"
            VENDORS = ["TestVendor"]

            def fetch(self) -> str:
                return ""
            def parse(self, raw: str) -> list[ChipScrapeResult]:
                return []

        mock_checker = MagicMock(spec=RobotsChecker)
        mock_checker.can_fetch.return_value = False
        scraper = DenyScraper(robots_checker=mock_checker)
        with pytest.raises(PermissionError, match="robots.txt disallows"):
            scraper.check_robots("http://example.com/forbidden")

    def test_dedup_removes_duplicates(self):
        """dedup removes results with duplicate (vendor, model, name)."""

        class DedupScraper(BaseScraper):
            SOURCE_ID = "test"
            VENDORS = ["VendorA"]

            def fetch(self) -> str:
                return ""
            def parse(self, raw: str) -> list[ChipScrapeResult]:
                return []

        scraper = DedupScraper()
        results = [
            ChipScrapeResult(name="Chip A", vendor="VendorA", model="M1"),
            ChipScrapeResult(name="Chip B", vendor="VendorA", model="M2"),
            ChipScrapeResult(name="Chip A", vendor="VendorA", model="M1"),  # dup
            ChipScrapeResult(name="Chip C", vendor="VendorA", model="M3"),
        ]
        deduped = scraper.dedup(results)
        assert len(deduped) == 3

    def test_write_calls_write_vendor_file(self, monkeypatch):
        """write() groups by vendor and calls write_vendor_file per vendor."""
        written = []

        def fake_write_vendor_file(vendor: str, chips: list[dict[str, Any]]) -> None:
            written.append((vendor, chips))

        monkeypatch.setattr(
            "soc_db.scraping.base.write_vendor_file", fake_write_vendor_file
        )

        class WriteScraper(BaseScraper):
            SOURCE_ID = "test"
            VENDORS = ["VendorA", "VendorB"]

            def fetch(self) -> str:
                return ""
            def parse(self, raw: str) -> list[ChipScrapeResult]:
                return []

        scraper = WriteScraper()
        results = [
            ChipScrapeResult(name="Chip A", vendor="VendorA", fields={"id": "a", "name": "Chip A"}),
            ChipScrapeResult(name="Chip B", vendor="VendorB", fields={"id": "b", "name": "Chip B"}),
            ChipScrapeResult(name="Chip C", vendor="VendorA", fields={"id": "c", "name": "Chip C"}),
        ]
        scraper.write(results)
        assert len(written) == 2
        vendors_written = {v for v, _ in written}
        assert vendors_written == {"VendorA", "VendorB"}

    def test_user_agent_default(self):
        """Default user_agent comes from common.USER_AGENT."""

        class DefaultUAScraper(BaseScraper):
            SOURCE_ID = "nonexistent"
            VENDORS = ["TestVendor"]
            def fetch(self) -> str:
                return ""
            def parse(self, raw: str) -> list[ChipScrapeResult]:
                return []

        scraper = DefaultUAScraper()
        assert scraper.user_agent == USER_AGENT

    def test_user_agent_custom(self):
        """SCRAPER_USER_AGENTS lookup works for known sources."""

        class KnownScraper(BaseScraper):
            SOURCE_ID = "wikipedia"
            VENDORS = ["TestVendor"]
            def fetch(self) -> str:
                return ""
            def parse(self, raw: str) -> list[ChipScrapeResult]:
                return []

        scraper = KnownScraper()
        assert scraper.user_agent == SCRAPER_USER_AGENTS["wikipedia"]

    def test_rate_limiter_from_config(self):
        """RATE_LIMIT_CONFIG is used to construct the rate limiter."""

        class ConfigScraper(BaseScraper):
            SOURCE_ID = "configured"
            VENDORS = ["TestVendor"]
            RATE_LIMIT_CONFIG = {
                "requests_per_sec": 2.0,
                "burst": 5,
                "backoff_factor": 3.0,
            }
            def fetch(self) -> str:
                return ""
            def parse(self, raw: str) -> list[ChipScrapeResult]:
                return []

        scraper = ConfigScraper()
        assert scraper.rate_limiter._requests_per_sec == 2.0
        assert scraper.rate_limiter._burst == 5
        assert scraper.rate_limiter._backoff_factor == 3.0
