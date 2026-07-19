# Roadmap: SoC Database (soc-db)

## v2.1 Milestone: Full Enterprise Hardening

This milestone transforms soc-db from a proven v2.0 monolith into an enterprise-grade service. Six phases pay down technical debt in dependency order: extract the monolithic enrichment function into per-domain modules, migrate from flat JSON files to SQLite with FTS5 full-text search, make the data layer truly async, add Redis-backed rate limiting with transparent fallback, instrument with OpenTelemetry for observability, and replace hardcoded vendor knowledge with dynamic Wikidata SPARQL queries. Each phase is backward-compatible — no breaking API or CLI changes.

## Constraints

- **GitHub Pages deployment (docs/):** The `docs/` directory (index.html, 404.html, swagger.html) must NEVER be modified or broken by any phase.
- **API backward compatibility:** Existing v1 endpoints must not change behavior or response shapes.
- **CLI backward compatibility:** All existing commands and output formats preserved.
- **JSON data files:** Existing `data/*.json` files remain untouched as frozen source of truth.

## Phases

- [ ] **Phase 1: REFAC — Enrichment Module Extraction** — Extract 700-line `enrich_one()` into per-domain modules with snapshot regression test
- [ ] **Phase 2: DB — SQLite Database Migration** — Replace flat JSON with SQLite, FTS5 search, and dual-read rollback
- [x] **Phase 3: ASYNC — Async Data Layer** — Non-blocking async database access via `aiosqlite` with async chip cache (completed 2026-07-19)
- [ ] **Phase 4: RLIMIT — Redis-Backed Rate Limiting** — Shared rate limiter for multi-worker deployment with transparent in-memory fallback
- [ ] **Phase 5: OBSERVE — OpenTelemetry Observability** — OpenTelemetry traces and Prometheus business metrics
- [ ] **Phase 6: WIKIDATA — Wikidata Knowledge Sync** — Dynamic vendor knowledge maps from Wikidata SPARQL with scheduled CI refresh

## Phase Details

### Phase 1: REFAC — Enrichment Module Extraction

**Goal**: Enrichment pipeline uses per-domain modules (cpu, gpu, memory, year, modem) instead of monolithic `enrich_one()`, with zero regression verified by snapshot test
**Depends on**: Nothing (first phase)
**Requirements**: REFAC-01, REFAC-02
**Success Criteria** (what must be TRUE):

  1. All 1746 chips produce identical enrichment output after refactoring (snapshot test passes)
  2. Developer can read and modify enrichment logic in per-domain files instead of one 700-line function
  3. CI pipeline runs snapshot test on every commit to detect enrichment regression
  4. Year inference priority ordering is explicitly documented per domain

**Plans**: 4 plans (01–04)

Plans:

- [ ] 01-01-PLAN.md — Snapshot test + enrich/ package foundation (Wave 1)
- [ ] 01-02-PLAN.md — Core extraction: year, process, GPU, memory modules (Wave 2)
- [ ] 01-03-PLAN.md — Peripheral extraction: modem, NPU, connectivity, storage (Wave 3)
- [ ] 01-04-PLAN.md — Aliases, scoring, CPU module, common.py shim, lint cleanup (Wave 4)

### Phase 2: DB — SQLite Database Migration

**Goal**: SQLite database replaces flat JSON files with FTS5 full-text search and dual-read rollback via `SOC_DB_USE_JSON` env var
**Depends on**: Phase 1
**Requirements**: DB-01, DB-02, DB-03
**Success Criteria** (what must be TRUE):

  1. Migration tool transfers all 1746 chips from JSON to SQLite with zero data loss (field-by-field diff passes)
  2. User can search chips with FTS5 full-text search and get equivalent or better results than v2.0 custom inverted index
  3. User can set `SOC_DB_USE_JSON=true` and instantly fall back to JSON file store for rollback
  4. All existing CLI commands (list, query, show, stats, enrich) work identically with SQLite backend
  5. Existing JSON files remain untouched as frozen source of truth

**Plans**: 2 plans (01–02)

Plans:

- [ ] 02-01-PLAN.md — SQLite DB package (connection, schema, queries, migrate) + config dual-read (Wave 1)
- [ ] 02-02-PLAN.md — CLI + API integration, FTS5 search, tests (Wave 2)

