---
phase: 13
plan: 01
type: sequential
title: Vendor Official Scrapers
description: Create official vendor site scrapers for Qualcomm, MediaTek, Intel/AMD, and Apple and register them in the SourceRegistry
autonomous: true
requirements: [VENDOR-01, VENDOR-02, VENDOR-03, VENDOR-04]
---

# Phase 13 Plan 01: Vendor Official Scrapers

## Objective
Create four vendor-official scrapers (Qualcomm Developer Network, MediaTek, Intel ARK + AMD, Apple Tech Specs) and register them in the SourceRegistry so that they are auto-discovered alongside existing scrapers. Each scraper respects robots.txt, uses per-source rate limiting, applies multi-strategy dedup via DedupEngine, and tracks provenance for every field.

## Context

### Source Legal Status (from data/LEGAL.md)

| Source | robots.txt | Legal Basis | Risk Level |
|--------|-----------|-------------|------------|
| Qualcomm developer.qualcomm.com | Not restrictive | Developer ToS requires registration | Medium |
| MediaTek mediatek.com | Not tested | Fair use of factual specs | Medium |
| Intel ARK ark.intel.com | Allow: /content/ Disallow: /search/ | Public product database | Low-Medium |
| AMD amd.com | Crawl-delay: 10 | Fair use of factual specs | Medium |
| Apple support.apple.com/specs | Not tested | Press releases / factual data | Medium |

All scrapers will check robots.txt before fetching via `BaseScraper.check_robots()`.

### Architecture Pattern
Each scraper extends `BaseScraper`, implements `fetch()` and `parse()`, uses `HTTPSource` for tiered HTTP fetching, configures per-source rate limiting, and produces `list[ChipScrapeResult]`. The `run()` lifecycle method orchestrates fetch → parse → dedup → write.

---

## Tasks

### Task 1 — Qualcomm scraper

**Type:** `auto`
**Files:** `src/soc_db/scraping/sources/qualcomm.py` (create)

Create `QualcommScraper` for Qualcomm Developer Network Snapdragon product pages.

**SOURCE_ID:** `"qualcomm"`
**VENDORS:** `["Qualcomm"]`
**PRIORITY:** `30`

**Rate limit:** 0.5 req/s, burst 2 (conservative for official site)

**Extract fields:**
- Identity: name, model (SM prefix, e.g. SM8750), vendor="Qualcomm"
- CPU: cores, cluster_config, clock_max, clock_min, architecture
- Process: process_nm
- GPU: gpu (e.g. "Adreno 830")
- NPU: npu, ai_ops
- Modem: modem, modem_dl, modem_ul
- Memory: memory_type, memory_max
- Connectivity: wifi, bluetooth, usb
- Media: display_max, camera_max, isps, video_decode, video_encode
- Lifecycle: year, announced
- Charging: charging (quick charge version)

**Approach:** Since Qualcomm Developer Network pages may require JS rendering, use BeautifulSoup-based static HTML parsing with a structured fallback. The scraper targets static spec tables on Qualcomm's product pages.

**Verification:**
1. `QualcommScraper` is a `BaseScraper` subclass
2. `fetch()` returns HTML string
3. `parse()` parses sample HTML into at least 1 `ChipScrapeResult`
4. Results contain expected fields (name, vendor, model, cores, etc.)
5. Source ID is "qualcomm"

---

### Task 2 — MediaTek scraper

**Type:** `auto`
**Files:** `src/soc_db/scraping/sources/mediatek.py` (create)

Create `MediaTekScraper` for MediaTek official product pages.

**SOURCE_ID:** `"mediatek"`
**VENDORS:** `["MediaTek"]`
**PRIORITY:** `30`

**Rate limit:** 0.5 req/s, burst 2

**Extract fields:**
- Identity: name, model (MT prefix, e.g. MT6989), vendor="MediaTek"
- CPU: cores, cluster_config, clock_max, architecture
- Process: process_nm
- GPU: gpu (e.g. "Immortalis-G720", "Mali-G710")
- NPU: npu, ai_ops
- Memory: memory_type, memory_max, memory_clock
- Display: display_max
- Connectivity: wifi, bluetooth
- Modem: modem, modem_dl, modem_ul
- Lifecycle: year, announced

**Verification:**
1. `MediaTekScraper` is a `BaseScraper` subclass
2. `fetch()` returns HTML string
3. `parse()` parses sample HTML into at least 1 `ChipScrapeResult`
4. Results contain expected fields
5. Source ID is "mediatek"

---

### Task 3 — Intel ARK + AMD scraper

**Type:** `auto`
**Files:** `src/soc_db/scraping/sources/intel_amd.py` (create)

Create `IntelAMDScraper` for Intel ARK and AMD official product spec pages.

**SOURCE_ID:** `"intel_amd"`
**VENDORS:** `["Intel", "AMD"]`
**PRIORITY:** `30`

**Rate limit:** 1.0 req/s, burst 3

