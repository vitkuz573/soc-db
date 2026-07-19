"""Scraper source implementations — one module per source.

New scrapers are discovered automatically by ``SourceRegistry.discover()``.
Each module should export a class that inherits from
:class:`soc_db.scraping.base.BaseScraper` and has a unique ``SOURCE_ID``.
"""
