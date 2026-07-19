---
phase: 12
plan: high-value-scrapers
subsystem: scraping
tags: [techpowerup, notebookcheck, geekbench, benchmarks, spec-aggregator]
requires: [phase-8-scraper-framework, phase-9-provenance-and-schema, phase-10-dedup-and-identity]
provides: [BIGSRC-01, BIGSRC-02, BIGSRC-03]
affects: [soc_db.scraping.sources]
tech-stack:
  added:
    - curl-cffi (tier 2 HTTP escalation, already in dependencies)
  patterns:
    - BaseScraper ABC + HTTPSource tiered HTTP + PerSourceRateLimiter
    - SchemaDriftDetector registration per source
    - ChipScrapeResult with provenance-ready fields
    - Auto-discovery via SourceRegistry naming convention
key-files:
  created:
    - src/soc_db/scraping/sources/techpowerup.py
    - src/soc_db/scraping/sources/notebookcheck.py
    - src/soc_db/scraping/sources/geekbench.py
    - tests/unit/test_scraping_techpowerup.py
    - tests/unit/test_scraping_notebookcheck.py
    - tests/unit/test_scraping_geekbench.py
  modified:
    - src/soc_db/scraping/__init__.py
key-decisions:
  - "TechPowerUp rate limit: max(1, cpu_count//4) req/s for fast desktop/server scraping with burst 3"
  - "NotebookCheck rate limit: 0.5 req/s, burst 2 (conservative due to broad robots.txt disallow)"
  - "Geekbench rate limit: 0.3 req/s, burst 1 (very conservative — site returns 403 on automated access)"
  - "Geekbench dual parse: JSON-LD first (structured data), HTML row fallback for non-JSON-LD pages"
  - "Vendor detection via name prefix matching rather than explicit vendor parameter"
metrics:
  tasks: 5
  files_created: 6
  files_modified: 1
  test_cases: 61
  existing_tests_passing: 738
  duration: ~30 min
  completed_date: "2026-07-19"
status: complete
---

# Phase 12: High-Value Scrapers — Summary

## One-Liner

Built three high-value scraper sources — TechPowerUp (17-field CPU specs), NotebookCheck (benchmark database), and Geekbench Browser (CPU/GPU scores) — following the existing BaseScraper framework with per-source rate limiting, robots.txt compliance, tiered HTTP fetching, and schema drift detection. All three auto-register in SourceRegistry and pass 61 new test cases.

## What Was Built

### TechPowerUp Scraper (`techpowerup`)

- **Source ID:** `techpowerup`
- **Priority:** 20 (highest spec density)
- **Rate limit:** hardware-concurrent `cpu_count//4` req/s, burst 3
- **Fields extracted (17):** name, vendor, model, cores, threads, clock, boost, process_nm, tdp, memory_type, memory_max, l2_cache, l3_cache, gpu, year, socket, id
- **Vendor detection:** 12 vendor prefixes (Intel, AMD, Qualcomm, Apple, Samsung, MediaTek, HiSilicon, Nvidia, Rockchip, Allwinner, Amlogic)
- **Parsing:** BeautifulSoup HTML table with cell-type-aware extraction
- **Helper functions:** `detect_vendor()`, `extract_model()`, `parse_tdp()`, `parse_cache_size()`, `parse_memory_max()`, `parse_clock()`, `parse_core_thread()`, `parse_process_node()`

### NotebookCheck Scraper (`notebookcheck`)

- **Source ID:** `notebookcheck`
- **Priority:** 25
- **Rate limit:** 0.5 req/s, burst 2 (conservative — broad robots.txt disallow)
- **Fields extracted (17):** name, vendor, model, cores, clock, tdp, cinebench_r23_mt, cinebench_r23_st, geekbench_6_mt, geekbench_6_st, geekbench_5_mt, geekbench_5_st, x265, blender, 7zip, ai_tops_npu, id
- **Column mapping:** Header-aware benchmark column detection via regex patterns
- **Benchmark value parsing:** Handles thousand-separators, N/A, dashes

### Geekbench Browser Scraper (`geekbench`)

- **Source ID:** `geekbench`
- **Priority:** 35
- **Rate limit:** 0.3 req/s, burst 1 (very conservative — 403-prone site)
- **Fields extracted (7):** name, vendor, model, single_core_score, multi_core_score, gpu_compute_score, id
- **Dual parse strategy:** JSON-LD structured data (ItemList with itemListElement) → HTML result row fallback
- **Anti-bot:** Relies on HTTPSource curl-cffi tier for Chrome TLS impersonation

### Registry Integration

All three scrapers auto-register via `SourceRegistry.discover()`. The `soc_db.scraping.__init__` exports all three classes. Total discovered scrapers: 7 (apple, geekbench, linux_dt, notebookcheck, techpowerup, wikidata, wikipedia).

### Tests (61 cases, 3 files)

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `test_scraping_techpowerup.py` | 21 | Helper functions, class attributes, parse valid/empty/invalid HTML, dedup, robots.txt |
| `test_scraping_notebookcheck.py` | 16 | Vendor detection, benchmark parsing, class attributes, parse with fixture, empty/invalid HTML |
| `test_scraping_geekbench.py` | 17 | Score parsing, vendor detection, class attributes, JSON-LD parsing, HTML row parsing, empty/invalid |
| Registry integration | 7 | Auto-discovery finds all 7 scrapers, registration still works |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all three scrapers are functional implementations with fixture testing.

## Threat Flags

None — no new network endpoints or auth paths introduced beyond what the plan specified.

## Self-Check

- [x] `src/soc_db/scraping/sources/techpowerup.py` created (357 lines)
- [x] `src/soc_db/scraping/sources/notebookcheck.py` created (334 lines)
- [x] `src/soc_db/scraping/sources/geekbench.py` created (361 lines)
- [x] `src/soc_db/scraping/__init__.py` updated (exports 3 new scrapers)
- [x] `tests/unit/test_scraping_techpowerup.py` created (21 tests)
- [x] `tests/unit/test_scraping_notebookcheck.py` created (16 tests)
- [x] `tests/unit/test_scraping_geekbench.py` created (17 tests)
- [x] All 61 new tests pass
- [x] All 738 existing unit tests still pass
- [x] All 11 integration scraping tests still pass
- [x] SourceRegistry auto-discovers all 7 scrapers
- [x] Unique SOURCE_IDs: techpowerup, notebookcheck, geekbench
- [x] Commit d6c03d0: TechPowerUp scraper
- [x] Commit fc281cb: NotebookCheck scraper
- [x] Commit c36fd50: Geekbench scraper
- [x] Commit 7b3ccbe: Registry/__init__.py
- [x] Commit 6b476ec: Tests

*Self-Check: PASSED*
