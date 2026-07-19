# Pitfalls Research: soc-db v2.1 Enterprise Hardening

**Domain:** Python SoC database monolith → hardened enterprise service
**Researched:** 2026-07-19
**Overall confidence:** HIGH

## Critical Pitfalls

### Pitfall 1: REGRESSION — Year Inference Breaks After refactoring

**What goes wrong:**
The `enrich_one()` function (~700 lines of if/elif year inference in common.py:799-1328) gets split into per-vendor modules. During extraction, subtle ordering dependencies between regex branches are lost — earlier patterns act as gates for later ones. The `break` statements in the giant chain mean extraction order matters. A Qualcomm chip that ALSO matches a MediaTek pattern (because "MT" appears in a description field) could get the wrong year.

**Why it happens:**
- The year inference chain has implicit ordering: MediaTek patterns (`MT\d{4}`) are checked BEFORE Qualcomm patterns (`SM\d{4}`). This ordering dependency is NOT documented anywhere.
- The chain uses `break` at every match — first match wins. When split into `infer_year_mediatek()`, `infer_year_qualcomm()`, etc., the calling code must maintain the original priority order or results diverge.
- Test coverage for year inference is excellent (180+ parametrized tests) BUT tests may have been written to match the current (possibly wrong) behavior — refactoring to the "correct" logic could fail existing tests.

**How to avoid:**
1. **Extract without changing logic FIRST** — before any refactoring, wrap the entire 530-line block in `infer_year(chip) -> int | None`. Move it as-is. Then extract sub-functions one at a time while preserving call order.
2. **Add a year-inference snapshot test** — run `enrich_one()` across ALL 1746 chips, record `(chip_id, year_before)`. After refactoring, assert all years match. This catches regressions the unit tests miss.
3. **Document the priority chain explicitly** — create a comment or README that lists vendor priority order for year inference.
4. **Use `git diff --stat` before/after** — the refactored version should produce identical `year` field for all chips.

**Warning signs:**
- Any extraction that moves code between files and the tests still pass — suspicious (might mean tests are too weak)
- CI build shows changed `data/*.json` files after running the pipeline — regression has already occurred
- A chip's year changed but the chip data wasn't intentionally modified

**Phase to address:**
REFAC-01 (refactoring common.py). Add snapshot test BEFORE starting extraction. Verify snapshot AFTER each sub-extraction.

---

### Pitfall 2: SCHEMA_DRIFT — JSON → SQLite Migration Breaks API Responses

**What goes wrong:**
The API (`api/main.py`) returns chip records as flat dicts with specific field names, types, and nesting. After migrating from JSON flat files to SQLite, the schema doesn't perfectly match. A field stored as `INTEGER` in SQLite was previously a string in JSON. A nested field like `sources` gets flattened. `null` vs `None` vs missing-key semantics shift. The API starts returning subtly different shapes — downstream consumers (GitHub Pages UI, CLI, API clients) break silently.

**Why it happens:**
- JSON allows heterogeneous types per-record; SQLite enforces a single type per column
- Fields like "aliases" (a list) get stored as JSON text in SQLite — code that previously got `chip["aliases"][0]` now gets `json.loads(chip["aliases"])[0]` — if the deserialization isn't added everywhere, it breaks
- The `completeness` float could get rounded by SQLite's REAL type vs Python's full precision
- `null` vs absent key: JSON can omit a field entirely; SQLite always returns `None` for NULL columns — code that checks `"year" in chip` now gets `chip.get("year") is not None` behavior change

**How to avoid:**
1. **Create a SQLite→dict mapping layer** — never expose raw SQLite rows to the API. Use `ChipResponse` Pydantic model to normalize DB rows into the same dict shape as before.
2. **Schema-as-contract** — freeze the API response schema (the Pydantic models in `models.py`). Ensure SQLite schema is derived FROM the Pydantic models, not the other way around.
3. **Migration dry-run** — run `INSERT ... SELECT` from old JSON to new SQLite, then `SELECT *` and diff against the original JSON for ALL 1746 chips field-by-field.
4. **API integration test with frozen responses** — record the API responses for a representative query BEFORE migration. After migration, assert the response JSON is byte-identical for the same query.

**Warning signs:**
- `list_fields = cursor.fetchone()` — missing `.description` for column names (code assumes column order)
- `SELECT *` in migration queries — column order depends on schema creation order
- Any code that accesses `row[3]` by position instead of `row["field_name"]` — fragile

**Phase to address:**
DB-01 (SQLite migration). API backward compat tests must pass in the SAME phase.

---

### Pitfall 3: SECRETS_LEAK — PyPI Publishing Exposes API Key or Tokens

**What goes wrong:**
The PyPI publishing CI/CD pipeline accidentally includes `.env`, `config.yaml`, or hardcoded tokens in the built wheel/sdist. API keys, Wikidata tokens, or Redis credentials get published to PyPI where anyone can download and inspect. The `.gitignore` excludes these files from git, but the build process may capture them anyway (e.g., via `include` in `MANIFEST.in`, or via a `pyproject.toml` glob that grabs everything).

