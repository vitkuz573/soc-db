---
phase: 10-dedup-and-identity
plan: 02
subsystem: scraping
tags: [scrapers, migration, scripts, consolidation]
requires: []
provides: [AppleScraper, LinuxDTScraper, WikidataScraper, enrich/dts]
affects: [scripts/ (deleted), pyproject.toml]
tech-stack:
  added: [rapidfuzz>=3.6 in pyproject.toml]
  patterns: [BaseScraper subclass pattern]
key-files:
  created:
    - src/soc_db/scraping/sources/apple.py
    - src/soc_db/scraping/sources/linux_dt.py
    - src/soc_db/scraping/sources/wikidata.py
    - src/soc_db/enrich/dts.py
  modified:
    - src/soc_db/scraping/__init__.py
    - src/soc_db/__init__.py
    - pyproject.toml
  deleted:
    - scripts/ (12 files + __pycache__)
decisions:
  - AppleScraper reuses APPLE_CHIPS dict from src/soc_db/scraper_apple.py
  - LinuxDTScraper uses HTTPSource for GitHub API access instead of raw urlopen
  - WikidataScraper uses existing soc_db.wikidata SPARQL wrappers
  - enrich_from_dts.py main() CLI entry point NOT migrated (obsoleted by framework)
metrics:
  duration: ~20 min
  completed: "2026-07-19"
status: complete
---

# Phase 10 Plan 02: Scripts Consolidation — Summary

**One-liner:** Migrated Apple, Linux DT, and Wikidata scrapers to BaseScraper framework, moved DTS enrichment to `src/soc_db/enrich/dts.py`, and deleted the entire `scripts/` directory (12 files).

## What was built

1. **`src/soc_db/scraping/sources/apple.py`** — `AppleScraper(BaseScraper)`:
   - Reuses `APPLE_CHIPS` dict and `parse_tables()` from `src/soc_db/scraper_apple.py`
   - Fetches Apple A-series and M-series Wikipedia pages via `HTTPSource`
   - SOURCE_ID="apple", VENDORS=["Apple"], PRIORITY=40

2. **`src/soc_db/scraping/sources/linux_dt.py`** — `LinuxDTScraper(BaseScraper)`:
   - Reuses `VENDOR_MAP`, `ARM32_VENDOR_DIRS`, `VENDOR_SOC_PATTERNS` from scripts version
   - Uses `HTTPSource` for GitHub API access with rate limiting
   - SOURCE_ID="linux_dt", VENDORS=39, PRIORITY=60

3. **`src/soc_db/scraping/sources/wikidata.py`** — `WikidataScraper(BaseScraper)`:
   - Combines `scripts/scraper_wikidata.py` and `scripts/scraper_wikidata_sparql.py`
   - Uses existing `soc_db.wikidata` SPARQL query builders and cached execution
   - SOURCE_ID="wikidata", VENDORS=21, PRIORITY=70

4. **`src/soc_db/enrich/dts.py`** — DTS enrichment module:
   - `CORE_ARCH` mapping (34 entries) for CPU core → architecture
   - `VENDOR_DIR_MAP` (53 vendor directory mappings)
   - `enrich_from_dts(chip)` entry point for the enrichment pipeline
   - DTSI index via GitHub API with include chain following

5. **`pyproject.toml`** — Updated:
   - Added `rapidfuzz>=3.6` to dependencies
   - Removed `"scripts/"` from ruff exclude
   - Removed `"scripts.*"` from mypy overrides

6. **`scripts/` deleted** (12 files):
   `common.py`, `enrich_from_dts.py`, `extract_wikitables.py`, `migrate.py`,
   `parsers.py`, `pipeline.py`, `run_all.sh`, `scraper_apple.py`,
   `scraper_linux_dt.py`, `scraper_wikidata.py`, `scraper_wikidata_sparql.py`,
   `scraper_wikipedia.py`

## Commit History

- `cbd7228` — feat(10-dedup): migrate Apple/Linux DT/Wikidata scrapers to BaseScraper framework
- `3ddd8ec` — feat(10-dedup): migrate enrich_from_dts to src/soc_db/enrich/dts.py
- `d7d9648` — feat(10-dedup): remove legacy scripts/ directory per DEDUP-03

## Verification

- ✅ All 3 scrapers import cleanly with SOURCE_ID, VENDORS, fetch(), parse()
- ✅ `enrich/dts.py` imports with CORE_ARCH (34) and VENDOR_DIR_MAP (53)
- ✅ `scripts/` directory fully deleted from disk and git
- ✅ No `from scripts` or `import scripts` references remain in src/ or tests/
- ✅ `pyproject.toml` has `rapidfuzz>=3.6` and no `scripts/` in excludes
