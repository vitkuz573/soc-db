"""soc-db: Enterprise-grade SoC / CPU identifier database.

Provides enrichment, lookup, and validation for 1746+ SoCs
from 37 vendors including Qualcomm, MediaTek, Samsung, Apple, and more.
"""

from __future__ import annotations

__version__ = "2.1.0-dev"

from soc_db.scraping import (
    AppleScraper,
    BaseScraper,
    ChipScrapeResult,
    HTTPSource,
    LinuxDTScraper,
    PerSourceRateLimiter,
    SchemaDriftDetector,
    SourceRegistry,
    WikidataScraper,
    WikipediaScraper,
)

__all__ = [
    "AppleScraper",
    "BaseScraper",
    "ChipScrapeResult",
    "HTTPSource",
    "LinuxDTScraper",
    "PerSourceRateLimiter",
    "SchemaDriftDetector",
    "SourceRegistry",
    "WikidataScraper",
    "WikipediaScraper",
]