**Why it happens:**
- `pyproject.toml` has `[tool.setuptools.packages.find]` with `include = ["soc_db*"]` — but dependencies like `requests` are still listed as core deps when they should be dev-only
- Secrets get injected at build time (e.g., during `python -m build`) via environment variables that leak into `config.py` via `os.getenv()` — if `config.py` falls back to a default value at build time, that default gets baked into the package
- The `data/` directory (chip JSON files) is shipped with the package — if any token or secret was accidentally written to a JSON file during enrichment, it ships to PyPI

**How to avoid:**
1. **Explicit `MANIFEST.in` with excludes** — `include src/soc_db/*.py` and NOT `include data/*` (data should be downloaded at runtime, not bundled)
2. **CI publish job runs `twine check`** — this verifies the package before upload
3. **Pre-publish dry-run** — `python -m build` then `tar tf dist/*.tar.gz` and inspect for unexpected files
4. **Use OpenID Connect (OIDC) for PyPI auth** — never store PyPI tokens as repo secrets; use trusted publishing
5. **Run `bandit` on the built package** — bandit can detect potential secret patterns in distributed code
6. **`detect-secrets` or `trufflehog` scan in CI** before publish step

**Warning signs:**
- `.env` or `.env.*` files exist near `src/` or in the repo root
- `data/` or `config/` directories are listed in `MANIFEST.in` or `include` in `pyproject.toml`
- The `[tool.setuptools.package-data]` section includes wildcards like `*.*` or `**/*`

**Phase to address:**
RELEASE-01 (PyPI publishing). Add pre-publish security scanning in the same phase.

---

### Pitfall 4: EVENT_LOOP_BLOCK — Mixing Sync/Async Blocks All Concurrent Requests

**What goes wrong:**
The API currently uses `asyncio.to_thread()` in `load_all_async()` but `get_chips()` still calls sync `load_all()` directly (CONCERNS.md confirms this). When the migration makes more of the data layer async, some synchronous calls remain — `urlopen()` in `fetch()`, `json.loads()` on large files, `re.search()` in the enrichment pipeline. A single synchronous call blocks the entire event loop, making ALL concurrent requests wait. Under load, this looks like the API is hanging.

**Why it happens:**
- Python's GIL doesn't help here — CPU-bound operations (regex on 1746 records) block the event loop thread
- `aiosqlite` is used for DB access, but enrichment logic remains synchronous — calling `enrich_one()` from an async route blocks everything
- The current `load_all()` already uses `asyncio.to_thread()` but it's the wrong direction — `to_thread` is a band-aid, not a proper async data layer
- Thread pool executors have a default max_workers of `min(32, os.cpu_count() + 4)` — if ALL 1746 chips are enriched in threads, the pool saturates

**How to avoid:**
1. **Run sync enrichment in `run_in_executor()` with a dedicated `ProcessPoolExecutor`** — CPU-bound regex work should NOT share the thread pool with I/O work
2. **Profile with structured logging** — add a logging statement before/after every potentially blocking call with timing. If any non-async call takes >50ms, flag it
3. **Use `asyncio.to_thread()` ONLY for I/O-bound sync operations** — file reads, network calls. NOT for CPU-bound regex matching
4. **Test with `--workers 4` under load** — run `wrk -t 4 -c 20 http://localhost:8000/v1/chips` and check response times don't degrade with concurrency
5. **`uvicorn`'s `--loop uvloop` and `--http httptools`** for maximum async performance

**Warning signs:**
- `time.sleep()` or `sleep()` anywhere in async code (use `asyncio.sleep()`)
- `urlopen()` or `requests.get()` in async functions (use `httpx.AsyncClient`)
- `json.loads()` on large payloads (4MB+) in async function (use `asyncio.to_thread()`)
- Any function decorated with `@app.get(...) async def` that calls a sync function doing CPU work

**Phase to address:**
ASYNC-01 (async data layer). Must also audit SYNC-01 (non-async code audit) in parallel.

---

### Pitfall 5: FLAKY_CI — Data Validation Dashboard Produces False Positives

**What goes wrong:**
The data validation CI job runs periodically (e.g., daily) or on every PR. It validates all 1746 chip records against the JSON schema, checks for anomalies (missing year, improbable process node, etc.). When validation is flaky — failing sometimes, passing others — developers learn to ignore CI failures. Real data corruption gets merged because "the validation is just being noisy again."

**Why it happens:**
- Validation depends on external APIs (Wikidata, Wikipedia scrapers) that have rate limits or partial availability
- Validation includes time-sensitive checks ("year should not be future") that produce different results at different times of year
- Random sampling: "validate random 100 chips" passes or fails depending on which chips are sampled
- Schema changes happen mid-development but the validation job runs against the wrong schema version
- Property-based tests (see Pitfall 6) fail nondeterministically

**How to avoid:**
1. **Deterministic validation** — NEVER validate against live external APIs in CI. Use recorded fixtures. Validate against Wikidata in a separate scheduled job that alerts, not blocks.
2. **Pin validation schema** — the CI validation job should pin to the SCHEMA_VERSION of the commit being validated, not HEAD
3. **Separate "gating" from "monitoring"** — PRs should be gated on deterministic checks only. Scheduled validation should monitor trends.
4. **Add `@pytest.mark.flaky(reruns=3)`** for any test that MUST call external services — but mark it explicitly as flaky
5. **Threshold-based alerts instead of binary pass/fail** — "schema validation rate dropped below 99.5%"

