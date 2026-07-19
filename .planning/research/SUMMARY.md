# Project Research Summary

**Project:** soc-db v2.1 Enterprise Hardening
**Domain:** SoC/CPU identifier database — enterprise-grade REST API + CLI + data pipeline
**Researched:** 2026-07-19
**Confidence:** HIGH

## Executive Summary

soc-db is a mature Python monolith (v2.0 shipped, 1746+ chips across 37 vendors, 405 tests, 100% coverage) that provides SoC/CPU identification data via CLI, REST API (FastAPI), and a GitHub Pages web UI. The v2.1 milestone focuses on enterprise hardening: paying down technical debt from a 2-year rapid-growth phase. The research recommends an incremental, backward-compatible approach with seven workstreams ordered by dependency: refactor the monstrous 700-line `enrich_one()` function into per-domain modules (most dangerous — must preserve year-inference priority ordering), migrate from 44 flat JSON files to SQLite with FTS5 (biggest impact), make the data layer truly async via `aiosqlite`, add Redis-backed shared rate limiting for multi-worker deployment, instrument with OpenTelemetry, and replace hardcoded vendor knowledge with Wikidata SPARQL queries.

**Key recommendation:** Execute phases in dependency order: REFAC-01 → DB-01 → ASYNC-01 + RATELIMIT-01 (parallel) → OBSERVE-01 → WIKIDATA-01. TEST-01 and VALIDATE-01 are cross-cutting and can run in parallel from the start. RELEASE-01 (PyPI publishing) comes last. Each new dependency (aiosqlite, redis, opentelemetry) is independently useful and doesn't require the others — but SQLite must exist before async access, Redis must exist before multi-worker, and OTel needs a stable API to instrument.

**Key risks:** (1) Year inference regression during refactoring — the 530-line priority-ordered if/elif chain has undocumented ordering dependencies. Mitigation: take a snapshot of all 1746 chip years BEFORE refactoring and verify identical output after each extraction. (2) Schema drift during JSON→SQLite migration — SQLite enforces types that JSON doesn't, and NULL/missing-key semantics differ. Mitigation: Pydantic response models as the contract, field-by-field diff of all 1746 records after migration. (3) Redis becomes a single point of failure — if Redis goes down and there's no fallback, ALL API requests fail. Mitigation: implement in-memory fallback in the SAME PR as the Redis rate limiter.

## Key Findings

### Recommended Stack

[Full detail: STACK.md](STACK.md)

All existing dependencies (FastAPI, uvicorn, pydantic, etc.) remain unchanged. Four new core dependencies are added — each for a specific purpose, with strong alternatives-considered rationale documented in STACK.md.

**Core technologies (new for v2.1):**

