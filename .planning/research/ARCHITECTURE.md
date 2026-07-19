# Architecture Patterns

**Project:** soc-db v2.1 Enterprise Hardening
**Researched:** 2026-07-19
**Mode:** Ecosystem (architecture integration analysis)
**Overall confidence:** HIGH

## Current Architecture (v2.0 — Baseline)

### Pattern: Modular Monolith

```
┌─────────────────────────────────────────────────┐
│                  CLI (argparse)                  │
│              src/soc_db/cli.py                   │
├─────────────────────────────────────────────────┤
│              REST API (FastAPI)                  │
│                 api/main.py                      │
├─────────────────────────────────────────────────┤
│           Scrapers / Pipeline (batch)            │
│  src/soc_db/scraper_*.py  |  scripts/*.py       │
├─────────────────────────────────────────────────┤
│           Core Library (src/soc_db/)             │
│  common.py  |  models.py  |  config.py          │
│  log_config.py  |  parsers.py                    │
├─────────────────────────────────────────────────┤
│              Data Store (JSON files)             │
│   data/*.json  |  schema/chip-schema.json        │
└─────────────────────────────────────────────────┘
```

### Current Data Flow (key problem areas)

1. **All data loaded into memory on cache miss** — `load_all()` in both `cli.py` and `api/main.py` reads all 44 JSON files synchronously. The API wraps this in `asyncio.to_thread()` but it's still bulk-load.
2. **Synchronous enrichment pipeline** — `enrich_one()` is 700+ lines, monolithic, synchronous.
3. **In-memory rate limiter** — `_rate_limit_buckets: dict[str, list[float]]` in `api/main.py` module scope. Does NOT work with multiple uvicorn workers (each worker has its own memory space).
4. **No observability** — Only structured JSON logging. No tracing, no metrics export.
5. **Hardcoded vendor knowledge** — `VENDOR_KNOWLEDGE` dict in `common.py` requires code changes for new chips.

---

## Target Architecture (v2.1)

### Layer Diagram — New Components Highlighted