**Warning signs:**
- CI tests that `assert requests.get(url).status_code == 200` (network-dependent)
- Tests that depend on `datetime.now()` or `date.today()` without freezing time
- "Passes locally but fails in CI" — classic flaky symptom
- The CI pipeline has `retry` or `rerun` built in as a workaround for known flakiness

**Phase to address:**
VALIDATE-01 (data validation CI). Implement deterministic checks FIRST, then add external-dependent checks as non-gating advisory jobs.

---

### Pitfall 6: HYPOTHESIS_HELL — Non-Deterministic Failures from Property-Based Tests

**What goes wrong:**
Property-based tests with Hypothesis generate random input. A test passes 99 times and fails on the 100th with a bizarre counterexample that's hard to reproduce. The failure occurs on a CI runner but not locally. Developers disable or ignore the property tests because "they're just random — probably not a real bug." The real bug (e.g., `enrich_one()` crashes on chips with empty string vendor) stays hidden.

**Why it happens:**
- Hypothesis uses a random seed — if the CI runner and local machine have different seeds, they find different counterexamples
- The `@given(chip_dict())` strategy generates wide variety including edge cases (empty strings, None values, Unicode) that the original code never handled
- The current property tests (`tests/property/test_enrich_one.py`) are weak — `test_no_exceptions` passes as long as no exception is raised, even if the result is garbage
- Hypothesis's database (`.hypothesis/examples`) caches failing examples — if you delete it, you lose reproducibility
- `max_examples=100` is too low for meaningful coverage of the 10+ field combinations

**How to avoid:**
1. **Seed the Hypothesis RNG** — use `@settings(derandomize=True)` for CI runs to get deterministic behavior, or `@settings(max_examples=1000)` for local runs
2. **Commit the Hypothesis database** — `.hypothesis/examples` should be checked into git (small, binary files) so CI and local share failing examples
3. **Test invariance properties, not just "no crash"** — the current `test_no_exceptions` should be replaced with `result["year"] is None or 2003 <= result["year"] <= 2030`
4. **Reproduce from `hypothesis print-statistics`** — add `--hypothesis-show-statistics` to CI to see what edge cases ARE being generated
5. **Explicitly test known edge cases** — don't rely SOLELY on Hypothesis for edge coverage. Add explicit tests for: empty strings, None values, non-ASCII, zero-length arrays, negative years
6. **`@example(...)` decorator for specific known edge cases** — ensures those are ALWAYS tested, not just found randomly

**Warning signs:**
- `test_no_exceptions` in property tests (covers nothing meaningful)
- `@settings(max_examples=50)` or lower (too few iterations)
- No explicit examples alongside `@given`
- `.hypothesis/` in `.gitignore`

**Phase to address:**
TEST-01 (property-based testing). Commit .hypothesis/examples. Replace weak property tests with invariant-based ones.

---

### Pitfall 7: REDIS_DOWNTIME — Rate Limiter Becomes Single Point of Failure

**What goes wrong:**
The Redis-backed rate limiter (RATELIMIT-01) is deployed. When Redis goes down (network blip, restart, OOM), ALL API requests fail with 500 errors because the rate limiter can't check whether to allow the request. The in-memory fallback rate limiter that worked in v2.0 is gone. A Redis restart causes 30 seconds of 503s for every request.

**Why it happens:**
- The rate limiter is in the request path — every API request hits Redis synchronously (or async) to check/update the rate limit counter
- `redis-py` default connection timeout is infinite — a hung Redis connection blocks the request indefinitely
- The connection pool in `redis-py` can leak connections if not properly released, exhausting file descriptors
- Developers assume Redis is "always available" and don't implement a circuit breaker or fallback
- Wrong TTL: using `EXPIRE` on the rate limit key with a short TTL (e.g., 1 second) means the rate limit state resets after a brief Redis blip — legit users get rate-limited because their counter disappeared

**How to avoid:**
1. **Implement a local fallback** — if Redis is unreachable, fall back to the existing in-memory `_rate_limit_buckets` (with a warning log). This is CRITICAL — the in-memory limiter already exists and works.
2. **Use `redis-py` with `socket_connect_timeout=2` and `socket_timeout=2`** — never let a Redis call block indefinitely
3. **Connection pooling** — `redis.from_url(url, max_connections=10)` — and use it as a context manager
4. **Health check integration** — the `/health` endpoint should check Redis connectivity and return 503 if Redis is down (but the RATE LIMITER should still fall back to local)
5. **Rate limit key design** — use `WINDOW:SECONDS:CLIENT_IP` with TTL = window * 2. Not too short, not infinite.
6. **Test Redis failure mode** — actually stop Redis, verify API still works (with in-memory fallback), verify log warning is emitted

**Warning signs:**
- `redis.Redis()` created without timeout parameters
- No `try/except redis.ConnectionError` around rate limit checks
- Rate limiter has no local fallback
- `/health` endpoint doesn't check Redis
- Connection pool not configured (defaults to unbounded)

**Phase to address:**
RATELIMIT-01 (Redis rate limiter). The in-memory fallback must be implemented in THE SAME PR — not added later.

