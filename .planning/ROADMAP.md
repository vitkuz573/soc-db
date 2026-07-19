# Roadmap: SoC Database (soc-db)

## Milestones

- ✅ **v2.1 Full Enterprise Hardening** — Phases 1-6 (shipped 2026-07-19)
- 🚧 **v3.0 Full SoC Coverage** — Phases 7-14 (in progress)

## Phases

<details>
<summary>✅ v2.1 Full Enterprise Hardening (Phases 1-6) — SHIPPED 2026-07-19</summary>

- [x] **Phase 1: REFAC** — Enrichment Module Extraction (4/4 plans) — completed 2026-07-19
- [x] **Phase 2: DB** — SQLite Database Migration (2/2 plans) — completed 2026-07-19
- [x] **Phase 3: ASYNC** — Async Data Layer (2/2 plans) — completed 2026-07-19
- [x] **Phase 4: RLIMIT** — Redis-Backed Rate Limiting (2/2 plans) — completed 2026-07-19
- [x] **Phase 5: OBSERVE** — OpenTelemetry Observability (2/2 plans) — completed 2026-07-19
- [x] **Phase 6: WIKIDATA** — Wikidata Knowledge Sync (1/1 plan) — completed 2026-07-19

</details>

### 🚧 v3.0 Full SoC Coverage (In Progress)

**Milestone Goal:** Collect ALL SoCs on the market with full 95-field profiles — no gaps.

- [x] **Phase 7: Governance & Safety** — Legal review and GitHub Pages filesystem boundary guard (completed 2026-07-19)
- [ ] **Phase 8: Scraper Framework** — Plugin-based scraper framework with anti-bot, rate limiting, and drift detection
- [ ] **Phase 9: Provenance & Schema** — Field-level provenance tracking with 30 new Chip model fields
- [ ] **Phase 10: Dedup & Identity** — UUID-based canonical chip identity with multi-strategy matcher
- [ ] **Phase 11: Batch Processing** — Batch enrichment with checkpointing, quality scoring, and API performance
- [ ] **Phase 12: High-Value Scrapers** — TechPowerUp, NotebookCheck, and Geekbench Browser scrapers
- [ ] **Phase 13: Vendor Official Scrapers** — Qualcomm, MediaTek, Intel/AMD, and Apple official scrapers
- [ ] **Phase 14: UI/API Polish** — Chip comparison API, quality dashboard, and CLI filtering enhancements

## Phase Details

### Phase 7: Governance & Safety

**Goal**: Legal and safety foundations are in place so scraping can proceed without risk to the project
**Depends on**: Nothing (first phase of v3.0)
**Requirements**: GOV-01, GOV-02
**Success Criteria** (what must be TRUE):

  1. Every scraping target has a documented legal basis (ToS reviewed, robots.txt compliance checked, compliance matrix populated)
  2. A filesystem boundary guard prevents any pipeline tool from writing to `docs/` — the guard is tested, CI-enforced, and blocks writes at the filesystem level
  3. Scraper identity strategy (User-Agent, contact info, rate limit headers) is documented and implemented per target
  4. robots.txt caching and compliance framework is operational, preventing scrapes of disallowed paths
  5. C&D response plan is documented and accessible to the team

**Plans**: 2/2 plans complete
Plans:

- [x] 07-01-PLAN.md — Legal compliance matrix (data/LEGAL.md)
- [x] 07-02-PLAN.md — Filesystem guard, robots.txt, scraper identity, CI

### Phase 8: Scraper Framework

**Goal**: New scrapers can be added as single-file plugins with safe HTTP handling, rate limiting, and drift detection
**Depends on**: Phase 7
**Requirements**: FRAME-01, FRAME-02, FRAME-03, FRAME-04
**Success Criteria** (what must be TRUE):

   1. A new scraper source can be added as a single file inheriting from `BaseScraper` and auto-registering via `SourceRegistry`
   2. Failed HTTP requests auto-escalate through anti-bot tiers (httpx → curl-cffi with TLS impersonation → Playwright fallback)
   3. Each source has its own rate limiter with configurable delay, exponential backoff with jitter, and per-source failure isolation
   4. Schema drift detection monitors page structure changes per source and raises alerts when selectors yield <80% of expected fields
   5. The Wikipedia scraper is migrated to the framework to prove the pattern works end-to-end

**Plans**: 3 plans

Plans:
- [ ] 08-01-PLAN.md — BaseScraper ABC + PerSourceRateLimiter + dependencies
- [ ] 08-02-PLAN.md — HTTPSource tiered escalation + SourceRegistry + SchemaDriftDetector
- [ ] 08-03-PLAN.md — Wikipedia scraper migration + integration

### Phase 9: Provenance & Schema

**Goal**: Every data value is traceable to its source, and the schema covers all 95 target fields
**Depends on**: Phase 8
**Requirements**: PROV-01, PROV-02
**Success Criteria** (what must be TRUE):

  1. Every field in every chip carries a provenance tag identifying its source (stored as `{field_name: source_id}` per chip)
  2. `ConflictResolver` logs field-level conflicts with source priority — no silent last-writer-wins merge
  3. 30 new fields are added to the Chip model covering charging protocols, Wi-Fi/BT/USB versions, AV1 decode, AI TOPS, PCIe, market_segment, and others
  4. All existing 1761 chips have `legacy_v2` provenance marked for every existing field value
  5. Completeness scoring accounts for all 95 fields and reports per-vendor fill rates

**Plans**: TBD

### Phase 10: Dedup & Identity