```
                         ┌──────────────────────────────┐
                         │       GitHub Pages            │  ← UNTOUCHED
                         │   docs/ (static HTML/JS/CSS)  │     docs/ directory
                         │  index.html, 404.html, etc.   │     not migrated
                         └──────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│                    CLI (argparse)                         │
│                src/soc_db/cli.py                          │
│  Uses: db.sync_api, enrich.*                              │
├──────────────────────────────────────────────────────────┤
│                 REST API (FastAPI)                        │
│                    api/main.py                            │
│  Uses: db.async_api, enrich.*, OTel, Redis                │
├──────────────────────────────────────────────────────────┤
│              Scrapers / Pipeline (batch)                  │
│     src/soc_db/scraper_*.py  |  scripts/*.py             │
│  Uses: db.sync_api, enrich.*, wikidata_sparql.*           │
├──────────────────────────────────────────────────────────┤
│              Core Library (src/soc_db/)                   │
│  ┌────────────────────────────────────────────────────┐   │
│  │  enrich/     (NEW — replaces common.py sections)    │   │
│  │  ├── __init__.py   (pipeline orchestrator)          │   │
│  │  ├── cpu.py        (architecture, cores inference)  │   │
│  │  ├── gpu.py        (GPU map lookup, inference)      │   │
│  │  ├── memory.py     (memory type→clock/bus inference) │   │
│  │  ├── year.py       (year inference by vendor regex) │   │
│  │  ├── modem.py      (modem/NPU inference)            │   │
│  │  ├── wifi_bt.py    (Wi-Fi/Bluetooth year inference) │   │
│  │  ├── storage.py    (storage type inference)          │   │
│  │  ├── aliases.py    (codename alias generation)       │   │
│  │  └── scoring.py    (completeness scoring)            │   │
│  └────────────────────────────────────────────────────┘   │
│  ┌────────────────────────────────────────────────────┐   │
│  │  db/          (NEW — SQLite abstraction layer)      │   │
│  │  ├── __init__.py   (exports sync_api, async_api)    │   │
│  │  ├── sync_api.py   (sync connection, CLI helpers)   │   │
│  │  ├── async_api.py  (async connection via aiosqlite) │   │
│  │  ├── models.py     (SQLAlchemy-style or raw tables) │   │
│  │  ├── queries.py    (pre-built query builders)       │   │
│  │  ├── migrate.py    (JSON→SQLite migration runner)   │   │
│  │  └── fts.py        (FTS5 full-text search)          │   │
│  └────────────────────────────────────────────────────┘   │
│  ┌────────────────────────────────────────────────────┐   │
│  │  wikidata_sparql/ (NEW — Wikidata knowledge source) │   │
│  │  ├── __init__.py                                   │   │
│  │  ├── client.py    (SPARQL query wrapper)            │   │
│  │  ├── queries.py   (pre-built SPARQL query templates) │   │
│  │  └── maps.py      (process_map, gpu_map builders)   │   │
│  └────────────────────────────────────────────────────┘   │
│  models.py  |  config.py  |  log_config.py                │
│  parsers.py  |  common.py (deprecated/legacy shim)        │
├──────────────────────────────────────────────────────────┤
│              Data Stores                                  │
│  ┌──────────────────┐  ┌──────────────┐  ┌────────────┐  │
│  │  data/*.json      │  │  soc-db.db   │  │  Redis     │  │
│  │  (legacy/migrate  │  │  (SQLite —   │  │  (rate     │  │
│  │   source, frozen) │  │   primary)   │  │   limiter) │  │
│  └──────────────────┘  └──────────────┘  └────────────┘  │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│           Cross-Cutting Infrastructure (NEW)              │
│  ┌────────────────────────────────────────────────────┐   │
│  │  OpenTelemetry         (instrumentation/otel.py)    │   │
│  │  ├── FastAPIInstrumentor (auto ASGI tracing)        │   │
│  │  ├── SQLite tracing      (db query spans)            │   │
│  │  ├── Redis tracing       (rate limiter spans)        │   │
│  │  └── Enrichment spans    (custom enrich pipeline)    │   │
│  └────────────────────────────────────────────────────┘   │
│  ┌────────────────────────────────────────────────────┐   │
│  │  Redis Client          (infra/redis.py — NEW)       │   │
│  │  ├── Connection pool (redis.asyncio)                │   │
│  │  ├── Rate limiter impl (sliding window in Redis)    │   │
│  │  └── Health check                                   │   │
│  └────────────────────────────────────────────────────┘   │
│  ┌────────────────────────────────────────────────────┐   │
│  │  Deployment Config   (deploy/* — MODIFIED)          │   │
│  │  ├── uvicorn workers = N (>1 requires Redis)        │   │
│  │  ├── SQLite file path, Redis URL in env vars        │   │
│  │  └── OTel endpoint config (OTEL_EXPORTER_*)         │   │
│  └────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `cli.py` | CLI entry point, argparse dispatch | `db.sync_api`, `enrich.*` |
| `api/main.py` | FastAPI server, middleware, route handlers | `db.async_api`, `enrich.*`, OTel, Redis |
| `scraper_*.py` | Web scraping Wikipedia/Apple | `enrich.*`, `db.sync_api`, `common.fetch()` |
| `enrich/` | Per-domain enrichment modules (cpu, gpu, year, etc.) | `models.py` (via Chip dict), optionally `wikidata_sparql` |
| `db/` | SQLite abstraction (sync + async), FTS5, migration | SQLite file, `models.py` (schema mapping) |
| `wikidata_sparql/` | SPARQL query → vendor knowledge maps | Wikidata public endpoint, `enrich/` as consumer |
| `infra/redis.py` | Redis connection pool, rate limiter implementation | Redis server, `api/main.py` middleware |
| `instrumentation/otel.py` | OTel tracer/metric setup, FastAPI instrumentation, custom spans | OTel collector endpoint, all other layers |
| `docs/` | Static site — **untouched** | GitHub Pages build |

---

## Data Flow Changes

### Before (v2.0) — CLI query

```
soc-db query --vendor Qualcomm
  → cli.py:main() → cmd_query()
  → cli.py:load_all() → data/*.json (reads ALL 44 files)
  → filter chain (Python list comprehensions)
  → JSON/CSV/table output
```

### After (v2.1) — CLI query

```
soc-db query --vendor Qualcomm
  → cli.py:main() → cmd_query()
  → db.sync_api.query(vendor="Qualcomm")
    → sqlite3.execute("SELECT * FROM chips WHERE vendor = ?", ("Qualcomm",))
    → returns list[dict] (SQLite handles filtering)
  → JSON/CSV/table output
```

**Key change:** SQLite does the filtering, not Python. No bulk load into memory.

### Before (v2.0) — API request

```
GET /v1/chips?vendor=Qualcomm&limit=5
  → uvicorn (single worker) → FastAPI routing
  → get_chips() → cache check (TTL 300s)
    → cache miss: load_all() → reads ALL 44 JSON files
    → builds full inverted search index
  → filter + paginate → json.dumps → JSONResponse
```

### After (v2.1) — API request

```
GET /v1/chips?vendor=Qualcomm&limit=5
  → uvicorn (N workers) → FastAPI routing
  → Rate limiter middleware → Redis.sliding_window_check(client_ip)
    → Redis SCARD / ZREMRANGEBYSCORE / ZADD
  → OTel span created (auto via FastAPIInstrumentor)
  → db.async_api.query(vendor="Qualcomm", limit=5)
    → aiosqlite.execute("SELECT ... FROM chips WHERE vendor = ? LIMIT ?", (...))
    → async row fetch → Pydantic validation
  → OTel span closed
  → JSONResponse
```

**Key changes:**
- Async SQLite query (non-blocking)
- No in-memory cache — SQLite handles it
- No companion search index — FTS5 handles full-text search
- Rate limiter in Redis (shared across workers)
- OTel trace every request

### Before (v2.0) — Enrichment

```
enrich_one(chip)
  → Pipeline: cleanup → model fallback → memory → process → GPU
    → year → Wi-Fi/BT → modem → NPU → storage → aliases → score → sources
  → One 700+ line function
  → VENDOR_KNOWLEDGE dict for process/gpu maps
```

### After (v2.1) — Enrichment

```
enrich_one(chip)
  → Pipeline orchestrator (enrich/__init__.py)
    → cleanup()          (enrich/__init__.py — inline)
    → model_fallback()   (enrich/__init__.py)
    → memory.infer()     (enrich/memory.py — extracted)
    → cpu.infer()        (enrich/cpu.py — extracted)
    → gpu.infer()        (enrich/gpu.py — extracted)
    → year.infer()       (enrich/year.py — extracted, the big one)
    → wifi_bt.infer()    (enrich/wifi_bt.py — extracted)
    → modem.infer()      (enrich/modem.py — extracted)
    → storage.infer()    (enrich/storage.py — extracted)
    → aliases.generate() (enrich/aliases.py — extracted)
    → scoring.compute()  (enrich/scoring.py — extracted)

VENDOR_KNOWLEDGE replaced by:
  - wikidata_sparql.maps.get_process_map(vendor)  # dynamic SPARQL query
  - wikidata_sparql.maps.get_gpu_map(vendor)
  - Fallback: local cache of last SPARQL results
```

**Key changes:**
- Each domain is its own module, unit-testable in isolation
- `VENDOR_KNOWLEDGE` hardcoded dict replaced with SPARQL-driven lookup
- Year inference extracted to `enrich/year.py` (still the biggest piece, but now isolated)

---

## JSON → SQLite Migration Strategy

### Principle: Zero-Downtime, Backward-Compatible

The migration must NOT break:
- API contracts (same endpoints, same response shapes)
- CLI commands (same flags, same output)
- GitHub Pages (docs/ directory untouched)
- Running servers (no required downtime)

### Migration Phases

```
Phase A: Dual-read (coexistence)
  ┌─────────────────────────────┐
  │  app reads from JSON files  │ ← existing behavior
  │  Migration script runs:     │
  │    JSON → SQLite (offline)  │
  │  verify: row counts match   │
  └─────────────────────────────┘

Phase B: Cutover (SQLite primary)
  ┌─────────────────────────────┐
  │  app reads from SQLite      │ ← new default
  │  JSON files still present   │ ← backup/rollback
  │  load_all() falls back to   │
  │  JSON if SQLite missing     │
  └─────────────────────────────┘

Phase C: Legacy cleanup (optional)
  ┌─────────────────────────────┐
  │  JSON files become optional │
  │  Makefile target:           │
  │    make migrate-from-json   │
  │  data/*.json → git lfs or   │
  │  archive                    │
  └─────────────────────────────┘
```

### Specific Migration Mechanics

1. **Schema Design:** Single `chips` table with all 95 fields as columns. JSON fields (`aliases`, `sources`, `gpu_api`, `tags`, `devices`, `alternative_names`) stored as JSON text. JSON Schema validation moves from file-level to pre-insert check.

2. **FTS5 Virtual Table:** Companion `chips_fts` table for full-text search on `name`, `model`, `description`, `codename` columns. Eliminates the Python-level inverted index (`_build_search_index()` in `api/main.py`).

3. **Migration Script:** `python -m soc_db.db.migrate` reads all 44 JSON files, transforms, inserts into SQLite. Output: `data/soc-db.db`. Reports row count per vendor and total.

4. **Verification:** After migration, run `SELECT COUNT(*) FROM chips` against each vendor's JSON file count. Must match exactly.

5. **Rollback:** Set `SOC_DB_USE_JSON=true` env var to force read from JSON files. No data loss.

### SQLite Schema

```sql
CREATE TABLE chips (
    id TEXT PRIMARY KEY,                    -- "sm8250_kona"
    name TEXT NOT NULL,                     -- "Snapdragon 865"
    vendor TEXT NOT NULL,                   -- "Qualcomm"
    model TEXT,
    aliases TEXT,                           -- JSON array as text
    codename TEXT,
    description TEXT,
    architecture TEXT,
    isa TEXT,
    cores INTEGER,
    threads INTEGER,
    cluster_config TEXT,
    clock_max INTEGER,
    clock_mid INTEGER,
    clock_min INTEGER,
    max_freq TEXT,
    process_nm INTEGER,
    process_name TEXT,
    process TEXT,
    cache TEXT,                             -- JSON object
    tdp REAL,
    gpu TEXT,
    gpu_clock INTEGER,
    gpu_api TEXT,                           -- JSON array
    gpu_tflops REAL,
    memory_type TEXT,
    memory_max INTEGER,
    memory_clock INTEGER,
    memory_bus INTEGER,
    memory_bandwidth INTEGER,
    storage_type TEXT,
    npu TEXT,
    ai_ops REAL,
    modem TEXT,
    modem_dl INTEGER,
    modem_ul INTEGER,
    cellular TEXT,
    video_decode TEXT,
    video_encode TEXT,
    display_max TEXT,
    camera_max TEXT,
    isps INTEGER,
    video_capture TEXT,
    wifi TEXT,
    bluetooth TEXT,
    usb TEXT,
    navigation TEXT,
    charging TEXT,
    year INTEGER CHECK(year >= 2007 AND year <= 2030),
    announced TEXT,                         -- ISO date
    revision TEXT,
    status TEXT DEFAULT 'unknown',
    completeness REAL,
    sources TEXT,                           -- JSON object
    updated TEXT,                           -- ISO date
    datasheet_url TEXT,
    wikipedia_url TEXT,
    wikidata_id TEXT,
    linux_dt_compatible TEXT,
    devices TEXT,                           -- JSON array
    alternative_names TEXT,                 -- JSON array
    parent TEXT,
    tags TEXT,                              -- JSON array
    rating TEXT,                            -- JSON object
    benchmarks TEXT,                        -- JSON object
    _enriched_at TEXT,                      -- metadata: last enrichment timestamp
    _data_version INTEGER DEFAULT 1,        -- metadata: schema version for future migrations
    UNIQUE(model, vendor)                   -- prevent duplicates
);

-- FTS5 for full-text search
CREATE VIRTUAL TABLE chips_fts USING fts5(
    id, name, vendor, model, description, codename,
    content='chips',
    content_rowid='rowid'
);

-- Indexes for common query patterns
CREATE INDEX idx_chips_vendor ON chips(vendor);
CREATE INDEX idx_chips_year ON chips(year);
CREATE INDEX idx_chips_architecture ON chips(architecture);
CREATE INDEX idx_chips_gpu ON chips(gpu);
CREATE INDEX idx_chips_completeness ON chips(completeness);
```

---

## Integration Points for Each New Feature

### 1. Refactor common.py into `enrich/` modules

| Aspect | Detail |
|--------|--------|
| **New location** | `src/soc_db/enrich/{cpu,gpu,memory,year,modem,wifi_bt,storage,aliases,scoring}.py` |
| **Breaking change?** | No — `common.py` becomes a compatibility shim, forwarding `enrich_one()` to the pipeline |
| **Integration** | `enrich/__init__.py` exports `enrich_one()`, `enrich_all()` |
| **Consumers** | CLI (`cli.py`), API (`api/main.py`), scrapers (`scraper_*.py`) — all import unchanged |
| **Global state** | `VENDOR_KNOWLEDGE` replaced by `wikidata_sparql/` module + local cache |

### 2. SQLite database

| Aspect | Detail |
|--------|--------|
| **New location** | `src/soc_db/db/` |
| **Integration point** | `config.py` gets `db_path: Path` and `use_json_fallback: bool` settings |
| **CLI integration** | `cli.py:load_all()` → `db.sync_api.get_all_chips()` (sync sqlite3) |
| **API integration** | `api/main.py:get_chips()` → `db.async_api.query(...)` (aiosqlite) |
| **Scraper integration** | `scraper_*.py:write_vendor_file()` → `db.sync_api.bulk_upsert(vendor, chips)` |
| **File location** | `data/soc-db.db` (default, configurable via `SOC_DB_PATH`) |
| **GitHub Pages risk** | **NONE** — `docs/` directory is static. No reference to `data/` in GitHub Pages build. |

### 3. Async data access via aiosqlite

| Aspect | Detail |
|--------|--------|
| **Library** | `aiosqlite` — wraps stdlib `sqlite3` in async context |
| **Integration point** | `db/async_api.py` uses `aiosqlite.connect()` |
| **Connection lifecycle** | One connection per request, or connection pool via `async with aiosqlite.connect()` |
| **CLI compatibility** | CLI stays synchronous using `db/sync_api.py` (stdlib `sqlite3`) |
| **API compatibility** | API route handlers become fully async; no more `asyncio.to_thread()` wrappers needed |
| **Thread safety** | `aiosqlite` uses shared-thread-per-connection; safe for concurrent requests |

### 4. Redis integration for shared rate limiter

| Aspect | Detail |
|--------|--------|
| **Library** | `redis[hiredis]` (redis-py >=5.0, async via `redis.asyncio`) |
| **Integration point** | `api/main.py` rate limiter middleware → `RedisRateLimiter` class |
| **New file** | `src/soc_db/infra/redis.py` (or inline in `api/main.py`) |
| **Sliding window impl** | Redis Sorted Set per IP: `ZREMRANGEBYSCORE`, `ZADD`, `ZCARD` |
| **Fallback** | If Redis unavailable, log warning and fall back to in-memory limiter (per-worker) |
| **Config** | `SOC_DB_REDIS_URL` env var (default: none — limiter falls back to in-memory) |
| **Deployment** | Redis must be running for multi-worker setups; single-worker okay without |

```
Redis key structure:
  ratelimit:{client_ip}:{window_start}

Window algorithm:
  1. ZREMRANGEBYSCORE ratelimit:192.168.1.1:1710800000 -inf (now - 60s)
  2. ZCARD → if >= limit, reject
  3. ZADD timestamp
  4. EXPIRE 60s
```

### 5. OpenTelemetry instrumentation

| Aspect | Detail |
|--------|--------|
| **Library** | `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi` |
| **Integration point** | `api/main.py` lifespan: configure OTel provider, instrument FastAPI |
| **Custom spans** | `enrich/` pipeline gets manual spans per domain module |
| **DB tracing** | `db/async_api.py` wraps queries in spans |
| **Exporter** | OTLP exporter (configurable via `OTEL_EXPORTER_OTLP_ENDPOINT`) |
| **Console fallback** | If no endpoint configured, export to console for dev |
| **New file** | `src/soc_db/instrumentation/otel.py` — `setup_otel()` function |

```python
# instrumentation/otel.py — pseudocode
def setup_otel(app: FastAPI, service_name="soc-db"):
    provider = TracerProvider()
    processor = BatchSpanProcessor(OTLPSpanExporter())
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=provider,
        excluded_urls="/health,/metrics",
    )
```

### 6. Multi-worker uvicorn deployment

| Aspect | Detail |
|--------|--------|
| **Change** | CLI flag: `uvicorn api.main:app --workers 4` (was `--workers 2`) |
| **Architectural impact** | Redis becomes required if `workers > 1` (rate limiter state no longer in-process) |
| **SQLite concurrency** | SQLite supports multiple readers, single writer. WAL mode must be enabled. |
| **WAL mode** | `PRAGMA journal_mode=WAL;` — allows concurrent reads without blocking |
| **Config** | `SOC_DB_WORKERS` env var added to `config.py` |

### 7. Wikidata SPARQL for vendor knowledge

| Aspect | Detail |
|--------|--------|
| **Endpoint** | `https://query.wikidata.org/sparql` |
| **New files** | `src/soc_db/wikidata_sparql/` package |
| **Integration** | Called during enrichment, results cached in SQLite or on disk |
| **Cache TTL** | 24h default (vendor knowledge doesn't change hourly) |
| **Fallback** | If SPARQL query fails, fall back to cached results, then to hardcoded defaults |
| **Pre-built queries** | `queries.py` contains SPARQL templates for process nodes, GPU models by vendor |

---

## Key Abstraction: Dual Interface Pattern

Both CLI (sync) and API (async) need database access. The architectural pattern is:

```python
# db/sync_api.py
import sqlite3
from pathlib import Path

class SyncChipDB:
    def __init__(self, db_path: Path):
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row

    def get_all_chips(self) -> list[dict]:
        cur = self._conn.execute("SELECT * FROM chips")
        return [dict(row) for row in cur.fetchall()]

    def get_chip(self, chip_id: str) -> dict | None:
        cur = self._conn.execute("SELECT * FROM chips WHERE id = ?", (chip_id,))
        row = cur.fetchone()
        return dict(row) if row else None

# db/async_api.py
import aiosqlite
from pathlib import Path

class AsyncChipDB:
    def __init__(self, db_path: Path):
        self._db_path = db_path

    async def get_all_chips(self) -> list[dict]:
        async with aiosqlite.connect(str(self._db_path)) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM chips")
            rows = await cur.fetchall()
            return [dict(row) for row in rows]

    async def get_chip(self, chip_id: str) -> dict | None:
        async with aiosqlite.connect(str(self._db_path)) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM chips WHERE id = ?", (chip_id,))
            row = await cur.fetchone()
            return dict(row) if row else None
```

---

## Patterns to Use

### Pattern 1: Repository Pattern for DB Access
**What:** Abstract data access behind a repository interface that can be swapped (JSON vs SQLite).
**When:** During migration Phase A (dual-read), both `JsonChipRepository` and `SqliteChipRepository` implement the same protocol.
**Why:** Allows gradual migration. The API tests the SQLite path while JSON runs in production. Cutover is a single config flag.
**Example:**
```python
class ChipRepository(Protocol):
    def get_all(self) -> list[dict]: ...
    def get_by_id(self, chip_id: str) -> dict | None: ...
    def search(self, query: str) -> list[dict]: ...
```

### Pattern 2: Async Wrapper for Sync DB
**What:** Keep `aiosqlite` queries async in API layer, `sqlite3` synchronous in CLI layer. Share query logic.
**When:** Always. CLI has no async event loop; API runs entirely in async context.
**Why:** Avoids `asyncio.to_thread()` overhead for the common CLI case.
**Implementation:**
```python
# db/queries.py — shared query logic
QUERY_ALL_CHIPS = "SELECT * FROM chips"
QUERY_BY_VENDOR = "SELECT * FROM chips WHERE vendor = ?"

# Consumed by both sync_api.py and async_api.py
```

### Pattern 3: Dependency Injection for External Services
**What:** Redis client, SQLite connection, OTel tracer are injected via FastAPI `lifespan` → `app.state`.
**When:** API server startup.
**Why:** Makes testing trivial (replace with mocks). Avoids global state.
**Example:**
```python
@asynccontextmanager
async def lifespan(app):
    redis = await create_redis_pool()
    db = AsyncChipDB(settings.db_path)
    otel = setup_otel(app)
    app.state.redis = redis
    app.state.db = db
    yield
    await redis.aclose()
    await db.close()
```

### Pattern 4: FTS5 for Full-Text Search
**What:** SQLite FTS5 virtual table replaces the Python-level inverted index (`_build_search_index()`).
**When:** After SQLite cutover (Phase B).
**Why:** FTS5 is built into SQLite, supports BM25 ranking, tokenizers, and prefix queries. Eliminates 100+ lines of custom search code.
**Example:**
```sql
SELECT * FROM chips WHERE rowid IN (
    SELECT rowid FROM chips_fts WHERE chips_fts MATCH ?
)
ORDER BY rank
LIMIT ?
```

### Pattern 5: Enrichment Pipeline as Strategy Chain
**What:** Each enrichment domain module implements a standard `infer(chip) -> chip` signature. Pipeline orchestrator calls them in order.
**When:** After refactoring `common.py`.
**Why:** Each module independently unit-testable. Can add/remove steps without touching the pipeline.
**Example:**
```python
# enrich/__init__.py
PIPELINE_STEPS = [
    ("cleanup", cleanup),
    ("model", model_fallback),
    ("memory", memory.infer),
    ("gpu", gpu.infer),
    ("year", year.infer),
    ("wifi_bt", wifi_bt.infer),
    ("modem", modem.infer),
    ("storage", storage.infer),
    ("aliases", aliases.generate),
    ("scoring", scoring.compute),
]

def enrich_one(chip: dict) -> dict:
    for name, step in PIPELINE_STEPS:
        with tracer.start_as_current_span(f"enrich.{name}"):
            step(chip)
    return chip
```

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Global SQLite Connection
**What:** Opening a single SQLite connection at module level and sharing across threads/requests.
**Why bad:** SQLite connections are not thread-safe by default. Concurrent writes corrupt data.
**Instead:** Per-request connection (async) or connection from a properly managed pool.

### Anti-Pattern 2: Sync-ifying Async Calls
**What:** Using `asyncio.run()` or `.result()` on async DB calls inside CLI handlers.
**Why bad:** Creates nested event loops, blocks the thread, defeats the purpose of async.
**Instead:** CLI uses `sync_api.py` with stdlib `sqlite3`. API uses `async_api.py` with `aiosqlite`. Separate entry points.

### Anti-Pattern 3: Embedding SQL in Route Handlers
**What:** Writing raw SQL strings in `api/main.py` route functions.
**Why bad:** Tight coupling, untestable, hard to audit, schema changes require hunting through route code.
**Instead:** All SQL lives in `db/queries.py`. Route handlers call named functions: `db.async_api.search_chips("Qualcomm")`.

### Anti-Pattern 4: Removing JSON Files Too Early
**What:** Deleting `data/*.json` immediately after SQLite migration.
**Why bad:** Migration bugs are inevitable. The JSON files are the rollback mechanism and the source of truth for git diffs.
**Instead:** Keep JSON files as "frozen source of truth" through v2.1. Only consider deprecation in v2.2+.

### Anti-Pattern 5: Infinite OTel Spans
**What:** Creating spans in every function call, including trivial getters.
**Why bad:** Noise drowns signal. Excessive overhead.
**Instead:** Spans at natural boundaries: request entry, DB query, Redis call, enrichment step (not individual regex matches within steps).

---

## Scalability Considerations

| Concern | At 100 users (current) | At 10K users | At 1M users |
|---------|------------------------|--------------|-------------|
| **Data access** | SQLite (sync/async) | SQLite with WAL mode + connection pooling | PostgreSQL migration needed; SQLite hits write concurrency limit |
| **Rate limiting** | In-memory falls back from Redis | Redis required (shared state) | Redis Cluster or alternative |
| **Enrichment** | Synchronous per-request | Async enrichment with caching | Background worker queue for enrichment |
| **Observability** | OTel console exporter | OTel to local collector | OTel to distributed collector cluster |
| **API serving** | 2-4 uvicorn workers | 8-16 workers behind nginx | Kubernetes HPA autoscaling |
| **Search** | SQLite FTS5 | SQLite FTS5 (good up to ~100K docs) | Elasticsearch or Meilisearch sidecar |

**SQLite scaling ceiling:** ~50 concurrent writers (WAL mode helps readers but writers serialize). At 10K API users the read load is fine. At 1M users or with frequent enrichment writes, PostgreSQL becomes necessary. This is a v2.2+ concern.

---

## GitHub Pages Safety Analysis

**CRITICAL CONSTRAINT:** The `docs/` directory must NOT be modified by any migration or deployment pipeline.

| Risk | Impact | Mitigation |
|------|--------|------------|
| Migration script writes to `docs/` | GitHub Pages serves corrupted content | Migration script explicitly excludes `docs/` from all file operations. Only `data/*.db` file is created. |
| SQLite file placed in `docs/` | Unnecessary file in GitHub Pages build | `data/soc-db.db` stays in `data/`. GitHub Pages doesn't serve `data/`. |
| CI pipeline touches `docs/` during migration | Swagger/OpenAPI could be affected | CI pipeline configuration explicitly excludes `docs/` from migration steps. |
| Git ignore for `.db` files | Not committing binary DB to git | `.gitignore` gets `*.db` entry. Source of truth remains the JSON files (committed). SQLite is build artifact. |

**Conclusion:** Zero risk to GitHub Pages. The `docs/` directory contains only static HTML/JS/CSS. The SQLite database file lives in `data/` which is not published to GitHub Pages. The migration is a local operation that reads JSON from `data/` and writes SQLite to `data/`.

---

## Suggested Build Order

| Order | Feature | Rationale | Dependencies |
|-------|---------|-----------|--------------|
| 1 | `enrich/` module extraction | Foundation for everything else. No new dependencies. | None |
| 2 | `db/` SQLite + migration | Core data store change. Need this before async. | 1 (enrich uses db to store results) |
| 3 | `db/async_api.py` (aiosqlite) | Async access for API. SQLite must exist first. | 2 |
| 4 | `infra/redis.py` rate limiter | Multi-worker enabler. Can deploy in parallel with 3. | 2 |
| 5 | `api/main.py` OTel instrumentation | Observability layer. API must be stable first. | 3, 4 |
| 6 | `wikidata_sparql/` vendor knowledge | Replaces VENDOR_KNOWLEDGE. Independent of DB migration. | 1 |
| 7 | Multi-worker deployment config | Final deployment hardening. All infra pieces must exist. | 3, 4, 5 |

---

## Sources

- sqlite3 stdlib docs: https://docs.python.org/3/library/sqlite3.html (HIGH confidence)
- aiosqlite docs: https://aiosqlite.omnilib.dev/en/latest/ (HIGH confidence)
- redis-py async docs: https://redis.readthedocs.io/en/stable/examples/asyncio_examples.html (HIGH confidence)
- OpenTelemetry Python FastAPI instrumentation: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html (HIGH confidence)
- Codebase analysis of soc-db v2.0 (1746+ chips, 44 vendor files, 405 tests) (HIGH confidence)
- SQLite WAL mode documentation: https://www.sqlite.org/wal.html (HIGH confidence)
- Wikidata SPARQL endpoint: https://query.wikidata.org/sparql (HIGH confidence)
