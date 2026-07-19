# Project Research Summary

**Project:** soc-db v3.0 Full SoC Coverage
**Domain:** Large-scale SoC/CPU database — multi-source data collection and deduplication pipeline
**Researched:** 2026-07-19
**Confidence:** HIGH

## Executive Summary

soc-db v3.0 transforms the project from a Wikipedia-scraping + enrichment pipeline (1761 chips, avg completeness 0.19–0.54) into a multi-source data collection engine targeting **5000+ SoCs** with **95-field depth (≥0.80 completeness)**. Research confirms no single source provides all 95 fields — achieving full depth requires merging across 6+ source types (vendor official, Wikipedia, benchmark sites, spec aggregators, Linux kernel) with deterministic deduplication and field-level provenance tracking.

The recommended approach is a **plugin-based scraper framework** with staged capability tiers (basic HTTP → TLS-impersonated → headless browser → API), a **deterministic dedup engine** using vendor-specific model number extractors (NOT probabilistic record linkage — SoCs have unique identifiers like SM8550, MT6983, T8130), and **field-level provenance tracking** so every value carries its source. The SoC domain's natural unique keys make probabilistic methods (recordlinkage, splink) counterproductive — they introduce uncertainty where none exists.

**Key risks and mitigations:** (1) Legal exposure from scraping vendor sites — mitigate with Phase 0 legal review and source compliance matrix before any new scrapers. (2) Naive rate limiting causing cascading blocks — mitigate with per-source rate limiters, exponential backoff with jitter, and proxy rotation. (3) Uncontrolled data duplication from different chip naming conventions — mitigate with canonical UUID identity system and multi-strategy matching pipeline. (4) GitHub Pages integrity destroyed by accidental writes — mitigate with filesystem boundary guard in Phase 0.

## Key Findings

### Recommended Stack

v3.0 adds six new production dependencies and two dev dependencies, all chosen to avoid framework overhead while solving specific scraping challenges. The key architectural insight: **no Scrapy, no Selenium, no PostgreSQL** — the project's existing lightweight patterns (module-per-source, SQLite, dict-based data) are the right foundation; v3.0 just needs better HTTP, parsing, and merge tooling.

**Core technologies:**
- **httpx >=0.28**: Async HTTP client for all new scrapers — full async/await, HTTP/2, connection pooling. Does NOT replace `requests` for existing Wikipedia/Apple scrapers (backward compat).
- **curl-cffi >=0.15**: Anti-bot HTTP with browser TLS/JA3 impersonation — handles GSMArena, DeviceSpecifications, Geekbench where plain `requests`/`httpx` gets 403'd. Replaces Selenium/Playwright for anti-bot.
- **selectolax >=0.4**: 3-4x faster HTML parsing than BeautifulSoup+lxml (Cython Lexbor backend) for high-volume pages (5000+ device pages). Keep BeautifulSoup for existing scrapers where forgiving parsing is needed.
- **tenacity >=9.0**: Decorator-based retry with exponential backoff and jitter — replaces ad-hoc `time.sleep(1)` in common.py.
- **jmespath >=1.1**: JSON query expressions for vendor API responses — much cleaner than nested `dict.get()` chains.
- **rapidfuzz >=3.6**: C-accelerated fuzzy string matching for name-based dedup fallback (10-100x faster than difflib). Only used when deterministic model-number matching fails.
- **pandas >=2.2** (dev only): Bulk statistical quality checks for CI/audit scripts — NOT at runtime.
- **GitPython >=3.1** (dev only): Programmatic git operations for auto-PR workflow (commit/push only, not complex rebase).

**What NOT to add (strong recommendations):** No Scrapy (framework overhead for simple page scraping), no Selenium/Playwright (curl-cffi handles anti-bot at HTTP layer), no recordlinkage/splink (deterministic keys exist), no PostgreSQL/DuckDB (SQLite handles 5000 records easily), no Celery/Airflow (batch operation, not task queue), no Great Expectations (Pydantic validators suffice).

See [STACK.md](STACK.md) for full dependency table, version requirements, and anti-recommendation rationale.

### Expected Features

