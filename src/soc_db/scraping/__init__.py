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
from soc_db.scraping.sources.apple import AppleScraper
from soc_db.scraping.sources.apple_techspecs import AppleTechSpecsScraper
from soc_db.scraping.sources.geekbench import GeekbenchScraper
from soc_db.scraping.sources.intel_amd import IntelAMDScraper
from soc_db.scraping.sources.linux_dt import LinuxDTScraper
from soc_db.scraping.sources.mediatek import MediaTekScraper
from soc_db.scraping.sources.notebookcheck import NotebookCheckScraper
from soc_db.scraping.sources.qualcomm import QualcommScraper
from soc_db.scraping.sources.techpowerup import TechPowerUpScraper
from soc_db.scraping.sources.wikidata import WikidataScraper
from soc_db.scraping.sources.wikipedia import WikipediaScraper

__all__ = [
    "AppleScraper",
    "AppleTechSpecsScraper",
    "BaseScraper",
    "ChipScrapeResult",
    "DriftReport",
    "GeekbenchScraper",
    "HTTPSource",
    "IntelAMDScraper",
    "LinuxDTScraper",
    "MediaTekScraper",
    "NotebookCheckScraper",
    "PerSourceRateLimiter",
    "QualcommScraper",
    "SchemaDriftDetector",
    "SourceRegistry",
    "TechPowerUpScraper",
    "WikidataScraper",
    "WikipediaScraper",
]
