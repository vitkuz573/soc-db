# Feature Landscape

**Domain:** SoC/CPU identifier database — enterprise hardening
**Researched:** 2026-07-19

## Table Stakes

Features users expect from a production API service. Missing these = service feels incomplete for enterprise use.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Persistent database** | Data should survive server restarts. In-memory JSON loading loses cache on restart. | Medium | SQLite migration. Solves: data loaded fresh on every cache miss + restart loses cache. |
| **Non-blocking API I/O** | API should not block event loop on disk reads. Current `load_all()` blocks despite `asyncio.to_thread()`. | Low | `aiosqlite` makes all DB queries truly async. |
| **Scalable rate limiting** | Multi-worker deployment requires shared state. Current in-memory limiter is per-process. | Low | Redis-backed sliding window. Falls back to in-memory if Redis unavailable. |
| **Structured error handling** | All API errors return consistent `{"error": ..., "detail": ...}` shape. | Low | Already done in v2.0. No change needed. |
| **Health/readiness probes** | `/health` and `/metrics` endpoints for container orchestration. | Low | Already done in v2.0. OTel adds richer metrics. |
| **CLI reliability** | CLI should work without database dependency (offline-friendly). | Medium | CLI uses sync `sqlite3` but must handle missing DB gracefully. |

## Differentiators

Features that set soc-db apart from a simple JSON-file API.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Full-text search (FTS5)** | Fast search across 1746+ chips without loading all data into memory. | Low | SQLite FTS5 built-in. Replaces custom inverted index. |
| **OpenTelemetry tracing** | End-to-end request visibility: "which enrichment step is slow?" | Medium | Auto-instrumentation for FastAPI + manual spans for enrichment pipeline. |
| **Wikidata-driven knowledge** | Dynamic vendor knowledge (process nodes, GPU maps) instead of hardcoded dicts. | Medium | SPARQL queries replace `VENDOR_KNOWLEDGE`. Requires cache + fallback strategy. |
| **Async enrichment pipeline** | Enrichment can run concurrently for multiple chips without blocking. | Medium | Each domain module is async-compatible. Pipeline orchestrator uses `asyncio.gather()`. |
| **Migration with rollback** | JSON→SQLite migration that preserves JSON files as fallback. | Medium | Dual-read pattern: `SOC_DB_USE_JSON=true` forces JSON reads if SQLite has issues. |

## Anti-Features

Features to explicitly NOT build in v2.1.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **ORM (SQLAlchemy, Peewee, etc.)** | 95-field single-table schema doesn't need ORM abstraction. Adds complexity, slow imports, migration headaches. | Raw SQL with dict row factory. Queries in `db/queries.py`. |
| **PostgreSQL migration** | Would require server setup, connection pooling, networking config. Overkill for single-file database. | SQLite with WAL mode handles concurrent reads well. PostgreSQL deferred to v2.2+ if needed. |
| **Elasticsearch** | 1746 documents don't need a search cluster. FTS5 handles this trivially. | SQLite FTS5. Elasticsearch deferred to v2.2+ if scale exceeds 100K chips. |
| **GraphQL endpoint** | Increases API surface, requires resolver layer, adds complexity. | REST endpoints already comprehensive. GraphQL deferred to v2.2+ per PROJECT.md. |
| **WebSocket streaming** | No use case for real-time chip data. Adds keepalive complexity. | Deferred to v2.3+ per PROJECT.md. |
| **Removing JSON files** | Premature deletion loses rollback capability and git-diff-friendly source of truth. | Keep JSON files through v2.1. Deprecate in v2.2+ with migration guide. |
| **Async CLI** | CLI doesn't need async. Adding it would nest event loops and break subprocess usage. | CLI stays sync with stdlib `sqlite3`. API uses async with `aiosqlite`. |

## Feature Dependencies

```
enrich/ module extraction (REFAC-01)
  │
  ├── SQLite database (DB-01)
  │     └── Async data access (ASYNC-01)
  │           ├── Redis rate limiter (RATELIMIT-01)
  │           ├── OTel instrumentation (OBSERVE-01)
  │           └── Multi-worker deployment
  │
  └── Wikidata SPARQL (WIKIDATA-01) ─── can be done independently
```

## MVP Recommendation

Each feature delivers independent value. However, the build order should be:

1. **Phase 1: enrich/ module extraction** — No new dependencies. Reduces the largest tech debt (700-line `enrich_one()`). Makes all other phases cleaner.
2. **Phase 2: SQLite + migration** — Biggest impact. Eliminates synchronous bulk-load. JSON files preserved as fallback.
3. **Phase 3: Async data access** — Builds on SQLite. Makes API truly non-blocking.
4. **Phase 4: Redis rate limiter** — Enables multi-worker. Can parallel with Phase 3.
5. **Phase 5: OpenTelemetry** — Needed before multi-worker goes to production.
6. **Phase 6: Wikidata SPARQL** — Independent. Can be done last or in parallel.
7. **Phase 7: Multi-worker deployment** — Final production hardening.

**Defer:** Async enrichment pipeline (partial in Phase 1, full concurrency in v2.2). PostgreSQL/Elasticsearch (v2.2+).

## Sources

- Current codebase analysis: CONCERNS.md, ARCHITECTURE.md, STRUCTURE.md (HIGH confidence)
- PROJECT.md requirements list for v2.1 (HIGH confidence)
- SQLite FTS5 performance characteristics (HIGH confidence)
- OpenTelemetry Python ecosystem maturity (HIGH confidence)
