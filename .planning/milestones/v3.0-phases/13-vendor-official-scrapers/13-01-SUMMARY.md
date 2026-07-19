---
phase: 13
plan: 01
subsystem: scraping
tags: [scraping, qualcomm, mediatek, intel, amd, apple, vendor-sources]
requires: []
provides: [VENDOR-01, VENDOR-02, VENDOR-03, VENDOR-04]
affects: [SourceRegistry]
tech-stack:
  added:
    - BeautifulSoup (BS4 for HTML parsing — already in project)
    - re (regex-based field extraction)
  patterns:
    - BaseScraper subclass per vendor
    - HTTPSource for tiered HTTP fetching
    - Per-source rate limiting config
    - robots.txt compliance via check_robots()
    - BeautifulSoup-based HTML parsing with article/spec-table dual strategy
key-files:
  created:
    - src/soc_db/scraping/sources/qualcomm.py
    - src/soc_db/scraping/sources/mediatek.py
    - src/soc_db/scraping/sources/intel_amd.py
    - src/soc_db/scraping/sources/apple_techspecs.py
    - tests/unit/test_scraping_qualcomm.py
    - tests/unit/test_scraping_mediatek.py
    - tests/unit/test_scraping_intel_amd.py
    - tests/unit/test_scraping_apple_techspecs.py
  modified:
    - src/soc_db/scraping/__init__.py
decisions:
  - "AppleTechSpecsScraper created as separate scraper (source_id='apple_techspecs') rather than modifying the existing Wikipedia-based AppleScraper. Keeps concerns separated and both scrapers independently auto-discoverable."
  - "Intel/AMD combined into single scraper with shared parsing utilities (detect_vendor, parse_core_thread, parse_clock, etc.) since both target similar spec table patterns."
  - "Built-in knowledge base for Apple Silicon (M1-M4, A15-A18) used as fallback when Apple Tech Specs pages are unreachable, ensuring at least baseline data is always provided."
  - "Conservative rate limits (0.5 req/s for Qualcomm and MediaTek) to respect official vendor sites."
metrics:
  duration_minutes: 4
  tasks_completed: 7
  files_created: 8
  files_modified: 1
  tests_added: 71
status: complete
---

# Phase 13 Plan 01: Vendor Official Scrapers — Summary

**Objective:** Create four vendor-official scrapers (Qualcomm, MediaTek, Intel/AMD, Apple Tech Specs) and register them in the SourceRegistry.

**One-liner:** Four new BaseScraper subclasses for official vendor sources added with 71 tests, auto-discovered by SourceRegistry (11 total scrapers).

## Tasks Completed

| # | Task | Type | Commit | Files |
|---|------|------|--------|-------|
| 1 | Qualcomm scraper | `auto` | `216183f` | `src/soc_db/scraping/sources/qualcomm.py` |
| 2 | MediaTek scraper | `auto` | `bc42713` | `src/soc_db/scraping/sources/mediatek.py` |
| 3 | Intel ARK + AMD scraper | `auto` | `2b3ca78` | `src/soc_db/scraping/sources/intel_amd.py` |
| 4 | Apple Tech Specs scraper | `auto` | `c7e14bb` | `src/soc_db/scraping/sources/apple_techspecs.py` |
| 5 | Register in SourceRegistry | `auto` | `ccb4850` | `src/soc_db/scraping/__init__.py` |
| 6 | Create tests | `auto` | `19cfbc1` | 4 test files (71 tests) |
| 7 | Write SUMMARY.md | `auto` | *(this commit)* | `.planning/phases/13-vendor-official-scrapers/13-01-SUMMARY.md` |

## Scrapers Created

### 1. QualcommScraper (`qualcomm`)
- **SOURCE_ID:** `qualcomm`, **VENDORS:** `["Qualcomm"]`, **PRIORITY:** 30
- **Rate limit:** 0.5 req/s, burst 2
- **Targets:** Qualcomm Developer Network Snapdragon product pages
- **Fields extracted:** name, model (SM prefix), cores, cluster_config, clock_max, architecture, process_nm, GPU (Adreno), NPU, ai_ops, modem, modem_dl, memory_type, memory_max, wifi, bluetooth, display_max, camera_max, charging, year
- **Parsing strategy:** BeautifulSoup with article/card elements and spec tables

### 2. MediaTekScraper (`mediatek`)
- **SOURCE_ID:** `mediatek`, **VENDORS:** `["MediaTek"]`, **PRIORITY:** 30
- **Rate limit:** 0.5 req/s, burst 2
- **Targets:** MediaTek official product pages (Dimensity, Helio, Kompanio, Pentonic)
- **Fields extracted:** name, model (MT prefix), cores, cluster_config, clock_max, architecture, process_nm, GPU (Immortalis/Mali), NPU/APU, ai_ops, memory_type, memory_max, display_max, wifi, bluetooth, modem, year
- **Parsing strategy:** BeautifulSoup with product items and spec tables

