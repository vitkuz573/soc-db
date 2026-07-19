# Technology Stack

**Project:** soc-db v2.1 Enterprise Hardening
**Researched:** 2026-07-19

## Recommended Stack (Additions to v2.0)

These are new dependencies required for v2.1 features. All existing dependencies (FastAPI, uvicorn, pydantic, beautifulsoup4, etc.) remain unchanged.

### New Core Dependencies

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `aiosqlite` | >=0.20 | Async SQLite database access | Native async without thread pools; replicates stdlib `sqlite3` API; well-maintained (Omnilib project). The async wrapper for all API database operations. |
| `redis[asyncio]` | >=5.0 | Redis client with async support | Industry-standard Redis client. Async support via `redis.asyncio`. Hiredis parser for performance (`redis[hiredis]`). Used for shared rate limiter state. |
| `opentelemetry-api` | >=1.25 | OpenTelemetry tracing API | Vendor-neutral telemetry API. Required for manual instrumentation of enrichment pipeline and DB queries. |
| `opentelemetry-sdk` | >=1.25 | OpenTelemetry SDK | Trace/metric/log export pipeline. Batch span processor, OTLP exporter. |
| `opentelemetry-instrumentation-fastapi` | >=0.45b | FastAPI automatic instrumentation | One-call setup (`FastAPIInstrumentor.instrument_app(app)`) for ASGI request tracing. Covers all HTTP routes. |
| `opentelemetry-exporter-otlp` | >=1.25 | OTLP exporter for traces/metrics | Standard protocol for exporting to any OTel-compatible backend (Jaeger, Grafana Tempo, Datadog, etc.). |

### New Development Dependencies

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `pytest-benchmark` | >=4.0 | Already present — verify FTS5 vs inverted index performance | Ensure SQLite queries are faster than current in-memory search. |

### Removal Candidates

| Package | Status | Reason |
|---------|--------|--------|
| `requests` | Remove from core deps | Only used by legacy scripts (excluded from pre-commit). Move to dev dependencies or remove. `urllib.request` is used in core library. |

### Key Stdlib Additions

| Module | Purpose | Why Not a Dependency |
|--------|---------|---------------------|
| `sqlite3` (stdlib) | Synchronous SQLite access for CLI | Python 3.12+ ships with SQLite. No install needed. CLI doesn't need async. |

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Async SQLite | `aiosqlite` | `asyncio.to_thread(sqlite3)` | Currently partially used. `aiosqlite` is cleaner, handles connection lifecycle, and avoids manual thread management. |
| Async SQLite | `aiosqlite` | `databases` library | Over-engineered for a single-file SQLite DB. `databases` adds query builder abstraction that doesn't match the existing dict-based patterns. |
| Async SQLite | `aiosqlite` | `sqlite-utils` (simonw) | Great library but wraps CLI use case; async support is via threads. `aiosqlite` is native async. |
| Rate limiter backend | Redis | In-memory (current) | Doesn't work with multiple workers. Redis is the standard solution for shared rate limiter state. |
| Rate limiter backend | Redis | Memcached | Redis sorted sets are a natural fit for sliding windows. Memcached lacks the data structures. |
| Observability | OpenTelemetry | Prometheus client directly | Vendor lock-in. OTel can export to Prometheus, Jaeger, Datadog, etc. Swappable exporter configuration. |
| Observability | OpenTelemetry | `logfire` | Too new, vendor-specific. OTel is the industry standard. |
| Full-text search | SQLite FTS5 | Custom inverted index (current) | Current index rebuilds entirely on cache miss. FTS5 is built-in, BM25 ranking, no rebuild needed. |
| Full-text search | SQLite FTS5 | Elasticsearch | Overkill for 1746 documents. FTS5 handles this easily. Can upgrade to ES in v2.2+ if scale demands. |
| Vendor knowledge source | Wikidata SPARQL | Wikipedia scraping (current) | Wikipedia infoboxes are inconsistent. Wikidata has structured data. SPARQL allows precise queries. |
| Vendor knowledge source | Wikidata SPARQL | Hardcoded dict (current) | Requires code changes for every new chip. SPARQL is dynamic. |

---

## Installation

```bash
# New core dependencies
pip install aiosqlite>=0.20 redis[hiredis]>=5.0
pip install opentelemetry-api>=1.25 opentelemetry-sdk>=1.25
pip install opentelemetry-instrumentation-fastapi>=0.45b
pip install opentelemetry-exporter-otlp>=1.25

# Update pyproject.toml dependencies
# Remove requests from core deps, add above
```

### Updated `pyproject.toml` dependencies section

```toml
dependencies = [
    "beautifulsoup4>=4.12",
    "lxml>=5.1",
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
    "pydantic>=2.5",
    "pydantic-settings>=2.2",
    "aiosqlite>=0.20",
    "redis[hiredis]>=5.0",
    "opentelemetry-api>=1.25",
    "opentelemetry-sdk>=1.25",
    "opentelemetry-instrumentation-fastapi>=0.45b",
    "opentelemetry-exporter-otlp>=1.25",
]
```

---

## Configuration Additions (config.py)

```python
# New settings for v2.1
db_path: Path = Path(__file__).resolve().parent.parent.parent / "data" / "soc-db.db"
use_json_fallback: bool = False  # Set True to skip SQLite, read JSON directly
redis_url: str | None = None     # e.g. "redis://localhost:6379/0"
otel_endpoint: str | None = None # e.g. "http://localhost:4317"
otel_service_name: str = "soc-db"
api_workers: int = 2             # uvicorn worker count
```

## Sources

- aiosqlite docs: https://aiosqlite.omnilib.dev/en/latest/ (HIGH confidence)
- redis-py async docs: https://redis.readthedocs.io/en/stable/examples/asyncio_examples.html (HIGH confidence)
- OpenTelemetry Python: https://opentelemetry.io/docs/languages/python/instrumentation/ (HIGH confidence)
- FastAPI OTel instrumentation: https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html (HIGH confidence)
- SQLite FTS5 docs: https://www.sqlite.org/fts5.html (HIGH confidence)
- Current STACK.md in codebase: `.planning/codebase/STACK.md` (HIGH confidence)