**Must have (table stakes):**
- **5000+ SoC entries** across all major vendors — Qualcomm (800+), MediaTek (600+), Intel (1000+), AMD (400+), Samsung (200+), plus embedded/IoT/RISC-V
- **95-field depth with completeness ≥0.80** — currently 65 scored fields; 30 new fields to add for v3.0 (market_segment, AI TOPS, charging, WiFi/BT/USB versions, AV1 decode, PCIe, etc.)
- **Per-chip data source tracking** — every field value traceable to its source (vendor official vs Wikipedia vs benchmark)
- **Deduplicated chip entries** — one canonical entry per chip with aliases, not 4 duplicates from different sources
- **Cross-source validation** — detect and report when sources disagree on field values
- **Regular data refresh** — automated pipeline on schedule, not static database
- **Benchmark data integration** — Geekbench, AnTuTu, NotebookCheck scores
- **CLI with advanced filtering** — `soc-db list --process 4nm --npu-min 20`
- **REST API comparison endpoint** — `GET /v1/chips/{id}/compare?with=id2`
- **Data quality dashboards** — per-vendor completeness, field coverage, conflict detection

**Should have (competitive):**
- **Per-field source tracking with conflict scoring** — every value knows its source; when sources disagree, a confidence score is computed. No other chip database does this.
- **Unified chip categorization across mobile/desktop/server/embedded/IoT** — most databases specialize; soc-db spans all categories.
- **Automated vendor page generation** — completeness heatmaps, trend charts per vendor
- **Chip lifecycle tracking** — announced → sampling → production → end-of-life
- **Benchmark trend analysis** — "How does Snapdragon 8 Gen series compare across generations?"
- **Linux DeviceTree and BSP data** — deep hardware data from kernel upstream
- **Community contribution pipeline** — users submit corrections via PRs, CI validates and merges

**Defer (v3.1+):**
- Device ↔ SoC cross-reference database (50000+ relationships)
- Real-time chip announcement monitoring
- Chip photography / die shots
- Power/efficiency curve modeling
- Competitive performance analysis ("X is 15% faster than Y")

See [FEATURES.md](FEATURES.md) for full feature table, source authority hierarchy, field coverage by source matrix, and MVP phase ordering recommendation.

### Architecture Approach

The architecture introduces a **`scraping/` subpackage** as a first-class architectural component — peer of `db/` and `enrich/` — replacing the current `scripts/` directory. Five core patterns form the foundation:

**Major components:**
1. **BaseScraper + SourceRegistry** — Plugin-based source registration. Each source inherits from `BaseScraper`, registers with `SourceRegistry` via class attributes. Registry maintains ordered priority list per vendor. Adding a new source is a single-file change.
2. **ProvenanceTracker** — Field-level source attribution stored as `{field_name: source_id}` dict per chip. Enables "where did this process node come from?" queries at runtime. Conflicts are logged, not silently overwritten.
3. **ConflictResolver** — Resolves field-level conflicts using a per-vendor priority matrix (official > Wikipedia > aggregator). Supports field-level overrides. Every conflict is logged and auditable.
4. **BatchEnricher** — Processes chips in 500-chip batches with checkpoint files. Crash recovery without re-enriching 5000 chips from scratch. Progress logging with ETA.
5. **QualityScorer** — Post-pipeline analysis producing per-vendor and per-field quality reports. Separate from per-chip completeness scoring (different consumers, different cadence).

**Pipeline stages are explicitly separated:** `scrape → merge → enrich → write → validate → report`. No more enrichment inside write operations. No more silent last-writer-wins.

**Anti-patterns eliminated:** Duplicate `scripts/common.py` (deleted), in-place enrichment mutation during write (separated stages), global mutable `VENDOR_KNOWLEDGE` (injected dependency), ID-from-name slug collisions (canonical UUIDs), last-writer-wins merge (provenance-tracked conflict resolution).

See [ARCHITECTURE.md](ARCHITECTURE.md) for full component details, code examples, data flow diagrams, and scaling considerations for 5K/20K/100K chips.

### Critical Pitfalls

1. **Naive rate limiting causes cascading blocks** — Current `time.sleep(1)` with single User-Agent will trigger 429s/403s across all sources at 5000-chip scale. Mitigation: per-source rate limiters with exponential backoff, proxy rotation, User-Agent rotation, failure isolation per source, curl-cffi for TLS fingerprint randomization. **Address in Phase 1.**