### 3. IntelAMDScraper (`intel_amd`)
- **SOURCE_ID:** `intel_amd`, **VENDORS:** `["Intel", "AMD"]`, **PRIORITY:** 30
- **Rate limit:** 1.0 req/s, burst 3
- **Targets:** Intel ARK and AMD official product pages
- **Fields extracted:** name, model, cores, threads, clock, boost, tdp, process_nm, l2_cache, l3_cache, memory_type, memory_max, gpu, socket, year
- **Shared parsing utilities:** `detect_vendor()`, `parse_core_thread()`, `parse_clock()`, `parse_tdp()`, `parse_cache_size()`, `parse_memory_max()`, `parse_process_node()`
- **Intel process naming handled:** "Intel 7" → 10nm mapping

### 4. AppleTechSpecsScraper (`apple_techspecs`)
- **SOURCE_ID:** `apple_techspecs`, **VENDORS:** `["Apple"]`, **PRIORITY:** 40
- **Rate limit:** 1.0 req/s, burst 2
- **Targets:** Apple Tech Specs (support.apple.com/specs) for M-series and A-series
- **Fields extracted:** name, model (APL/T-prefix), performance_cores, efficiency_cores, total_cores, cluster_config, architecture, process_nm, GPU core count, Neural Engine, memory_bandwidth, memory_type, memory_max, tdp, year
- **Built-in knowledge base:** CPU core configs, GPU core counts, NPU cores, memory bandwidth, and TDP for M1-M4 and A15-A18 Pro chips
- **Fallback behavior:** When pages are unreachable, known chip data is always produced

## SourceRegistry Registration

All 4 scrapers are auto-discovered via `SourceRegistry.discover()`. Total registered scrapers: 11.

| SOURCE_ID | Class | Vendors | Priority |
|-----------|-------|---------|----------|
| apple | AppleScraper | Apple | 40 |
| **apple_techspecs** | **AppleTechSpecsScraper** | **Apple** | **40** |
| geekbench | GeekbenchScraper | Intel, AMD, Apple, Qualcomm, Samsung, MediaTek, HiSilicon | 35 |
| **intel_amd** | **IntelAMDScraper** | **Intel, AMD** | **30** |
| linux_dt | LinuxDTScraper | 40+ vendors | 60 |
| **mediatek** | **MediaTekScraper** | **MediaTek** | **30** |
| notebookcheck | NotebookCheckScraper | Intel, AMD, Qualcomm, Apple, Samsung, MediaTek, HiSilicon, Nvidia, Rockchip | 25 |
| **qualcomm** | **QualcommScraper** | **Qualcomm** | **30** |
| techpowerup | TechPowerUpScraper | 11 vendors | 20 |
| wikidata | WikidataScraper | 21 vendors | 70 |
| wikipedia | WikipediaScraper | 14 vendors | 30 |

## Verification

- [x] All 4 scraper files created and importable
- [x] All scrapers registered in SourceRegistry (auto-discovered)
- [x] 71 new tests pass
- [x] All 813 existing tests still pass (21 pre-existing failures due to missing deps: rapidfuzz, opentelemetry, SPARQLWrapper — same as before Phase 13)
- [x] Each scraper has proper SOURCE_ID, VENDORS, PRIORITY, and RATE_LIMIT_CONFIG
- [x] Each scraper produces ChipScrapeResult with proper fields and source_id
- [x] robots.txt compliance via `check_robots()` in all scrapers
- [x] Per-source rate limiting configured for all scrapers
- [x] Dedup via BaseScraper.dedup() (multi-key dedup)
- [x] Provenance tracking via `ChipScrapeResult.source_id` → integrated through write lifecycle
- [x] No GitHub Pages files touched (guard_path in write_vendor_file)

## Test Coverage

| Test File | Tests | Key Coverage |
|-----------|-------|-------------|
| `test_scraping_qualcomm.py` | 12 | Parse CPU/GPU/NPU, dedup, robots, AI OPS extraction |
| `test_scraping_mediatek.py` | 14 | Parse NPU/AI, GPU extraction, dedup, helpers |
| `test_scraping_intel_amd.py` | 22 | Vendor detection, core/clock/TDP/cache parsing, Intel+AMD parsing |
| `test_scraping_apple_techspecs.py` | 23 | Knowledge base validation, core/GPU/NPU/memory/TDP configs, fallback data |

## Requirements Satisfied

| Requirement | Description | Status |
|-------------|-------------|--------|
| VENDOR-01 | Qualcomm Developer Network scraper | ✅ QualcommScraper created |
| VENDOR-02 | MediaTek official product listing scraper | ✅ MediaTekScraper created |
| VENDOR-03 | Intel ARK / AMD product spec scrapers | ✅ IntelAMDScraper created |
| VENDOR-04 | Apple Tech Specs scraper (M-series deep data) | ✅ AppleTechSpecsScraper created |

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- [x] `src/soc_db/scraping/sources/qualcomm.py` exists (386 lines)
- [x] `src/soc_db/scraping/sources/mediatek.py` exists (385 lines)
- [x] `src/soc_db/scraping/sources/intel_amd.py` exists (501 lines)
- [x] `src/soc_db/scraping/sources/apple_techspecs.py` exists (466 lines)
- [x] `tests/unit/test_scraping_qualcomm.py` exists (147 lines)
- [x] `tests/unit/test_scraping_mediatek.py` exists (155 lines)
- [x] `tests/unit/test_scraping_intel_amd.py` exists (210 lines)
- [x] `tests/unit/test_scraping_apple_techspecs.py` exists (221 lines)
- [x] All 6 commits exist in git history
- [x] All 71 new tests pass