---

### Pitfall 8: SHARED_STATE_CORRUPTION — Multi-Worker Processes Step on Each Other

**What goes wrong:**
The application deploys with `gunicorn -w 4` (4 workers). Worker 1 and Worker 2 simultaneously receive requests. Both call `get_chips()` — the cache check `if app.state._chips is None` passes for both (the cache was empty or expired). Both reload ALL 1746 chips from disk. Worker 1 finishes first, sets `_chips`. Worker 2 finishes, OVERWRITES `_chips` with the same data — no corruption here, just wasted work. BUT: the search index rebuild (`_build_search_index`) takes ~500ms. If Worker 1 is serving a search request while Worker 2 rebuilds the index, the search index pointer could be in an inconsistent state.

Worse: the rate limiter (`_rate_limit_buckets` — in-memory dict) is per-process, NOT shared. With 4 workers, each has its own rate limit counter. A user can make 4x the allowed requests by distributing across workers.

**Why it happens:**
- Gunicorn with `--worker-class uvicorn.workers.UvicornWorker` forks workers — each has its OWN memory space
- The rate limiter dict `_rate_limit_buckets` is in-memory only — workers don't share state
- The `app.state._chips` cache is duplicated across all workers — memory waste but not corrupt
- Scheduled tasks (like Wikidata refresh) run in ALL workers simultaneously, not just one

**How to avoid:**
1. **Rate limiter MUST use external storage** — this is why REDIS-01 is a prerequisite for multi-worker. Without Redis, rate limiting doesn't work with >1 worker.
2. **File-based cache for chip data** — instead of in-memory `app.state._chips`, use a shared file with a lock. Or accept the per-worker duplicate (10MB per worker is negligible).
3. **Scheduled tasks in leader worker only** — use gunicorn's `--preload` with a flag file, or use a separate scheduler process (not the web workers)
4. **`gunicorn` with `--worker-tmp-dir /dev/shm`** for faster temp file operations
5. **`uvicorn` with `--workers` uses `multiprocessing`** — each worker is a separate process. Use `--reload` only in development.
6. **Test with `curl` in parallel** — `wrk -t 4 -c 4 http://localhost:8000/v1/chips` — verify rate limit behavior with multiple workers

**Warning signs:**
- In-memory dicts used for state that should be shared across workers
- `app.state.*` that is written, not just read, in request handlers
- Rate limiter works in dev (single worker) but breaks in production (multiple workers)
- No external cache/DB for cross-worker state

**Phase to address:**
This applies across RATELIMIT-01 (Redis) AND the multi-worker deployment config. Document that Redis is REQUIRED before running with >1 worker.

---

### Pitfall 9: OTELE_OVERHEAD — OpenTelemetry Instrumentation Slows the API

**What goes wrong:**
OpenTelemetry instrumentation is added to every endpoint, every DB query, every enrichment call. Each span creation, attribute setting, and export adds latency. The default OTel Python SDK uses `BatchSpanProcessor` which exports spans every 5 seconds — but during a traffic spike, the span buffer fills up and spans are dropped. The developer sees "missing traces" and increases the buffer size, which increases memory pressure. The API response time degrades by 30-50% under load.

**Why it happens:**
- Python OpenTelemetry instrumentation is relatively expensive compared to Go/Java — each span involves multiple dict allocations, timestamps, attribute serialization
- The auto-instrumentation patching (monkey-patching libraries like `requests`, `aiohttp`) adds overhead to EVERY call, not just the traced ones
- `OTEL_TRACES_SAMPLER=always_on` samples EVERY request — for an API serving 1000 req/s, that's 1000 spans/s per service
- Span attributes like `http.request.body` are captured by default — large request bodies serialize into span attributes, wasting memory
- The Prometheus metrics endpoint (`/metrics`) is scraped every 15 seconds by default — each scrape involves computing and serializing all metrics

**How to avoid:**
1. **Use parent-based sampling** — sample traces at the entry point (e.g., 10% of requests) and let child spans inherit. Use `OTEL_TRACES_SAMPLER=traceidratio` with `OTEL_TRACES_SAMPLER_ARG=0.1`
2. **Exclude health check endpoints** — the `/health` endpoint gets scraped every 5 seconds. Don't trace it. Use `OTEL_PYTHON_FASTAPI_EXCLUDED_URLS=health,metrics`
3. **Use `BatchSpanProcessor` with conservative settings** — `max_export_batch_size=512`, `max_queue_size=2048`, `schedule_delay_millis=5000`. Monitor for dropped spans.
4. **Profile before and after** — run `wrk -t 4 -c 20 http://localhost:8000/v1/chips` for 60 seconds, measure p50/p95/p99 latency BEFORE and AFTER OTel is added. Accept <5% degradation.
5. **Use `OTEL_PYTHON_LOG_CORRELATION` for JSON log → trace correlation** — avoids needing to trace EVERYTHING. Logs can link to traces without the overhead.
6. **Selective instrumentation** — don't auto-instrument everything. Manually instrument only the critical paths (enrichment, DB queries, external API calls).

