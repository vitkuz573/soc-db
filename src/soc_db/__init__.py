"""soc-db: Enterprise-grade SoC / CPU identifier database.

Provides enrichment, lookup, and validation for 1746+ SoCs
from 37 vendors including Qualcomm, MediaTek, Samsung, Apple, and more.
"""

from __future__ import annotations

__version__ = "2.1.0-dev"

from soc_db.scraping import (
    BaseScraper,
    ChipScrapeResult,
    HTTPSource,
    PerSourceRateLimiter,
    SchemaDriftDetector,
    SourceRegistry,
    WikipediaScraper,
)

__all__ = [
    "BaseScraper",
    "ChipScrapeResult",
    "HTTPSource",
    "PerSourceRateLimiter",
    "SchemaDriftDetector",
    "SourceRegistry",
    "WikipediaScraper",
]
