"""SourceRegistry — auto-discovery of BaseScraper subclasses by naming convention.

Discovery convention: any module in ``soc_db.scraping.sources`` that exports
a class with a ``SOURCE_ID`` class attribute gets registered. The class must
be a subclass of :class:`soc_db.scraping.base.BaseScraper` (enforced at
registration time).
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from soc_db.scraping.base import BaseScraper

logger = logging.getLogger(__name__)


class SourceRegistry:
    """Registry of BaseScraper subclasses, auto-discovered by convention.

    Usage::

        SourceRegistry.clear()
        scrapers = SourceRegistry.discover()
        wikipedia_cls = SourceRegistry.get("wikipedia")
    """

    _registry: dict[str, type[BaseScraper]] = {}

    # ── registration ────────────────────────────────────────────────────

    @classmethod
    def register(cls, scraper_cls: type[BaseScraper]) -> None:
        """Register a scraper class by its ``SOURCE_ID``.

        Args:
            scraper_cls: A subclass of BaseScraper with a non-empty ``SOURCE_ID``.

        Raises:
            TypeError: If *scraper_cls* is not a BaseScraper subclass.
            ValueError: If ``SOURCE_ID`` is empty or ``None``.
        """
        from soc_db.scraping.base import BaseScraper as _BaseScraper

        if not isinstance(scraper_cls, type) or not issubclass(scraper_cls, _BaseScraper):
            raise TypeError(
                f"{scraper_cls!r} is not a subclass of BaseScraper"
            )

        source_id = scraper_cls.SOURCE_ID
        if not source_id:
            raise ValueError(
                f"{scraper_cls!r} has an empty SOURCE_ID"
            )

        cls._registry[source_id] = scraper_cls
        logger.info("Registered scraper: %s (%s)", source_id, scraper_cls.__name__)

    # ── discovery ───────────────────────────────────────────────────────

    @classmethod
    def discover(cls) -> dict[str, type[BaseScraper]]:
        """Scan ``soc_db.scraping.sources`` for BaseScraper subclasses.

        Returns:
            A copy of the registry dict after discovery.
        """
        try:
            sources_module = importlib.import_module("soc_db.scraping.sources")
        except ImportError:
            logger.info("soc_db.scraping.sources package not found — no scrapers to discover")
            return dict(cls._registry)

        # Iterate over all modules in the sources package
        if hasattr(sources_module, "__path__"):
            for _importer, modname, _ispkg in pkgutil.walk_packages(
                sources_module.__path__, prefix="soc_db.scraping.sources."
            ):
                try:
                    mod = importlib.import_module(modname)
                except ImportError as exc:
                    logger.warning("Could not import %s: %s", modname, exc)
                    continue

                # Find all BaseScraper subclasses in the module
                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, _get_base_scraper())
                        and attr is not _get_base_scraper()
                    ):
                        try:
                            cls.register(attr)
                        except (TypeError, ValueError) as exc:
                            logger.warning(
                                "Skipping %s.%s: %s", modname, attr_name, exc
                            )

        return dict(cls._registry)

    # ── queries ─────────────────────────────────────────────────────────

    @classmethod
    def get(cls, source_id: str) -> type[BaseScraper] | None:
        """Return the scraper class for *source_id*, or ``None``."""
        return cls._registry.get(source_id)

    @classmethod
    def all(cls) -> list[type[BaseScraper]]:
        """Return all registered scraper classes sorted by SOURCE_ID."""
        return [
            cls._registry[sid]
            for sid in sorted(cls._registry.keys())
        ]

    # ── lifecycle ───────────────────────────────────────────────────────

    @classmethod
    def clear(cls) -> None:
        """Clear all registered scrapers (useful for testing)."""
        cls._registry.clear()


def _get_base_scraper() -> type[BaseScraper]:
    """Lazy import of BaseScraper to avoid circular imports at module level."""
    from soc_db.scraping.base import BaseScraper

    return BaseScraper