**Warning signs:**
- `opentelemetry-instrument` with no `--excluded_urls` configuration
- `OTEL_TRACES_SAMPLER=always_on` in production
- No before/after benchmark for OTel instrumentation
- Auto-instrumentation for EVERY library instead of selective manual instrumentation
- Large span attributes (body payload, full URLs with query params)

**Phase to address:**
OBSERVE-01 (OpenTelemetry). Must include before/after performance benchmarks. Sampling must be configured, not default.

---

### Pitfall 10: SPARQL_UNRELIABLE — Wikidata API Changes or Rate Limits Break Automation

**What goes wrong:**
The Wikidata SPARQL endpoint is used to auto-generate vendor knowledge maps (process nodes, GPU models, architecture details). The SPARQL query runs on schedule, fetches data, and updates the vendor maps. One day, the endpoint starts returning empty results — Wikidata changed a property ID (`P1234` → `P5678`), or the SPARQL endpoint rate-limits the request. The automation updates the vendor maps with: "no data" = empty maps. The enrichment pipeline then strips out all GPU/process data for that vendor because the map says nothing. 500 chip records lose their GPU field silently.

**Why it happens:**
- Wikidata property IDs change (e.g., when a property is deprecated and replaced). "Process node" was P1234 last year, now it's P5678.
- The Wikidata SPARQL endpoint has aggressive rate limiting (default: ~5 queries per second per IP, no user-agent → much lower)
- SPARQL query timeout is 60 seconds — complex queries on the full dataset timeout silently, returning partial results
- The endpoint returns HTTP 200 even for queries that hit the timeout — the JSON response has `{"status": "error"}` inside the body, not an HTTP error code
- The Wikidata schema is NOT versioned — a property's expected type can change (e.g., from string to URL) without notice

**How to avoid:**
1. **Validate SPARQL results before writing** — check that the response contains expected fields and >0 rows. If the result is empty or looks wrong, LOG A WARNING and DO NOT UPDATE the maps. Keep the previous data.
2. **Version-pin SPARQL queries** — each query should include a comment with the Wikidata property P-IDs used. When a property changes, grep for the old P-ID.
3. **Retry with exponential backoff** — use `tenacity` or similar with `retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=60))`
4. **Set explicit user-agent** — `User-Agent: soc-db/2.1 (+https://github.com/vitkuz573/soc-db)` — Wikidata blocks requests without identifiable user-agent
5. **Run in dry-run mode first** — the automation should have a `--dry-run` flag that shows what would change without writing
6. **Monitor Wikidata endpoint health** — a weekly CI check that runs the SPARQL query and verifies expected results
7. **Use `format=json` and check `boolean` field** — the SPARQL endpoint returns `{"boolean": false}` for queries that time out. CHECK THIS before trusting results.

**Warning signs:**
- SPARQL queries without property P-IDs in comments
- No `User-Agent` header on SPARQL requests
- Automation that blindly overwrites vendor maps without validation
- No retry logic for SPARQL queries
- `query.wikidata.org` calls with no timeout parameter

**Phase to address:**
WIKIDATA-01 (SPARQL automation). Must include result validation and dry-run mode. NEVER auto-publish SPARQL results without human review.

---

### Pitfall 11: IMPORT_ORDER — Refactoring common.py Creates Circular Imports

**What goes wrong:**
When `common.py` is split into modules (`enrichment/year.py`, `enrichment/vendor_knowledge.py`, `enrichment/process.py`, etc.), cross-references between modules create circular imports. `year.py` imports from `vendor_knowledge.py` to check chip vendor. `vendor_knowledge.py` imports from `process.py` for process node inference. `process.py` imports from `year.py` for year-based process defaults. Python raises `ImportError` at runtime because the module graph has a cycle.

**Why it happens:**
- The original `common.py` is a flat 1561-line file — every function references every other function. There were no module boundaries, so there ARE no clean module boundaries to extract.
- `enrich_one()` interleaves year inference, vendor knowledge lookup, GPU mapping, process node inference, memory type inference, etc. — in non-obvious order
- Type annotations (Pydantic models, custom types) used across modules create import-time cycles
- Existing code does `from soc_db.common import VENDOR_KNOWLEDGE` — refactoring must preserve this import path or EVERY call site breaks

**How to avoid:**
1. **Start from CALLERS, not from common.py** — before splitting `common.py`, update all callers to import from the new module structure. The last step is making `common.py` a re-export shim.
2. **Use `TYPE_CHECKING` for type-only imports** — `from __future__ import annotations` + `TYPE_CHECKING` guards prevent import-time cycles
3. **Create an `enrichment/__init__.py` that re-exports all public API** — callers import from `soc_db.enrichment` not from individual modules
4. **Add `python -c "import soc_db.common"` to CI** — if the refactored `common.py` still imports cleanly, the re-export shim works
5. **Use `importlib.import_module()` sparingly** — it's a band-aid, not a solution. Fix the architecture instead.

**Warning signs:**
- Any `from X import Y` where X is being split — mark as a potential cycle point
- Modules that import from each other in both directions
- `__init__.py` files that import FROM submodules instead of just re-exporting
- `ImportError: cannot import name 'X' from partially initialized module 'Y'`

**Phase to address:**
REFAC-01 (refactoring). Add `TYPE_CHECKING` guards proactively. Keep `common.py` as a shim with `from enrichment import *` for backward compat during migration.

