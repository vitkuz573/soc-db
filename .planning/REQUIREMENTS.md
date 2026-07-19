# Requirements: SoC Database (soc-db)

**Defined:** 2026-07-19
**Core Value:** Accurate, queryable, up-to-date SoC identification data that developers and tools can rely on as a single source of truth.

## v1 Requirements

### Governance & Safety (GOV)

- [ ] **GOV-01**: Legal review of all scraping targets (ToS, robots.txt, compliance matrix)
- [ ] **GOV-02**: GitHub Pages filesystem boundary guard — data pipeline never writes to `docs/`

### Scraper Framework (FRAME)

- [ ] **FRAME-01**: Plugin-based scraper framework with BaseScraper and SourceRegistry
- [ ] **FRAME-02**: Multi-tier anti-bot HTTP (httpx → curl-cffi with TLS impersonation → Playwright)
- [ ] **FRAME-03**: Per-source rate limiting with exponential backoff and jitter
- [ ] **FRAME-04**: Schema drift detection — alert when page structure changes

### Provenance & Schema (PROV)

- [ ] **PROV-01**: Field-level provenance tracking — every value carries its source
- [ ] **PROV-02**: Add 30 new fields to Chip model (charging, Wi-Fi version, AV1 decode, AI TOPS, etc.)

### Dedup & Identity (DEDUP)

- [ ] **DEDUP-01**: UUID-based canonical chip identity system
- [ ] **DEDUP-02**: Multi-strategy matcher (exact model → alias → Wikidata → fuzzy)
- [ ] **DEDUP-03**: Consolidate and delete legacy `scripts/` directory

### Batch Processing (BATCH)

- [ ] **BATCH-01**: Batch enrichment with checkpointing and crash recovery
- [ ] **BATCH-02**: Data quality scoring per vendor and per field
- [ ] **BATCH-03**: API performance at 5000+ chips (pagination perf, lazy loading)

### High-Value Scrapers (BIGSRC)

- [ ] **BIGSRC-01**: TechPowerUp scraper (4398 chips, 30+ fields)
- [ ] **BIGSRC-02**: NotebookCheck scraper (20+ benchmarks per chip)
- [ ] **BIGSRC-03**: Geekbench Browser scraper (CPU/GPU benchmark scores)

### Vendor Official Scrapers (VENDOR)

- [ ] **VENDOR-01**: Qualcomm Developer Network scraper
- [ ] **VENDOR-02**: MediaTek official product listing scraper
- [ ] **VENDOR-03**: Intel ARK / AMD product spec scrapers
- [ ] **VENDOR-04**: Apple Tech Specs scraper (M-series deep data)

### UI/API Polish (UIPLUS)

- [ ] **UIPLUS-01**: Chip comparison API endpoint (`/v1/compare`)
- [ ] **UIPLUS-02**: Data quality dashboard view
- [ ] **UIPLUS-03**: CLI filters for completeness, source, vendor

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

- Auto-PR workflow for data updates
- GSMArena / DeviceSpecifications scrapers
- WebSocket streaming for data updates
- GraphQL endpoint

## Out of Scope

| Feature | Reason |
|---------|--------|
| VS Code / Copilot plugins | Ecosystem play, separate milestone |
| WebSocket streaming | Not related to data collection |
| Machine-readable errata database | Long-term only |
| Enterprise CI/CD (PyPI publish) | Deferred to v3.1 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| GOV-01 | — | Pending |
| GOV-02 | — | Pending |
| FRAME-01 | — | Pending |
| FRAME-02 | — | Pending |
| FRAME-03 | — | Pending |
| FRAME-04 | — | Pending |
| PROV-01 | — | Pending |
| PROV-02 | — | Pending |
| DEDUP-01 | — | Pending |
| DEDUP-02 | — | Pending |
| DEDUP-03 | — | Pending |
| BATCH-01 | — | Pending |
| BATCH-02 | — | Pending |
| BATCH-03 | — | Pending |
| BIGSRC-01 | — | Pending |
| BIGSRC-02 | — | Pending |
| BIGSRC-03 | — | Pending |
| VENDOR-01 | — | Pending |
| VENDOR-02 | — | Pending |
| VENDOR-03 | — | Pending |
| VENDOR-04 | — | Pending |
| UIPLUS-01 | — | Pending |
| UIPLUS-02 | — | Pending |
| UIPLUS-03 | — | Pending |

**Coverage:**
- v1 requirements: 25 total
- Mapped to phases: 0
- Unmapped: 25

---
*Requirements defined: 2026-07-19*
*Last updated: 2026-07-19 after initial definition*
