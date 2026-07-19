# Requirements: SoC Database (soc-db)

**Defined:** 2026-07-19
**Core Value:** Accurate, queryable, up-to-date SoC identification data that developers and tools can rely on as a single source of truth.

## v1 Requirements

Requirements for v2.1 milestone. Each maps to roadmap phases.

### Enrichment Refactoring (REFAC)

- [ ] **REFAC-01**: System can enrich chips via per-domain modules (cpu, gpu, memory, year, modem) instead of monolithic `enrich_one()` function
- [ ] **REFAC-02**: Snapshot test captures ALL 1746 chips' enrichment output before/after refactoring to detect regression

### Database Migration (DB)

- [ ] **DB-01**: SQLite database replaces flat JSON files with zero-data-loss migration tool
- [ ] **DB-02**: FTS5 full-text search replaces custom inverted index with equivalent or better search quality
- [ ] **DB-03**: Dual-read mode via `SOC_DB_USE_JSON=true` env var for instant rollback

### Async Data Layer (ASYNC)

- [x] **ASYNC-01**: API server uses async database access via aiosqlite without blocking the event loop
- [x] **ASYNC-02**: Chip cache (`get_chips()`) operates asynchronously with TTL-based invalidation

### Rate Limiting (RLIMIT)

- [x] **RLIMIT-01**: Rate limiter uses Redis as shared backend for multi-worker deployment
- [x] **RLIMIT-02**: Rate limiter falls back to in-memory mode transparently when Redis is unavailable

### Observability (OBSERVE)

- [ ] **OBSERVE-01**: FastAPI and core library emit OpenTelemetry traces with request-scoped span context
- [ ] **OBSERVE-02**: Business metrics (chip count, queries/sec, vendor distribution) exposed via Prometheus endpoint

### Wikidata Knowledge Sync (WIKIDATA)

- [ ] **WIKIDATA-01**: Hardcoded `VENDOR_KNOWLEDGE` maps replaced with Wikidata SPARQL queries for process node, GPU, and architecture
- [ ] **WIKIDATA-02**: Scheduled CI workflow refreshes vendor knowledge from Wikidata on weekly cadence

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Release Pipeline (RELEASE)

- **RELEASE-01**: GitHub Actions CI replaces AppVeyor for unified CI/CD
- **RELEASE-02**: Automated PyPI publishing via GitHub trusted publishing (OIDC)
- **RELEASE-03**: Multi-worker uvicorn deployment with shared state via Redis

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| GraphQL endpoint | v2.2+ target, not related to enterprise hardening |
| WebSocket streaming | v2.3+ target, infra not ready |
| VS Code / Copilot plugins | Ecosystem play, separate milestone |
| DuckDB analytics | OLAP queries, defer to v2.2 data quality |
| Custom enrichment DSL | Anti-feature — adds complexity without benefit |
| Full async migration of CLI | CLI benefits from simplicity of sync sqlite3 |
| Auto-merge PRs for data corrections | Requires human review for data quality |
| Remove AppVeyor | Keep until GHA is validated on all paths |
| Remove `requests` dependency | Breaking change — handle in separate cleanup |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| REFAC-01 | Phase 1 | Pending |
| REFAC-02 | Phase 1 | Pending |
| DB-01 | Phase 2 | Pending |
| DB-02 | Phase 2 | Pending |
| DB-03 | Phase 2 | Pending |
| ASYNC-01 | Phase 3 | Complete |
| ASYNC-02 | Phase 3 | Complete |
| RLIMIT-01 | Phase 4 | Complete |
| RLIMIT-02 | Phase 4 | Complete |
| OBSERVE-01 | Phase 5 | Pending |
| OBSERVE-02 | Phase 5 | Pending |
| WIKIDATA-01 | Phase 6 | Pending |
| WIKIDATA-02 | Phase 6 | Pending |

**Coverage:**

- v1 requirements: 13 total
- Mapped to phases: 13
- Unmapped: 0

---
*Requirements defined: 2026-07-19*
*Last updated: 2026-07-19 after initial definition*