---

## Technical Debt Patterns

### Shortcuts That Seem Reasonable but Create Long-term Problems

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Keep `common.py` as import shim after refactoring | Zero import changes in callers | Dead code accumulates; nobody removes unused imports from `common.py` | Acceptable for 1 release cycle; document removal in next milestone |
| SQLite migration with `SELECT *` | Quick to write | Column order dependency; schema changes silently break callers | Never — always use explicit column lists |
| Ship `data/` directory in PyPI wheel | Users get data without download | Package size balloons; data updates require new release | Never — data should be downloaded at runtime or via a separate data package |
| `asyncio.to_thread()` everywhere | Quick async migration | Thread pool exhaustion; no cancellation support | Acceptable for I/O-bound operations only (file reads). NOT for CPU-bound work |
| Auto-publish SPARQL results | Fully automated | Silent data corruption if Wikidata schema changes | Never — always require human review before publishing SPARQL results |
| `try/except Exception` around Redis calls | Prevents crashes from Redis downtime | Silently swallows real errors; operator doesn't know Redis is down | Acceptable only with proper logging and monitoring alert |
| 100% sampling in OpenTelemetry | Complete trace data | 30-50% performance degradation; high memory usage | Never for production. Use 10% sampling max |
| Hypothesis without seed or DB | Simplifies CI setup | Non-reproducible failures; flaky CI | Never — always commit `.hypothesis/examples` and use `derandomize=True` in CI |
| One big `pyproject.toml` instead of constraints files | Single-file management | Version conflicts when adding OTel + Prometheus + Redis deps | Acceptable for <10 dependencies. Beyond that, use `constraints.txt` |

### Shortcuts to Never Take

| Shortcut | Why Never |
|----------|-----------|
| Skipping snapshot test before refactoring year inference | Without a before/after comparison, you CANNOT detect regression in 1746 chips |
| Migrating SQLite schema without API integration tests | You WILL change the response shape subtly and not notice |
| Publishing to PyPI without build inspection | You WILL accidentally include a secret at some point |
| Deploying multi-worker without Redis rate limiter | The in-memory rate limiter doesn't work with >1 worker — trivial to bypass |
| Auto-updating vendor maps from Wikidata without validation | One schema change on Wikidata side silently corrupts your data |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| **Redis** | Creating a new `redis.Redis()` connection for every request | Use `redis.from_url()` with `max_connections` pool. Reuse the client as a singleton. |
| **Redis** | No timeout on connection | `socket_connect_timeout=2, socket_timeout=2, retry_on_timeout=True` |
| **Wikidata SPARQL** | Not setting User-Agent header | `headers={"User-Agent": "soc-db/2.1 (+https://github.com/vitkuz573/soc-db)"}` |
| **Wikidata SPARQL** | Not checking for timeout/error in response body | Parse `{"boolean": false}` / `{"status": "error"}` IN ADDITION to HTTP status code |
| **Wikidata SPARQL** | Using default query timeout (60s) | Set explicit timeout via `REQUEST_TIMEOUT` env var or query parameter |
| **PyPI** | Using API token auth directly in CI | Use trusted publishing (OIDC) — PyPI supports it natively with GitHub Actions |
| **GitHub Pages** | Building docs/ directory dynamically during deployment | CI must build docs/ and commit it; static site MUST remain unchanged by Python build |
| **OpenTelemetry** | Adding auto-instrumentation for ALL dependencies | Selectively instrument: FastAPI, aiosqlite, httpx. NOT every transitive dep. |
| **OpenTelemetry** | Not setting `OTEL_SERVICE_NAME` | Defaults to "unknown_service" — traces become unidentifiable |
| **FastAPI + Gunicorn** | Using `--reload` in production | `--reload` watches for file changes and is DANGEROUS in production |
| **FastAPI + Gunicorn** | Not setting `--forwarded-allow-ips` behind nginx | Client IP is always 127.0.0.1 — rate limiting by IP doesn't work |
| **Hypothesis** | Not using `@example()` for known edge cases | Hypothetical random generation may NEVER hit your known bug case |
| **SQLite** | Using `sqlite3` without WAL mode | Concurrent reads block each other; WAL mode allows concurrent reads |
| **SQLite** | Not enabling FTS5 before migration | Full-text search requires FTS5 virtual table — add DURING migration, not after |

---

## Performance Traps

