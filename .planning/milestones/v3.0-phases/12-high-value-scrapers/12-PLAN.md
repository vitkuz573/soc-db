---
phase: 12
plan: high-value-scrapers
type: full
subsystem: scraping
tags: [techpowerup, notebookcheck, geekbench, benchmarks, spec-aggregator]
requirements: [BIGSRC-01, BIGSRC-02, BIGSRC-03]
objective: Build three high-value scraper sources (TechPowerUp, NotebookCheck, Geekbench Browser) following the existing BaseScraper framework. Each scraper integrates robots.txt checking, per-source rate limiting, HTTPSource tiered HTTP fetching, and provenance tracking. All scrapers are registered in SourceRegistry and have corresponding tests with fixture HTML.
---

# Phase 12: High-Value Scrapers — Execution Plan

## Context

Phase 12 builds three scraper sources that aggregate benchmark and spec data from the highest-value public sources:

1. **TechPowerUp** (BIGSRC-01) — 4398 chips, 30+ fields per entry. Static HTML at `techpowerup.com/cpu-specs/`. Extracts name, vendor, cores, threads, clock, boost, process, TDP, memory type, memory max, L2/L3 cache, graphics, year, socket.
2. **NotebookCheck** (BIGSRC-02) — 20+ benchmarks per chip. Extracts Cinebench, Geekbench, x265, Blender, 7-Zip scores and AI NPU TOPS.
3. **Geekbench Browser** (BIGSRC-03) — CPU/GPU benchmark scores per chip. Uses curl-cffi tier for 403 bypass. Extracts single-core, multi-core, GPU compute scores.

All scrapers follow the established pattern:
- Inherit from `BaseScraper`
- Use `HTTPSource` for tiered fetching
- Call `check_robots()` before network access
- Register via `SourceRegistry` (auto-discovered from `soc_db.scraping.sources`)
- Produce `ChipScrapeResult` instances
- Integrate provenance tracking
- Include test files with fixture HTML

## Tasks

### Task 1: TechPowerUp Scraper

**Type:** auto
**Files:**
- `src/soc_db/scraping/sources/techpowerup.py` (create)
- `src/soc_db/scraping/__init__.py` (update — export TechPowerUpScraper)
- `src/soc_db/scraping/sources/__init__.py` (no change needed, auto-discovered)

**Done criteria:**
- `TechPowerUpScraper` class exists with `SOURCE_ID = "techpowerup"`
- Hardware concurrency-based rate limiting (max(1, cpu_count//4) req/s, burst 3)
- `fetch()` downloads TechPowerUp CPU specs listing
- `parse()` extracts: name, vendor, cores, threads, clock, boost, process_nm, tdp, memory_type, memory_max, l2_cache, l3_cache, gpu, year, socket
- `expected_fields()` returns the full set of 16+ fields
- Uses `HTTPSource` for tiered HTTP
- Calls `check_robots()` per URL
- Produces `ChipScrapeResult` with provenance-ready fields

**Implementation:**
- TechPowerUp CPU specs page structure: a table with rows per CPU. Each row has cells for name, clock, cores/threads, TDP, memory, cache, socket, etc.
- Name parsing: extract vendor from known prefixes (Intel, AMD, Qualcomm, Apple, etc.)
- Model extraction: extract model number from name or cell
- Cache values: parse "L2$N/A", "L3$N/A" or "L2$size", "L3$size" patterns
- Clock/boost: parse "X GHz / Y GHz" or separate columns
- TDP: parse "X W" pattern

### Task 2: NotebookCheck Scraper

**Type:** auto
**Files:**
- `src/soc_db/scraping/sources/notebookcheck.py` (create)
- `src/soc_db/scraping/__init__.py` (update — export NotebookCheckScraper)

**Done criteria:**
- `NotebookCheckScraper` class exists with `SOURCE_ID = "notebookcheck"`
- Rate limit: 0.5 req/s, burst 2 (conservative for broad robots.txt)
- `fetch()` downloads the mobile processor benchmark list
- `parse()` extracts: name, vendor, cores, clock, tdp, and benchmark scores (cinebench_r23_mt, cinebench_r23_st, geekbench_6_mt, geekbench_6_st, x265, blender, 7zip, ai_tops_npu)
- `expected_fields()` returns benchmarks + spec fields
- Uses `HTTPSource`, `check_robots()`

**Implementation:**
- NotebookCheck benchmark list page: a `<table>` with rows per processor and columns for each benchmark
- Parse: BeautifulSoup HTML table parsing with column mapping
- Benchmark values may be empty/unknown strings — map to None
- NPU TOPS from "AI Performance" column if present

### Task 3: Geekbench Browser Scraper

**Type:** auto
**Files:**
- `src/soc_db/scraping/sources/geekbench.py` (create)
- `src/soc_db/scraping/__init__.py` (update — export GeekbenchScraper)

**Done criteria:**
- `GeekbenchScraper` class exists with `SOURCE_ID = "geekbench"`
- Rate limit: 0.3 req/s, burst 1 (conservative — 403-prone)
- `fetch()` searches Geekbench Browser for processor results
- `parse()` extracts: name, single_core_score, multi_core_score, gpu_compute_score
- Uses `HTTPSource` (curl-cffi tier handles 403)
- `expected_fields()` defined
- `check_robots()` called

**Implementation:**
- Geekbench Browser URL: `https://browser.geekbench.com/search?q={processor_name}`
- Returns JSON results page with benchmark entries
- Parse JSON response to extract processor name and scores
- Handle 403 at the HTTPSource level (curl-cffi with Chrome impersonation)

### Task 4: Register in SourceRegistry + Update __init__.py

**Type:** auto
**Files:**
- `src/soc_db/scraping/__init__.py` (update)

**Done criteria:**
- `soc_db.scraping.__init__` exports `TechPowerUpScraper`, `NotebookCheckScraper`, `GeekbenchScraper`
- `__all__` includes all three
- Auto-discovery via `SourceRegistry.discover()` finds all three

### Task 5: Tests for All Three Scrapers (with fixture HTML)

**Type:** auto
**Files:**
- `tests/unit/test_scraping_techpowerup.py` (create)
- `tests/unit/test_scraping_notebookcheck.py` (create)
- `tests/unit/test_scraping_geekbench.py` (create)

**Done criteria:**
- Each test file has fixture HTML representing realistic page structure
- Tests verify:
  - Scraper class has correct `SOURCE_ID`, `VENDORS`, `PRIORITY`
  - `expected_fields()` returns non-empty set
  - `parse()` returns `list[ChipScrapeResult]` with expected fields
  - `fetch()` returns appropriate type (str for TPU, dict for NBC/GB)
  - `check_robots()` is called
  - Empty/invalid HTML produces empty results (graceful handling)
  - Rate limiter is configured
- All existing tests (`pytest tests/ -x`) still pass after adding new files

## Verification

1. Run `pytest tests/unit/test_scraping_techpowerup.py tests/unit/test_scraping_notebookcheck.py tests/unit/test_scraping_geekbench.py -v` — all pass
2. Run `pytest tests/unit/test_scraping_registry.py -v` — still passes, auto-discovery works
3. Run `pytest tests/ -x` — all existing tests still pass
4. Confirm `from soc_db.scraping.sources.techpowerup import TechPowerUpScraper` works
5. Confirm all three scraper classes have unique SOURCE_IDs

## Output

- `SUMMARY.md` at `.planning/phases/12-high-value-scrapers/12-SUMMARY.md`
- STATE.md updated with Phase 12 progress
- ROADMAP.md updated