2. **Data provenance loss — undoable merges** — Current merge is destructive last-writer-wins with no field-level source tracking. Mitigation: ProvenanceTracker stores `{field: source}` per chip, ConflictResolver uses explicit priority, conflict reports generated for human review, immutable audit log of field changes. **Address in Phase 2 before any multi-source merge.**

3. **Deduplication nightmare — same chip, different names** — "Snapdragon 8 Gen 2" / "SM8550-AB" / "qcom,sm8550" / "Qualcomm SM8550-AB Snapdragon 8 Gen 2" are the same chip. Current exact-string matching creates 4 duplicates. Mitigation: canonical UUID identity, multi-strategy matching pipeline (model number regex → fuzzy name → alias table → Wikidata QID → hardware characteristics), merge policy with official-source priority. **Address in Phase 3 — the most complex phase.**

4. **Legal exposure from unauthorized scraping** — GSMArena, DeviceSpecifications, vendor sites likely prohibit scraping. SOC-DB/1.0 User-Agent makes scraping trivially traceable. Mitigation: legal audit per source before scraping, prefer official APIs, robots.txt compliance, C&D response plan, separate scraper identity for problematic targets. **Address in Phase 0 — gate before any new scrapers.**

5. **False positives in Auto-PR workflow** — Every trivial change (whitespace, formatting, Wikipedia bot edits) generates a PR, causing reviewer burnout. Mitigation: semantic diff engine comparing parsed values (not raw JSON), change classification (noise/auto-merge/human-review), review batching, confidence-based thresholds. **Address in Phase 7 — add auto-PR only after change classification is built.**

See [PITFALLS.md](PITFALLS.md) for all 12 pitfalls with warning signs, recovery strategies, and pitfall-to-phase mapping.

## Implications for Roadmap

Based on combined research across all four dimensions (stack, features, architecture, pitfalls), the recommended phase structure has 8 phases with a mandatory Phase 0 gate:

### Phase 0: Governance & Safety Gates
**Rationale:** Legal exposure and GitHub Pages integrity are non-negotiable prerequisites. Adding scrapers without legal review risks C&D letters. Writing to `docs/` without a guard destroys the public-facing site. Both must be resolved before any production code changes.
**Delivers:** Source compliance matrix (legal basis for each target), filesystem boundary guard for `docs/`, robots.txt caching framework, C&D response plan, scraper identity strategy.
**Addresses features:** Not directly (governance), but enables all subsequent phases.
**Avoids pitfalls:** #7 (Legal exposure), #12 (GitHub Pages integrity).
**Stack usage:** None — purely process and guard code.

### Phase 1: Scraper Framework & Infrastructure
**Rationale:** The framework (BaseScraper, SourceRegistry, rate limiting, anti-bot tiers, schema drift detection) must exist before any new scrapers are built. This is the foundation everything else depends on. Migrating ONE source (Wikipedia) proves the pattern works.
**Delivers:** BaseScraper ABC, SourceRegistry with per-vendor priority, per-source rate limiter with exponential backoff, curl-cffi anti-bot tier (browser TLS impersonation), selectolax parsing tier, schema drift detection with yield thresholds, Wikipedia scraper migrated to prove pattern.
**Addresses features:** Scraper framework infrastructure (prerequisite for all data collection).
**Avoids pitfalls:** #1 (Naive rate limiting), #2 (Schema drift), #8 (Anti-bot blocking).
**Stack additions:** httpx, curl-cffi, selectolax, tenacity, jmespath.
**Research flag:** STANDARD PATTERNS — well-documented scraping patterns, curl-cffi docs are excellent. Skip `--research-phase`.

### Phase 2: Provenance Data Model & Schema Expansion
**Rationale:** Provenance tracking MUST be in the data model before any multi-source merge happens. The 30 new fields should be added early so scrapers can target them directly (rather than backfilling later). Schema expansion and provenance model are independent concerns that can be done in parallel.
**Delivers:** Provenance field added to Chip model, 30 new fields (market_segment, AI TOPS, charging, WiFi/BT/USB versions, AV1 decode, PCIe, etc.), ProvenanceTracker + ConflictResolver wired into pipeline, legacy provenance backfill (all existing values marked `legacy_v2`), completeness scoring updated for new fields, freshness metadata.
**Addresses features:** 95-field schema (DATA-02), per-chip data source tracking (table stakes), cross-source validation data model.
**Avoids pitfalls:** #4 (Data provenance loss), #9 (Stale data inconsistency).
**Stack usage:** Pydantic v2 validators (already have), rapidfuzz ready for fallback matching.
**Research flag:** NEEDS RESEARCH — field weight design for quality scoring is subjective and needs discussion. Which fields matter most? Should be discussed before implementation.