| Trap | Symptoms | Prevention | Breaks At |
|------|----------|------------|-----------|
| **Blocking enrichment in async route** | All requests slow down when one enrichment runs | Move enrichment to background task or ProcessPoolExecutor | 10 concurrent requests |
| **No connection pooling for Redis** | Latency spikes; TCP connection errors | `redis.from_url()` with pool | 50 req/s |
| **Loading ALL chips on every cache miss** | Periodic latency spikes (cache TTL expires) | Use SQLite queries instead of loading all records | Cache TTL expiry + 10 req/s |
| **Rebuilding search index on every cache miss** | CPU spike every cache TTL | Use SQLite FTS5 — query, don't rebuild index | Cache TTL expiry + 50 req/s |
| **OTel BatchSpanProcessor with default settings** | Memory grows under load; spans dropped | Tune `max_queue_size` and `schedule_delay` | 500 spans/s |
| **SPARQL query on every request** | API latency >5s, Wikidata rate limits | Cache SPARQL results in SQLite, refresh on schedule | 1 req/s |
| **JSON serialization of 1746 chips** | Response time >500ms | Support pagination (already exists), use `orjson` | 100 chips unbatched |
| **Gunicorn with too many workers** | Memory exhaustion, context switching overhead | `2 * CPU_CORES + 1` for IO-bound; `CPU_CORES` for CPU-bound | 16+ workers on 4-core machine |
| **Not using WAL mode for SQLite** | Writer blocks all readers | Enable WAL mode at connection time | 2+ concurrent writes |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| **PyPI token in CI as plain secret** | Anyone with repo read access can publish malicious packages | Use OIDC trusted publishing instead of token-based auth |
| **Bundling API keys in built wheel** | Users download your keys from PyPI | Set `MANIFEST.in` to exclude `.env`, `config/`, `credentials*` |
| **Running API without authentication in production** | Anyone can query/modify chip data | Make `api_key` REQUIRED in production (fail if not set) |
| **Otel exporter without auth** | Anyone can read your traces (sensitive data) | Use OTel exporter with TLS + auth headers |
| **Redis without password in cloud deployment** | Data exposure, cache poisoning | `requirepass` in Redis config; Redis 6+ ACLs |
| **SPARQL query injection** | Malformed SPARQL queries expose Wikidata data | Never interpolate user input into SPARQL queries |
| **CORS wide open (`allow_origins: ["*"]`)** | Any website can make API calls from user's browser | Restrict to known origins or use dynamic origin validation |
| **World-readable cache dir (`/tmp/soc-db-cache/`)** | Sensitive cached data exposed on multi-tenant systems | Use `SOC_DB_CACHE_DIR` env var; default to user-local dir |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| **Rate limiting without clear error message** | User gets 429 with no info on when retry | Return `Retry-After` header AND `retry_after` in JSON body |
| **Breaking CLI output format** | Scripts parsing CLI output break | Add `--format json` for machine-readable output; warn before changing default format |
| **Removing fields from API response** | GitHub Pages UI shows blank fields | Add fields to API response as `null` (absent) instead of removing them; deprecate with `sunset` header |
| **Requiring Redis for basic local dev** | New contributors can't run the app | Make Redis optional — fall back to in-memory rate limiter; print warning |
| **SPARQL automation changes data without notice** | Operator finds chips with missing GPU fields | Send notification (email/chat) when automation changes data; require manual approval for auto-changes |
| **OTel SDK version mismatch with app deps** | Import errors on `opentelemetry-api` vs `opentelemetry-sdk` | Pin OTel SDK versions in `constraints.txt`; test upgrade in CI |

---

## "Looks Done But Isn't" Checklist