**Extract fields:**
- Identity: name, model, vendor (auto-detected from name)
- CPU: cores, threads, clock (base), boost, cache (l2_cache, l3_cache)
- Process: process_nm, tdp
- Memory: memory_type, memory_max
- GPU: gpu (integrated graphics)
- Socket: socket
- Lifecycle: year

**Shared parsing utilities:**
- `detect_vendor(name)`: returns "Intel" or "AMD"
- `parse_core_thread(text)`: parse "8 / 16" into (8, 16)
- `parse_clock(text)`: parse "3.4 GHz / 5.4 GHz" into (3.4, 5.4)
- `parse_tdp(text)`: parse "125 W" → 125
- `parse_cache(text)`: parse "30 MB" → "30 MB"

**Verification:**
1. `IntelAMDScraper` is a `BaseScraper` subclass
2. Helper functions work correctly
3. `parse()` handles both Intel and AMD sample HTML
4. Results contain expected fields

---

### Task 4 — Apple Tech Specs scraper (new)

**Type:** `auto`
**Files:** `src/soc_db/scraping/sources/apple_techspecs.py` (create)

Create `AppleTechSpecsScraper` for Apple's official Tech Specs pages (support.apple.com/specs).

**SOURCE_ID:** `"apple_techspecs"`
**VENDORS:** `["Apple"]`
**PRIORITY:** `40`

**Rate limit:** 1.0 req/s, burst 2

**Extract fields:**
- Identity: name, model (T-prefix or APL prefix), vendor="Apple"
- CPU: performance_cores, efficiency_cores (total cores = sum), architecture
- Clock: clock_max, max_freq
- GPU: gpu (core count, e.g. "Apple GPU (10-core)")
- NPU: npu (Neural Engine core count)
- Memory: memory_bandwidth, memory_type (unified memory)
- Process: process_nm
- TDP: tdp
- Lifecycle: year

**Note:** This is a new scraper distinct from the existing Wikipedia-based `AppleScraper` (source_id="apple"). It targets Apple's official spec pages to get more authoritative M-series data.

**Verification:**
1. `AppleTechSpecsScraper` is a `BaseScraper` subclass
2. `fetch()` returns HTML string
3. `parse()` parses sample HTML into at least 1 `ChipScrapeResult`
4. Results contain Apple M-series specific fields
5. Source ID is "apple_techspecs"

---

### Task 5 — Register scrapers in SourceRegistry

**Type:** `auto`
**Files:**
- `src/soc_db/scraping/__init__.py` (edit)
- `src/soc_db/scraping/sources/__init__.py` (edit)

**Actions:**
1. Add imports for all 4 new scrapers in `__init__.py`
2. Add them to `__all__`
3. Ensure `SourceRegistry.discover()` will auto-discover them from the `sources` package

The registry auto-discovers scrapers via `pkgutil.walk_packages` on the sources package. Since each module exports a class that inherits `BaseScraper` with a unique `SOURCE_ID`, the registration is automatic. The explicit imports in `__init__.py` ensure they're available for direct import.

**Verification:**
1. After importing, all 4 scrapers are discoverable
2. SourceRegistry can find them by SOURCE_ID
3. No import errors

---

### Task 6 — Create tests

**Type:** `auto`
**Files:**
- `tests/unit/test_scraping_qualcomm.py` (create)
- `tests/unit/test_scraping_mediatek.py` (create)
- `tests/unit/test_scraping_intel_amd.py` (create)
- `tests/unit/test_scraping_apple_techspecs.py` (create)

**Test coverage per scraper:**
1. SOURCE_ID, VENDORS, PRIORITY class attributes
2. Rate limiter configured with expected parameters
3. `parse()` with sample HTML returns expected results
4. `parse()` with empty/invalid HTML returns empty list
5. Helper functions (where applicable)
6. Dedup works
7. Produces `ChipScrapeResult` instances with correct source_id
8. `fetch()` calls robots check

---

### Task 7 — Write SUMMARY.md

**Type:** `auto`
**Files:**
- `.planning/phases/13-vendor-official-scrapers/13-01-SUMMARY.md` (create)

---

## Verification

1. All 4 scraper files exist and are importable
2. All scrapers are registered in SourceRegistry
3. All tests pass (488 existing + new tests)
4. Each scraper has proper SOURCE_ID, VENDORS, PRIORITY, and RATE_LIMIT_CONFIG
5. Each scraper produces ChipScrapeResult with proper fields
6. Provenance tracking is integrated via the `write()` lifecycle
7. No GitHub Pages files touched

## Success Criteria

- [ ] Qualcomm scraper created and registered
- [ ] MediaTek scraper created and registered
- [ ] Intel/AMD scraper created and registered
- [ ] Apple Tech Specs scraper created and registered
- [ ] All scrapers auto-discoverable via SourceRegistry
- [ ] Tests pass for all 4 scrapers
- [ ] All existing tests still pass
- [ ] SUMMARY.md written