**Goal**: One canonical entry per chip with deterministic matching across all sources
**Depends on**: Phase 9
**Requirements**: DEDUP-01, DEDUP-02, DEDUP-03
**Success Criteria** (what must be TRUE):

  1. Every chip carries a stable UUID derived from vendor + model-number fingerprint, not a name-derived slug
  2. Multi-strategy matcher resolves duplicates through exact-model → alias-table → Wikidata QID → fuzzy-name fallback, merging without false positives
  3. All 4 existing scrapers (Wikipedia, Apple, Linux DeviceTree, Wikidata SPARQL) produce deduplicated entries through the framework
  4. Legacy `scripts/` directory is deleted and all functionality migrated to the `scraping/` subpackage

**Plans**: 3 plans

Plans:
- [ ] 10-01-PLAN.md — DedupEngine: UUID identity, multi-strategy matcher, write_vendor_file integration
- [ ] 10-02-PLAN.md — Scripts consolidation: migrate Apple/Linux DT/Wikidata scrapers, delete scripts/
- [ ] 10-03-PLAN.md — Tests: DedupEngine unit tests, integration tests, full regression pass

### Phase 11: Batch Processing & Quality

**Goal**: Pipeline scales to 5000+ chips with checkpoint recovery and measurable quality guarantees
**Depends on**: Phase 10
**Requirements**: BATCH-01, BATCH-02, BATCH-03
**Success Criteria** (what must be TRUE):

  1. `BatchEnricher` processes chips in configurable batch sizes (default 500) with checkpoint files enabling crash recovery without re-processing
  2. `QualityScorer` produces per-vendor and per-field reports with fill_rate, source_diversity, and conflict_rate metrics
  3. API p95 response time is < 200ms at 5000 chips for all paginated endpoints
  4. API endpoints use staged/lazy loading for large result sets, avoiding full table scans on every request

**Plans**: TBD

### Phase 12: High-Value Scrapers

**Goal**: Major chip count increase by scraping benchmark and spec aggregator sources
**Depends on**: Phase 11
**Requirements**: BIGSRC-01, BIGSRC-02, BIGSRC-03
**Success Criteria** (what must be TRUE):

  1. TechPowerUp scraper adds 2000-3000 chips with 30+ fields each, including process node, TDP, and memory specs
  2. NotebookCheck scraper adds 20+ benchmark scores (single/multi-core, efficiency) for 60%+ of chips
  3. Geekbench Browser scraper adds CPU and GPU benchmark scores cross-referenced by chip identity
  4. Total chip count reaches 4000-4500 with all new data passing through provenance tracking and dedup

**Plans**: TBD

### Phase 13: Vendor Official Scrapers

**Goal**: Authoritative vendor data fills deep field coverage gaps for Qualcomm, MediaTek, Intel, AMD, and Apple
**Depends on**: Phase 12
**Requirements**: VENDOR-01, VENDOR-02, VENDOR-03, VENDOR-04
**Success Criteria** (what must be TRUE):

  1. Qualcomm Developer Network scraper enriches 400+ chips with 50+ official fields (NPU, ISP, modem, process node)
  2. MediaTek scraper adds 300+ chips with detailed specs from official product listings
  3. Intel ARK and AMD scraper add lifecycle status and deep specs for 1500+ chips across desktop/mobile/server
  4. Apple Tech Specs scraper deepens M-series data (80+ chips) with official performance, GPU core, and memory bandwidth data
  5. Total chip count reaches 5000-5500 with per-vendor completeness ≥0.80 average

**Plans**: TBD

### Phase 14: UI/API Polish

**Goal**: Users can compare chips, explore data quality, and filter the complete dataset from CLI and API
**Depends on**: Phase 13
**Requirements**: UIPLUS-01, UIPLUS-02, UIPLUS-03
**Success Criteria** (what must be TRUE):

  1. `GET /v1/chips/{id}/compare?with={id2}` returns side-by-side field comparison with diff highlighting
  2. Data quality dashboard shows per-vendor completeness heatmaps, field coverage charts, and source conflict reports
  3. CLI supports advanced filtering: `soc-db list --process 4nm --npu-min 20 --source vendor --benchmark-min 5000`
  4. CLI reports per-chip provenance (which sources contributed each field) via `soc-db show --provenance`

**Plans**: TBD
**UI hint**: yes

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|---------------|--------|-----------|
| 1. REFAC | v2.1 | 4/4 | Complete | 2026-07-19 |
| 2. DB | v2.1 | 2/2 | Complete | 2026-07-19 |
| 3. ASYNC | v2.1 | 2/2 | Complete | 2026-07-19 |
| 4. RLIMIT | v2.1 | 2/2 | Complete | 2026-07-19 |
| 5. OBSERVE | v2.1 | 2/2 | Complete | 2026-07-19 |
| 6. WIKIDATA | v2.1 | 1/1 | Complete | 2026-07-19 |
| 7. Governance & Safety | v3.0 | 2/2 | Complete   | 2026-07-19 |
| 8. Scraper Framework | v3.0 | 0/3 | Planning | - |
| 9. Provenance & Schema | v3.0 | 0/0 | Not started | - |
| 10. Dedup & Identity | v3.0 | 0/3 | Planning | - |
| 11. Batch Processing | v3.0 | 0/0 | Not started | - |
| 12. High-Value Scrapers | v3.0 | 0/0 | Not started | - |
| 13. Vendor Official Scrapers | v3.0 | 0/0 | Not started | - |
| 14. UI/API Polish | v3.0 | 0/0 | Not started | - |