- [ ] **REFAC-01 (common.py refactoring):** Often missing: a snapshot test of all 1746 chips before starting. Verify that `enrich_one()` produces IDENTICAL output for every chip before and after refactoring.
- [ ] **DB-01 (SQLite migration):** Often missing: checking that NULL/absent-field behavior matches JSON's missing-key behavior. Add a test that migrates, then queries every field and verifies exact same behavior as JSON path.
- [ ] **RELEASE-01 (PyPI publishing):** Often missing: `python -m build` and `twine check dist/*` in CI before upload. Add a dry-run publish step.
- [ ] **ASYNC-01 (async data layer):** Often missing: checking that `time.sleep` (not `asyncio.sleep`) is NOT present anywhere in async code. Add a ruff rule `ASYNC100` to forbid `time.sleep()`.
- [ ] **VALIDATE-01 (validation CI):** Often missing: distinguishing between flaky tests (external deps) and deterministic tests. Tag flaky tests explicitly with `@pytest.mark.flaky`.
- [ ] **TEST-01 (property-based testing):** Often missing: `@example()` decorators for known edge cases. Hypothesis can miss critical cases if the strategy doesn't cover them.
- [ ] **RATELIMIT-01 (Redis rate limiter):** Often missing: fallback mode when Redis is unavailable. The rate limiter should fail OPEN (allow requests) not fail CLOSED (block all).
- [ ] **Multi-worker deployment:** Often missing: verifying rate limiting works with `wrk -t 4 -c 10 http://...`. Each worker has its own rate limit counter — without Redis, multi-worker = no rate limiting.
- [ ] **OBSERVE-01 (OpenTelemetry):** Often missing: before/after performance benchmark. OTel can add 30-50% overhead if not configured correctly. Measure it.
- [ ] **WIKIDATA-01 (SPARQL automation):** Often missing: validation of SPARQL results before overwriting vendor maps. A bad Wikidata response can silently delete all your GPU data.
- [ ] **GitHub Pages deployment:** Often missing: verifying that `docs/` isn't regenerated by the build process. The static site files (index.html, 404.html, swagger.html) must survive unchanged.
- [ ] **`pyproject.toml` after adding all deps:** Often missing: version conflicts between `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`, `redis`, and existing deps. Pin versions and test `pip install -e ".[dev]"` in CI.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Year inference regression | MEDIUM | Revert refactoring. Restore snapshot test. Re-extract with priority order documented. |
| SQLite schema drift (API responses changed) | MEDIUM | Add Pydantic response model. Map DB columns → API fields. Do NOT change API response. |
| Secrets leaked to PyPI | HIGH | Revoke all tokens. Yank affected PyPI release. Rotate ALL credentials, not just the leaked one. |
| Event loop blocked by sync code | MEDIUM | Add `run_in_executor()` for CPU-bound work. Use `ProcessPoolExecutor` for enrichment. |
| Flaky CI blocking PRs | LOW | Remove flaky tests from gating. Make them scheduled-only. Fix root cause without pressure. |
| Non-deterministic Hypothesis failure | LOW | `hypothesis --seed <last-good-seed>` to reproduce. Then fix the bug. Commit `.hypothesis/examples`. |
| Redis outage = API outage | HIGH | Add in-memory fallback rate limiter. NOW. Redis should NEVER be a hard dependency. |
| Multi-worker rate limit bypass | HIGH | Add Redis rate limiter before enabling multi-worker. Without Redis, multi-worker has no rate limiting. |
| OTel performance degradation | MEDIUM | Reduce sampling to 10%. Add before/after benchmarks. Exclude health endpoints. |
| Wikidata schema change corrupts data | HIGH | Restore vendor maps from git history. Add validation BEFORE auto-update. |
| Circular import after refactoring | LOW | Add `TYPE_CHECKING` guards. Restructure module boundaries. Keep `common.py` as shim. |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Year inference regression (Pitfall 1) | REFAC-01 | Snapshot test before/after; all 1746 chips have identical year |
| SQLite schema drift (Pitfall 2) | DB-01 | API integration test with frozen responses; field-by-field diff |
| Secrets leak to PyPI (Pitfall 3) | RELEASE-01 | `twine check` + build inspection in CI; OIDC auth |
| Event loop blocking (Pitfall 4) | ASYNC-01 | `wrk` benchmark shows no latency increase with concurrency |
| Flaky CI (Pitfall 5) | VALIDATE-01 | Separate gating (deterministic) from monitoring (flaky) tests |
| Hypothesis non-determinism (Pitfall 6) | TEST-01 | `derandomize=True` in CI; `.hypothesis/examples` committed |
| Redis downtime breaks API (Pitfall 7) | RATELIMIT-01 | Stop Redis; verify API still works with in-memory fallback |
| Multi-worker state corruption (Pitfall 8) | RATELIMIT-01 + Deploy | Rate limiter works identically with 1 and 4 workers |
| OTel performance overhead (Pitfall 9) | OBSERVE-01 | Before/after latency benchmark; <5% degradation |
| Wikidata data corruption (Pitfall 10) | WIKIDATA-01 | Dry-run mode; result validation; automatic rollback on empty results |
| Circular imports (Pitfall 11) | REFAC-01 | `python -c "import soc_db"` passes; all tests import cleanly |

---

## Phase Dependencies

```
REFAC-01 (common.py refactoring) ── MUST pass before DB-01 (schema snapshot)
DB-01 (SQLite migration) ──────── MUST pass before ASYNC-01 (async data layer uses SQLite)
ASYNC-01 (async data layer) ───── MUST pass before OBSERVE-01 (need async spans)
RATELIMIT-01 (Redis rate limiter) ─ MUST pass before multi-worker deployment
RELEASE-01 (PyPI publishing) ──── Independent but must come last (version bump)
VALIDATE-01 ───────────────────── Independent, can run in parallel
TEST-01 ───────────────────────── Independent, can run in parallel, but feeds REFAC-01
WIKIDATA-01 ──────────────────── Independent, but uses SQLite if migrated
```

**IMPORTANT for roadmap ordering:**
1. REFAC-01 FIRST (most dangerous, affects all data)
2. DB-01 + ASYNC-01 NEXT (core infrastructure change)
3. RATELIMIT-01 BEFORE multi-worker (safety requirement)
4. TEST-01 early but parallel (feeds quality for REFAC-01)
5. RELEASE-01 LAST (must have all features before publishing)

---

## Sources

- **Python asyncio docs** — `docs.python.org/3/library/asyncio-dev.html` (event loop blocking, sync/async mixing)
- **Python asyncio synchronization** — `docs.python.org/3/library/asyncio-sync.html` (thread safety of async primitives)
- **Hypothesis docs** — `hypothesis.readthedocs.io` (reproducibility, database, @example patterns)
- **Wikidata SPARQL documentation** — `wikidata.org/wiki/Wikidata:SPARQL_query_service` (format, timeout, rate limits)
- **OpenTelemetry Python docs** — `opentelemetry-python.readthedocs.io` (sampling, performance considerations)
- **redis-py docs** — `redis-py.readthedocs.io` (connection pooling, timeouts, error handling)
- **Gunicorn settings** — `docs.gunicorn.org` (worker model, shared state considerations)
- **PyPA packaging guides** — `packaging.python.org` (PyPI publishing, OIDC trust publishing)
- **SOC-DB codebase analysis** — CONCERNS.md, common.py (1561 lines), api/main.py (477 lines), test structure

---
*Pitfalls research for: soc-db v2.1 Enterprise Hardening*
*Researched: 2026-07-19*