- **aiosqlite >=0.20**: Async SQLite database access — native async without thread pools, replicates stdlib `sqlite3` API. Chosen over `asyncio.to_thread()` wrappers (current), `databases` library (over-engineered), and `sqlite-utils` (wraps CLI use case).
- **redis[hiredis] >=5.0**: Redis client with async support for shared rate limiter state. Chosen over in-memory (doesn't work with multiple workers) and Memcached (lacks sorted set data structures for sliding windows).
- **opentelemetry-api >=1.25 + opentelemetry-sdk >=1.25**: Vendor-neutral telemetry API/SDK. Chosen over Prometheus client (vendor lock-in) and logfire (too new, vendor-specific).
- **opentelemetry-instrumentation-fastapi >=0.45b + opentelemetry-exporter-otlp >=1.25**: Auto ASGI tracing and OTLP export to any OTel-compatible backend (Jaeger, Tempo, Datadog, etc.).
- **SQLite FTS5** (stdlib, no dependency): Full-text search replacing the custom inverted index. Chosen over Elasticsearch (overkill for 1746 docs) and current custom index (rebuilds on every cache miss).
- **Wikidata SPARQL** (external API, no dependency): Dynamic vendor knowledge replacing hardcoded dicts. Chosen over Wikipedia scraping (inconsistent infoboxes) and hardcoded dicts (require code changes for every new chip).

**Removal candidates:** `requests` (move from core to dev deps — only used by legacy scripts).

### Expected Features

[Full detail: FEATURES.md](FEATURES.md)

**Must have (table stakes):**
- **Persistent database** — SQLite migration. Data survives restarts, no more cache rebuilds on every cache miss.
- **Non-blocking API I/O** — `aiosqlite` makes all DB queries truly async. No more `asyncio.to_thread()` band-aids.
- **Scalable rate limiting** — Redis-backed sliding window with in-memory fallback. Works across multiple uvicorn workers.
- **Structured error handling** — Already done in v2.0. No change needed.
- **Health/readiness probes** — Already done in v2.0. OTel adds richer metrics.
- **CLI reliability** — Sync `sqlite3` with graceful handling of missing DB.

**Should have (differentiators):**
- **Full-text search (FTS5)** — BM25 ranking, no index rebuild, zero-dependency.
- **OpenTelemetry tracing** — End-to-end request visibility. "Which enrichment step is slow?"
- **Wikidata-driven knowledge** — Dynamic vendor maps instead of code changes per chip.
- **Async enrichment pipeline** — Concurrent domain enrichment via `asyncio.gather()`.
- **Migration with rollback** — Dual-read pattern. `SOC_DB_USE_JSON=true` forces JSON reads if SQLite has issues.

**Anti-features (do NOT build in v2.1):**
- ORM (SQLAlchemy/Peewee) — 95-field single-table schema doesn't need it.
- PostgreSQL — Overkill for single-file DB. Deferred to v2.2+.
- Elasticsearch — 1746 docs don't need a search cluster. FTS5 handles it.
- GraphQL endpoint — Increases API surface unnecessarily. Deferred to v2.2+.
- WebSocket streaming — No use case. Deferred to v2.3+.
- Removing JSON files — Keep as frozen source of truth and rollback mechanism through v2.1.
- Async CLI — CLI doesn't need async. Stays sync with stdlib `sqlite3`.

### Architecture Approach

[Full detail: ARCHITECTURE.md](ARCHITECTURE.md)

The target architecture is a modular monolith with three new packages extracted from the current 1561-line `common.py` and flat JSON file store. The core pattern is a **dual interface**: synchronous `sqlite3` for CLI, async `aiosqlite` for API — sharing query logic via `db/queries.py`. The JSON→SQLite migration follows a three-phase zero-downtime approach (dual-read → cutover → legacy cleanup) with the repository pattern enabling gradual transition. The enrichment pipeline becomes a strategy chain of per-domain modules (`enrich/cpu.py`, `enrich/gpu.py`, `enrich/year.py`, etc.) with a standardized `infer(chip) → chip` signature. OpenTelemetry crosses all layers; Redis is scoped to the rate limiter only.

**Major components:**
1. **`enrich/`** (NEW) — Per-domain enrichment modules replacing the 700-line `enrich_one()`. Strategy chain pipeline. Each module is independently unit-testable.
2. **`db/`** (NEW) — SQLite abstraction layer with sync API (for CLI/scrapers) and async API (for FastAPI). FTS5 full-text search, migration runner, shared query definitions.
3. **`wikidata_sparql/`** (NEW) — SPARQL query wrapper for dynamic vendor knowledge maps. Pre-built query templates, result caching, dry-run mode.
4. **`infra/redis.py`** (NEW) — Redis connection pool and sliding-window rate limiter implementation with in-memory fallback.
5. **`instrumentation/otel.py`** (NEW) — OTel tracer setup, FastAPI auto-instrumentation, custom enrichment pipeline spans.

### Critical Pitfalls

[Full detail: PITFALLS.md](PITFALLS.md)

1. **Year inference regression after refactoring** — The 530-line year inference chain has undocumented priority ordering (MediaTek before Qualcomm, etc.). Extracting into modules loses the implicit `break`-based dispatch.
   - **Prevention:** Snapshot test ALL 1746 chip years BEFORE any refactoring. Verify identical output after each extraction.
   - **Phase:** REFAC-01

2. **Schema drift in JSON→SQLite migration** — JSON allows heterogeneous types per-record; SQLite enforces per-column types. NULL vs missing-key semantics differ. API responses change shape subtly.
   - **Prevention:** Pydantic `ChipResponse` as contract. Field-by-field diff of all 1746 records. API integration test with frozen responses.
   - **Phase:** DB-01

3. **Redis downtime breaks all requests** — Rate limiter in request path. If Redis is unreachable and there's no fallback, every API request returns 500.
   - **Prevention:** In-memory fallback rate limiter in the SAME PR as Redis. Redis connection timeouts (`socket_connect_timeout=2`). Health check integration.
   - **Phase:** RATELIMIT-01

4. **Event loop blocking from mixed sync/async** — Calling synchronous enrichment from async routes blocks the event loop. All concurrent requests wait.
   - **Prevention:** Move CPU-bound enrichment to `ProcessPoolExecutor`. Run sync I/O in `run_in_executor()`. Profile with `wrk` under concurrency.
   - **Phase:** ASYNC-01

5. **Wikidata SPARQL schema changes corrupt data** — Wikidata property IDs change without notice. Empty or timeout results overwrite vendor maps, silently deleting GPU/process data from 500+ records.
   - **Prevention:** Validate SPARQL results before writing. Version-pin property P-IDs in comments. Never auto-publish without human review. Retry with exponential backoff.
   - **Phase:** WIKIDATA-01

## Implications for Roadmap

Based on combined research, the recommended phase structure is:

### Phase 1: REFAC-01 — Enrichment Module Extraction
**Rationale:** Foundation for everything else. No new dependencies — pure code reorganization. Most dangerous phase due to year-inference regression risk; must be done first while the codebase is simplest.

**Delivers:** `enrich/` package with per-domain modules (cpu, gpu, memory, year, modem, wifi_bt, storage, aliases, scoring). `common.py` becomes a backward-compatible re-export shim.

**Addresses FEATURES.md:** Foundation for async enrichment pipeline (differentiator).

**Avoids PITFALLS.md:** Pitfall 1 (year inference regression — snapshot test before/after), Pitfall 11 (circular imports — TYPE_CHECKING guards, caller-first approach).

**Key constraint:** Snapshot test of all 1746 chips BEFORE any extraction. Verify identical year output after EACH sub-extraction. Document the priority chain explicitly.

---

### Phase 2: DB-01 — SQLite Database + JSON Migration
**Rationale:** Core data store change with the biggest impact (eliminates synchronous bulk-load, persistent data, FTS5). Must come after REFAC-01 because enrichment code references data shapes that SQLite must match.

**Uses STACK.md:** `sqlite3` (stdlib sync), `aiosqlite >=0.20` (async), SQLite FTS5 (stdlib), `db/queries.py` shared queries.

**Delivers:** `data/soc-db.db` with 95-field `chips` table, FTS5 virtual table, indexes. Migration script (`python -m soc_db.db.migrate`). `db/sync_api.py` for CLI. `db/async_api.py` for API (initial). JSON files preserved as frozen source of truth.

**Addresses FEATURES.md:** Persistent database (table stakes), non-blocking I/O (table stakes — initial), full-text search (differentiator).

**Implements ARCHITECTURE.md:** Repository pattern (JsonChipRepository ↔ SqliteChipRepository), dual interface pattern (sync/async), WAL mode, FTS5.

**Avoids PITFALLS.md:** Pitfall 2 (schema drift — Pydantic response model, field-by-field diff), Pitfall 4 (event loop blocking — enable WAL mode). Technical debt: never use `SELECT *`, always explicit column lists.

**Research flag:** Schema design needs validation against actual JSON data shapes. Some fields may have unexpected nullability or type heterogeneity across vendors.

---

### Phase 3: ASYNC-01 — Async Data Layer
**Rationale:** Builds on SQLite. Makes API truly non-blocking. Must come after DB-01 because async API needs SQLite.

**Uses STACK.md:** `aiosqlite >=0.20` (async connection per request).

**Delivers:** Fully async API route handlers. No more `asyncio.to_thread()` wrappers. Async connection lifecycle in FastAPI `lifespan`. Profile enrichment's sync code for `ProcessPoolExecutor` migration.

**Addresses FEATURES.md:** Non-blocking API I/O (table stakes — completed).

**Implements ARCHITECTURE.md:** Dual interface pattern (sync CLI / async API complete). FastAPI lifespan dependency injection.

**Avoids PITFALLS.md:** Pitfall 4 (event loop blocking — audit all sync calls, use `run_in_executor` for CPU-bound work, never `time.sleep` in async code).

**Research flag:** Enrichment pipeline may still be synchronous. Needs profiling to determine whether `ProcessPoolExecutor` is necessary now or can wait. Likely needs deeper research during planning.

---

### Phase 4: RATELIMIT-01 — Redis-Backed Rate Limiter
**Rationale:** Multi-worker safety requirement. Can run in parallel with ASYNC-01 (both depend on DB-01 but not on each other). Redis must exist before deploying with >1 worker.

**Uses STACK.md:** `redis[hiredis] >=5.0` with `redis.asyncio`.

**Delivers:** `infra/redis.py` with connection pool. Sliding window rate limiter using Redis sorted sets. In-memory fallback rate limiter. Redis health check in `/health` endpoint. `api_key` authentication requirement in production.

**Addresses FEATURES.md:** Scalable rate limiting (table stakes — completed).

**Implements ARCHITECTURE.md:** Redis sliding window algorithm (ZREMRANGEBYSCORE, ZADD, ZCARD). FastAPI middleware integration.

**Avoids PITFALLS.md:** Pitfall 7 (Redis downtime — in-memory fallback in SAME PR), Pitfall 8 (shared state corruption — rate limiter works across workers). Redis timeouts: `socket_connect_timeout=2, socket_timeout=2`.

**CRITICAL:** In-memory fallback must be implemented in this same PR. Without it, a Redis restart = total API outage.

---

### Phase 5: OBSERVE-01 — OpenTelemetry Instrumentation
**Rationale:** Observability layer. Must come after ASYNC-01 (need stable async API to instrument). Should come before multi-worker deployment (need to verify behavior under load).

**Uses STACK.md:** `opentelemetry-api >=1.25`, `opentelemetry-sdk >=1.25`, `opentelemetry-instrumentation-fastapi >=0.45b`, `opentelemetry-exporter-otlp >=1.25`.

**Delivers:** `instrumentation/otel.py` with `setup_otel()` function. FastAPI auto-instrumentation with excluded URLs (`/health, /metrics`). Custom spans for enrichment pipeline steps and DB queries. Console exporter fallback for dev.

**Addresses FEATURES.md:** OpenTelemetry tracing (differentiator — completed).

**Implements ARCHITECTURE.md:** Cross-cutting instrumentation layer. TracerProvider with BatchSpanProcessor. Configurable sampling.

**Avoids PITFALLS.md:** Pitfall 9 (OTel overhead — 10% sampling, exclude health endpoints, before/after benchmark with <5% degradation).

**Research flag:** OTel version compatibility with FastAPI and existing dependencies. Need to pin versions and test `pip install -e ".[dev]"` in CI. Standard patterns — skip deep research phase.

---

### Phase 6: WIKIDATA-01 — Wikidata SPARQL Vendor Knowledge
**Rationale:** Independent of DB migration, but benefits from SQLite for caching results. Can be done in parallel with OBSERVE-01.

**Delivers:** `wikidata_sparql/` package with SPARQL client, query templates, result validation, dry-run mode. Replaces `VENDOR_KNOWLEDGE` hardcoded dict in enrichment.

**Addresses FEATURES.md:** Wikidata-driven knowledge (differentiator — completed).

**Implements ARCHITECTURE.md:** SPARQL query → cached vendor maps → enrichment pipeline consumer.

**Avoids PITFALLS.md:** Pitfall 10 (SPARQL unreliability — validate results before writing, version-pin property P-IDs, retry with backoff, dry-run mode, never auto-publish without human review).

**Research flag:** Wikidata property IDs for process nodes, GPU models, and architecture details need to be confirmed. The current queries in the research are templates; actual P-IDs may have changed. Needs validation during implementation.

---

### Phase 7: RELEASE-01 — PyPI Publishing & Multi-Worker Deployment
**Rationale:** Must come last — all features must be complete and stable before publishing.

**Delivers:** PyPI publish with OIDC trusted publishing. Multi-worker uvicorn deployment config (workers = N, Redis required if N > 1). `.gitignore` for `*.db`. Pre-publish security scan (`twine check`, build inspection, `bandit`).

**Avoids PITFALLS.md:** Pitfall 3 (secrets leak — explicit MANIFEST.in excludes, OIDC auth, pre-publish dry-run, bandit scan). Pitfall 8 (shared state — Redis required before multi-worker).

**Research flag:** Current PyPI publishing setup needs audit. May need deeper research on OIDC configuration and MANIFEST.in content.

---

### Cross-Cutting: TEST-01 — Property-Based Testing
**Rationale:** Can run in parallel with all other phases. Feeds quality into REFAC-01 (property tests for enrichment modules).

**Delivers:** Invariant-based property tests replacing weak `test_no_exceptions`. Committed `.hypothesis/examples` directory. `@example()` decorators for known edge cases. `@settings(derandomize=True)` for CI determinism.

**Avoids PITFALLS.md:** Pitfall 6 (Hypothesis non-determinism — seed, DB, invariance).

---

### Cross-Cutting: VALIDATE-01 — Data Validation CI
**Rationale:** Can run in parallel. Improves CI reliability for all phases.

**Delivers:** Separate gating (deterministic checks) from monitoring (external-dependent checks). Pinned validation schema version. `@pytest.mark.flaky(reruns=3)` for external-dependent tests.

**Avoids PITFALLS.md:** Pitfall 5 (flaky CI — never validate against live APIs in gating CI).

---

### Phase Ordering Rationale

- **REFAC-01 is first** because it's the most dangerous (year inference regression affects all 1746 chips) and has zero dependencies. The snapshot test protects against regression.
- **DB-01 is second** because it's the biggest architectural change (data store) and everything else depends on SQLite existing.
- **ASYNC-01 and RATELIMIT-01 can run in parallel** after DB-01 — they share no dependency beyond SQLite being present.
- **OBSERVE-01 needs a stable API** to instrument, so it comes after ASYNC-01.
- **WIKIDATA-01 is independent** and can slot anywhere after REFAC-01, but benefits from OBSERVE-01 for monitoring SPARQL call latency.
- **RELEASE-01 is always last** — don't publish until all features are stable.
- **TEST-01 and VALIDATE-01 are cross-cutting** — start early, benefit all phases.

### Research Flags

Phases likely needing deeper research during planning:
- **ASYNC-01:** Enrichment pipeline's CPU-bound nature needs profiling to determine whether `ProcessPoolExecutor` or background task queue is appropriate. The current research identifies the risk but doesn't prescribe a specific implementation.
- **WIKIDATA-01:** Actual Wikidata property P-IDs for process nodes, GPU models, and architecture details need to be confirmed. The SPARQL query templates in the research need validation against the live endpoint.
- **RELEASE-01:** Current PyPI publishing configuration needs audit. OIDC trusted publishing setup may require GitHub Actions workflow changes.

Phases with standard patterns (skip research-phase):
- **DB-01:** SQLite schema design, migration scripts, and FTS5 setup are well-documented patterns. The earch research provides detailed schema SQL and migration pseudocode.
- **RATELIMIT-01:** Redis sliding window rate limiter is a documented pattern with code examples in the research.
- **OBSERVE-01:** OpenTelemetry FastAPI instrumentation is well-documented with official guides. The research provides the `setup_otel()` pseudocode.
- **TEST-01:** Hypothesis property-based testing is a standard technique with official documentation.
- **VALIDATE-01:** CI validation separation (gating vs monitoring) is a standard DevOps pattern.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All technologies have official documentation and are well-established in the Python ecosystem. Alternatives considered with clear rationale. Version recommendations are current. |
| Features | HIGH | Derived from PROJECT.md requirements, codebase analysis (CONCERNS.md, STRUCTURE.md), and domain knowledge of enterprise API services. Table stakes vs differentiators mapping is sound. |
| Architecture | HIGH | Based on thorough codebase analysis of existing v2.0 architecture. Component boundaries are well-defined. Migration strategy follows zero-downtime patterns. SQLite schema is detailed with actual SQL. |
| Pitfalls | HIGH | 11 detailed pitfalls with root cause analysis, prevention strategies, and recovery plans. Sources include official documentation and established patterns. Year inference analysis came from actual code reading of common.py. |

**Overall confidence:** HIGH

### Gaps to Address

- **Year inference exact priority ordering** — The research documents that ordering exists and why it matters, but the exact vendor priority order needs to be extracted from `common.py:799-1328` during REFAC-01 execution. The snapshot test strategy is sound, but the actual priority chain must be documented during extraction.
- **Enrichment CPU-bound profiling** — Whether `ProcessPoolExecutor` is needed depends on actual enrichment latency. Current code loads all data synchronously, so enrichment latency is masked. After async migration, it becomes visible. Needs profiling during ASYNC-01.
- **Wikidata property IDs** — The SPARQL query templates use placeholder P-IDs that need validation. The research provides the query structure and error-handling patterns, but actual property IDs must be confirmed against the live Wikidata schema during WIKIDATA-01.
- **Current PyPI configuration** — The research identifies secrets-leak risks but doesn't audit the actual `pyproject.toml`, `MANIFEST.in`, or CI publish workflow. These need review during RELEASE-01.

## Sources

### Primary (HIGH confidence)
- [aiosqlite docs](https://aiosqlite.omnilib.dev/en/latest/) — async SQLite access patterns
- [redis-py async docs](https://redis.readthedocs.io/en/stable/examples/asyncio_examples.html) — sliding window rate limiter implementation
- [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/instrumentation/) — FastAPI instrumentation, sampling configuration
- [OpenTelemetry FastAPI instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html) — auto-instrumentation setup
- [SQLite FTS5 docs](https://www.sqlite.org/fts5.html) — full-text search virtual table
- [SQLite WAL mode](https://www.sqlite.org/wal.html) — concurrent read concurrency
- [Python sqlite3 stdlib docs](https://docs.python.org/3/library/sqlite3.html) — sync access patterns
- [Hypothesis docs](https://hypothesis.readthedocs.io) — reproducibility, database, @example patterns
- [Wikidata SPARQL documentation](https://wikidata.org/wiki/Wikidata:SPARQL_query_service) — format, timeout, rate limits
- [PyPA packaging guides](https://packaging.python.org) — PyPI publishing, OIDC trusted publishing
- [Codebase analysis](.planning/codebase/) — CONCERNS.md, common.py (1561 lines), api/main.py (477 lines), test structure, STACK.md

### Secondary (MEDIUM confidence)
- [Gunicorn settings](https://docs.gunicorn.org) — worker model, shared state considerations
- [redis-py docs](https://redis-py.readthedocs.io) — connection pooling, timeouts, error handling

---
*Research completed: 2026-07-19*
*Ready for roadmap: yes*
