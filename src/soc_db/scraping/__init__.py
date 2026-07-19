"""Scraper framework — plugin-based scrapers with rate limiting, HTTP escalation, and drift detection.

This package provides the abstract scraper contract (BaseScraper),
per-source rate limiting (PerSourceRateLimiter), tiered HTTP fetching
(HTTPSource), auto-discovery (SourceRegistry), and schema drift detection
(SchemaDriftDetector).
"""

from soc_db.scraping.base import BaseScraper, ChipScrapeResult
from soc_db.scraping.drift import DriftReport, SchemaDriftDetector
from soc_db.scraping.rate_limit import PerSourceRateLimiter
from soc_db.scraping.registry import SourceRegistry
from soc_db.scraping.source import HTTPSource
from soc_db.scraping.sources.wikipedia import WikipediaScraper

__all__ = [
    "BaseScraper",
    "ChipScrapeResult",
    "DriftReport",
    "HTTPSource",
    "PerSourceRateLimiter",
    "SchemaDriftDetector",
    "SourceRegistry",
    "WikipediaScraper",
]
