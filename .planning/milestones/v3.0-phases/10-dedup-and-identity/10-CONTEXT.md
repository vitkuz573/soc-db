# Phase 10: Dedup & Identity - Context

**Gathered:** 2026-07-19
**Status:** Ready for planning

<domain>
## Phase Boundary

UUID-based canonical chip identity, multi-strategy matcher, and scripts/ consolidation.

Requirements: DEDUP-01, DEDUP-02, DEDUP-03

Success criteria:
1. Every chip has UUID from vendor + model-number fingerprint (not slug)
2. Multi-strategy matcher: exact -> alias -> Wikidata -> fuzzy, no false positives
3. All scrapers produce deduplicated entries through framework
4. scripts/ deleted, all functionality in scraping/ subpackage
</domain>

<code_context>
## Key Files
- src/soc_db/common.py — slug(), _match_existing(), write_vendor_file()
- src/soc_db/scraping/base.py — BaseScraper, ChipScrapeResult
- src/soc_db/scraping/source.py — HTTPSource
- src/soc_db/scraping/registry.py — SourceRegistry
- scripts/ — 13 legacy files to consolidate
</code_context>