### Phase 3: Dedup Engine & Source Migration
**Rationale:** With provenance model in place, the DedupEngine can safely merge data across sources. All 4 existing scrapers (Wikipedia, Apple, Linux DeviceTree, Wikidata SPARQL) migrate to the framework, proving dedup works with real multi-source data before new sources are added. The `scripts/` directory with duplicate logic is eliminated.
**Delivers:** DedupEngine with canonical UUID identity, vendor-specific Matcher subclasses (model number regex per vendor), alias registry, multi-strategy matching pipeline, migrated scrapers: wikipedia, apple, linux_dt, wikidata_sparql, `scripts/` directory deleted, `scripts/common.py` eliminated.
**Addresses features:** Deduplicated chip entries (table stakes), cross-source validation, source authority hierarchy.
**Avoids pitfalls:** #3 (Dedup nightmare), #10 (Slug collisions).
**Stack additions:** rapidfuzz (for fuzzy name matching fallback).
**Research flag:** NEEDS RESEARCH — vendor-specific model number regex patterns need validation against actual data from each vendor. The patterns in STACK.md are starting points but need testing against real chip listings.

### Phase 4: Batch Processing, Quality Scoring & Performance
**Rationale:** At 5000+ chips with 14 enrichment modules, the naive `enrich_all()` becomes a bottleneck. Batch processing with checkpointing, performance profiling, and staging the API loading must be done before the big data influx from new scrapers. Quality scoring provides the feedback loop for data health.
**Delivers:** BatchEnricher with 500-chip checkpoints, QualityScorer (per-vendor/per-field metrics), API performance fixes (staged loading, async I/O), profiling report, `data/quality_reports/` directory, p95 API response < 200ms at 5000 chips.
**Addresses features:** Quality dashboards (table stakes), performance regression prevention, data health metrics (fill_rate, source_diversity, conflict_rate, staleness).
**Avoids pitfalls:** #5 (API performance regression), #11 (Enrichment performance).
**Stack additions:** pandas (dev dependency for quality analysis).
**Research flag:** STANDARD PATTERNS — batch processing, checkpointing, and performance profiling are well-understood. Skip `--research-phase`. But DO profile first — don't guess bottlenecks.

### Phase 5: High-Value New Scrapers (P0/P1)
**Rationale:** With framework proven, schema ready, dedup working, and performance profiled, it's time for maximum data impact. TechPowerUp (4398 chips, 30+ fields), NotebookCheck (1000+ chips, 20 benchmarks), and Geekbench Browser (2000+ entries) are the highest-value targets. These structured-HTML sources are scrapable at Tier 2 (httpx + curl-cffi), no headless browser needed.
**Delivers:** TechPowerUp scraper (+2000-3000 chips), NotebookCheck scraper (20 benchmarks per chip), Geekbench Browser scraper (multi-core scores), chip count raised to ~4000-4500, benchmark data for 60%+ of chips.
**Addresses features:** 5000+ chips (DATA-01), benchmark integration (table stakes), benchmark coverage ≥0.60 target.
**Avoids pitfalls:** #8 (Anti-bot blocking — curl-cffi handles Tier 2 targets), #1 (Rate limiting — per-source rate limiter in Phase 1).
**Stack usage:** httpx + curl-cffi + selectolax + tenacity + jmespath.
**Research flag:** NEEDS RESEARCH — TechPowerUp may offer licensed API access; check before building scraper. Geekbench Browser rate limiting behavior is uncertain — needs experimentation. NotebookCheck URL patterns need verification.