### Phase 3: ASYNC — Async Data Layer

**Goal**: API server uses async database access via `aiosqlite` without blocking the event loop
**Depends on**: Phase 2
**Requirements**: ASYNC-01, ASYNC-02
**Success Criteria** (what must be TRUE):

   1. API server uses async connection pool (aiosqlite) — no `asyncio.to_thread()` wrappers for DB access
   2. Chip cache (`get_chips()`) operates asynchronously with TTL-based invalidation, not synchronous preloading
   3. API handles concurrent requests without event loop blocking
   4. Enrichment pipeline profiling determines if `ProcessPoolExecutor` is needed for CPU-bound work

**Plans**: 2/2 plans complete

Plans:

- [x] 03-01-PLAN.md — Async database foundation (aiosqlite dep, connection pool, query functions, unit tests) [Wave 1]
- [x] 03-02-PLAN.md — API async integration (TTL cache, async endpoints, integration tests, enrichment profiling) [Wave 2]

### Phase 4: RLIMIT — Redis-Backed Rate Limiting

**Goal**: Redis-backed sliding window rate limiter with transparent in-memory fallback for multi-worker safety
**Depends on**: Phase 2 (can be planned/executed in parallel with Phase 3)
**Requirements**: RLIMIT-01, RLIMIT-02
**Success Criteria** (what must be TRUE):

  1. API rate limits are enforced via Redis shared state across multiple workers
  2. When Redis is unavailable, rate limiter falls back to in-memory mode transparently (no 5xx errors)
  3. Health endpoint reports Redis connectivity status
  4. Rate limit headers (X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset) present in API responses

**Plans**: 2 plans (01–02)

Plans:

- [ ] 04-01-PLAN.md — Core rate limiter library (rate_limit.py, config, dep, unit tests) [Wave 1]
- [ ] 04-02-PLAN.md — API integration (middleware, health, headers, integration tests, docker-compose) [Wave 2]

### Phase 5: OBSERVE — OpenTelemetry Observability

**Goal**: FastAPI and core library emit OpenTelemetry traces with Prometheus-exposed business metrics
**Depends on**: Phase 3 (needs stable async API to instrument)
**Requirements**: OBSERVE-01, OBSERVE-02
**Success Criteria** (what must be TRUE):

  1. FastAPI endpoints emit OpenTelemetry traces with request-scoped span context
  2. Business metrics (chip count, queries/sec, vendor distribution) exposed at `/metrics` Prometheus endpoint
  3. Health endpoint (`/health`) is excluded from tracing to avoid noise
  4. OTel overhead is under 5% (verified by before/after benchmark with ~10% sampling)

**Plans**: TBD

### Phase 6: WIKIDATA — Wikidata Knowledge Sync

**Goal**: Hardcoded `VENDOR_KNOWLEDGE` maps replaced with Wikidata SPARQL queries with scheduled CI refresh
**Depends on**: Phase 1 (needs enrichment modules to consume knowledge maps)
**Requirements**: WIKIDATA-01, WIKIDATA-02
**Success Criteria** (what must be TRUE):

  1. Enrichment pipeline uses Wikidata SPARQL queries for process node, GPU model, and architecture data instead of hardcoded dicts
  2. Weekly CI workflow refreshes vendor knowledge from Wikidata
  3. SPARQL results are validated before overwriting maps (dry-run mode available; never auto-publish without human review)
  4. Failed SPARQL queries (timeout, empty results) don't corrupt existing vendor maps — retry with exponential backoff

**Plans**: TBD

## Progress

**Execution Order:** Phases execute in dependency order. Phase 4 (RLIMIT) can run in parallel with Phase 3 (ASYNC) after Phase 2 completes.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. REFAC | 4/0 | Planning (4 plans created) | - |
| 2. DB | 0/2 | Planning (2 plans created) | - |
| 3. ASYNC | 2/2 | Complete   | 2026-07-19 |
| 4. RLIMIT | 0/2 | Planning (2 plans created) | - |
| 5. OBSERVE | 0/0 | Not started | - |
| 6. WIKIDATA | 0/0 | Not started | - |