### Phase 6: Vendor Official Site Scrapers (P1)
**Rationale:** Vendor official sites (Qualcomm Developer Network, MediaTek, Apple, Intel ARK, AMD) have the richest per-chip data (50+ fields) but are the hardest targets — likely requiring Tier 3 (headless browser) or Tier 4 (official API/manual). Do these after the high-value structured sources are proven and the pipeline is stable.
**Delivers:** Qualcomm scraper (400+ chips, 50+ fields, official authoritative data), MediaTek scraper (300+ chips, 50+ fields), Intel ARK scraper (1500+ chips, lifecycle status), AMD scraper (400+ chips), Apple Tech Specs (80+ chips), chip count raised to ~5000-5500.
**Addresses features:** Vendor-official data priority (table stakes), field depth for process_node, NPU, connectivity, lifecycle tracking.
**Avoids pitfalls:** #7 (Legal — must verify API access options first), #8 (Anti-bot — likely Cloudflare protected, may need Tier 3/4).
**Stack usage:** May need Playwright for JS-heavy vendor sites (if curl-cffi insufficient), official APIs if available.
**Research flag:** NEEDS RESEARCH — Qualcomm Developer Network may require partner API key. MediaTek site is a JS-heavy SPA (confirmed). Intel ARK has complex dynamic pages. Each vendor needs individual research before scraper implementation.

### Phase 7: Additional Scrapers + Auto-PR CI Workflow
**Rationale:** GSMArena/DeviceSpecs add mobile-oriented fields (camera, display, charging) but have lower per-chip field depth. Auto-PR workflow should come late to avoid reviewer burnout — by Phase 7, the data pipeline is stable, conflict resolution is proven, and change classification can be built on real patterns.
**Delivers:** GSMArena scraper (mobile field enrichment), DeviceSpecifications scraper, Auto-PR workflow with semantic diff engine, change classification (noise/auto-merge/human-review), review batching, quality diff in PR body, `nightly-scrape.yml` GHA workflow.
**Addresses features:** Regular data refresh (table stakes), community contribution pipeline, auto-PR workflow.
**Avoids pitfalls:** #6 (Auto-PR false positives — change classification built before automation).
**Stack additions:** GitPython + gh CLI (dev).
**Research flag:** STANDARD PATTERNS — GitHub Actions workflows are well-documented. Change classification is custom but straightforward. Skip `--research-phase`.

### Phase 8: Quality Dashboards, API & UI Upgrades
**Rationale:** UI/API improvements depend on fully populated data and stable schema. Building comparison endpoints and quality dashboards before data is complete would produce empty/wrong results. Web UI efficiency for 5000+ chips is the final polish.
**Delivers:** `GET /v1/chips/{id}/compare` endpoint, per-vendor completeness reports with heatmaps, conflict detection dashboard, web UI typeahead search, CLI extended flags (`--process`, `--npu-min`, `--benchmark-min`), Open Data export (JSON/CSV/Parquet).
**Addresses features:** Comparison API (table stakes), quality dashboards (table stakes), CLI filtering, web UI upgrade (DATA-06).
**Avoids pitfalls:** #5 (API performance — fixed in Phase 4, verified here).
**Research flag:** STANDARD PATTERNS — FastAPI endpoints, chart.js dashboards, static site updates are well-understood. Skip `--research-phase`.

### Phase Ordering Rationale

- **Phase 0 first** because legal and safety issues block everything — without a compliance matrix, new scrapers risk C&D; without the GitHub Pages guard, a stray write takes down the public site.
- **Phase 1 before any new scrapers** because the framework (rate limiting, anti-bot, schema drift detection) is the foundation. Adding scrapers without these guarantees immediate failure at scale.
- **Phase 2 before dedup or merge** because provenance tracking must be in the data model before multi-source merging begins. Retrofitting provenance is much harder than building it in.
- **Phase 3 before new source scrapers** because dedup must be proven with existing sources before adding 4-5 new ones that each have different naming conventions.
- **Phase 4 before big data influx** because batch processing and performance optimization prevent the bottleneck that would hit at 4000+ chips.
- **Phase 5 (high-value scrapers) before Phase 6 (vendor sites)** because structured-HTML targets are easier and deliver more chips faster. Vendor sites are harder but deliver deeper field data.
- **Phase 7 (auto-PR) late** because change classification requires real data patterns to train on. Auto-PR without classification causes reviewer burnout.
- **Phase 8 last** because UI/API enhancements depend on complete, stable data.

### Research Flags

Phases needing deeper research during planning:
- **Phase 2:** Field weight design for quality scoring is subjective — needs stakeholder input on which fields matter most
- **Phase 3:** Vendor-specific model number regex patterns need validation against real chip listings from each vendor
- **Phase 5:** TechPowerUp API/licensing options, Geekbench Browser rate limiting behavior, NotebookCheck URL stability
- **Phase 6:** Each vendor site needs individual research — Qualcomm API key availability, MediaTek SPA structure, Intel ARK page patterns

Phases with standard patterns (skip `--research-phase`):
- **Phase 1:** Scraping patterns are well-documented, curl-cffi/httpx docs are excellent
- **Phase 4:** Batch processing and checkpointing are well-understood patterns
- **Phase 7:** GitHub Actions workflows are well-documented
- **Phase 8:** FastAPI endpoints and static site updates are standard

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All recommendations verified against official docs and PyPI release status. Anti-recommendations backed by domain analysis. Version requirements current as of Jul 2026. |
| Features | HIGH | Source landscape verified via live inspection of TechPowerUp (4398 CPUs), NotebookCheck, GSMArena, DeviceSpecifications. Field coverage matrix cross-referenced from actual page structure. Vendor estimates based on Wikipedia list sizes + industry knowledge. |
| Architecture | HIGH | Patterns are proven in production scraping pipelines (plugin registration, field-level provenance, conflict resolution with priority matrix). Anti-patterns identified from existing codebase analysis. Scaling considerations realistic for 5K target. |
| Pitfalls | HIGH | Based on established scraping industry patterns, documented legal cases (hiQ Labs, Craigslist, Feist, Van Buren), and existing codebase analysis of common.py, scraper_wikipedia.py, rate_limit.py. Each pitfall has specific warning signs and recovery strategies. |

**Overall confidence:** HIGH

### Gaps to Address

- **Vendor site HTML structure unverified:** Actual HTML of Qualcomm Developer Network, MediaTek product pages, and Apple Tech Specs may differ from documented expectations. Some may require Playwright (despite anti-recommendation). Address during Phase 5/6 per-source implementation.
- **Geekbench Browser rate limiting:** Known to return 403 for automated access, but exact rate limit thresholds unknown. Address via experimentation in Phase 5 — start at 0.2 req/s, escalate.
- **TechPowerUp licensing:** Their CPU database may offer REST API + MCP access for licensing. Check before building scraper in Phase 5. If API is affordable, prefer it over scraping.
- **NotebookCheck URL stability:** URLs contain non-semantic IDs. Search-based approach may be needed rather than direct URL patterns. Verify during Phase 5.
- **Intel ARK database complexity:** 1500+ CPUs with dynamic page structure. May need separate research phase before Phase 6 implementation.
- **Field weight calibration for quality scoring:** Which 95 fields matter most? Quality metric design requires stakeholder input. Address during Phase 2 planning.

## Sources

### Primary (HIGH confidence)
- httpx v0.28.1 official docs — async HTTP client patterns
- curl-cffi v0.15.0 PyPI — TLS impersonation, browser fingerprinting
- selectolax v0.4.11 docs — Lexbor HTML parser performance benchmarks
- tenacity v9.1.4 docs — retry strategies, exponential backoff
- jmespath v1.1.0 spec — JSON query expression patterns
- rapidfuzz v3.6+ docs — C-accelerated string matching, performance comparisons
- Existing codebase: `scraper_wikipedia.py`, `scraper_apple.py`, `common.py`, `rate_limit.py`, `models.py` (Chip model), `enrich/*.py` (14 modules)
- TechPowerUp CPU Database live inspection (4398 CPUs, 30+ fields)
- NotebookCheck Mobile Processor Benchmark List live inspection (1000+ processors, 20 benchmarks)
- GSMArena live inspection (10000+ phones with chipset field)
- DeviceSpecifications live inspection (processor list with specs)
- PROJECT.md v3.0 requirements and constraints

### Secondary (MEDIUM confidence)
- Qualcomm Developer Network page structure from secondary sources (actual HTML unverified)
- MediaTek product page structure from press/review analysis (JS-heavy SPA confirmed)
- Apple Tech Specs architecture from support.apple.com inspection (structure varies per product line)
- Geekbench Browser scraping analysis (403 verified, JSON-LD documented)

### Tertiary (LOW confidence — needs validation)
- TechPowerUp API licensing terms (may need to negotiate)
- Geekbench Browser rate limit thresholds (unknown — must experiment)
- NotebookCheck URL pattern stability (may change without notice)
- Intel ARK database full structure (dynamic pages, may need Playwright)

---

*Research completed: 2026-07-19*
*Ready for roadmap: yes*
