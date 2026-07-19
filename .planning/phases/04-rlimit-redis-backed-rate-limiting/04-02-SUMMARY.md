---
phase: 04-rlimit-redis-backed-rate-limiting
plan: 02
subsystem: API Integration
tags: [fastapi, middleware, rate-limiting, health-endpoint, docker-compose]
requires: [04-01]
provides: [Rate-limit headers on all responses, Redis status in health endpoint, graceful failure on limiter error]
affects: [api/main.py, src/soc_db/models.py, tests/integration/test_api.py, docker-compose.yml]
tech-stack:
  added: []
  patterns: [app.state-based rate limiter injection, lazy init for test isolation, try/except around limiter.check]
key-files:
  created: []
  modified: [src/soc_db/models.py, api/main.py, tests/integration/test_api.py, docker-compose.yml]
decisions:
  - "Rate limit check runs BEFORE call_next to avoid processing blocked requests"
  - "Headers added AFTER call_next for allowed requests (wraps real response including X-Request-ID)"
  - "Lazy InMemoryRateLimiter init for test scenarios without lifespan"
  - "try/except around limiter.check() prevents any Redis/limiter exception from causing 5xx"
  - "docker-compose depends_on does not create hard Redis dependency — app falls back to in-memory"
metrics:
  duration: ~15 min
  completed_date: "2026-07-19"
status: complete
---

# Phase 4 Plan 2: API Integration Summary

One-liner: Integrated rate limiter library into FastAPI — replaced inline rate limit with app.state-based RateLimiter, added standard rate limit headers, updated health/metrics endpoints, and added Redis service to docker-compose.

## What Was Built

### `src/soc_db/models.py` — HealthResponse Update

- Added `redis_connected: bool = False` field (backward-compatible — defaults to `False`)

### `api/main.py` — Major Refactoring

- **Removed** module-level `_rate_limit_buckets` and `_rate_limit_lock` (and unused `defaultdict` import)
- **Lifespan startup:** Creates rate limiter via `create_rate_limiter(redis_url=settings.redis_url, ...)` and stores on `app.state.rate_limiter`
- **Lifespan shutdown:** Closes rate limiter gracefully (if has `close()` method)
- **Rate limit middleware** (replaced inline implementation):
  - Gets limiter from `app.state.rate_limiter` (lazy `InMemoryRateLimiter` fallback for tests)
  - `limiter.check(client_ip)` returns `(allowed, limit, remaining, reset_time)`
  - If blocked: returns `429` with `X-RateLimit-*` headers + JSON body with `retry_after`
  - If allowed: adds `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` headers to response
  - `try/except` around `limiter.check()` prevents any exception from causing 5xx
- **Health endpoint:** Reads `limiter.is_redis_connected` and includes it in response
- **Metrics endpoint:** Reads `limiter.active_clients` instead of `len(_rate_limit_buckets)`

### `tests/integration/test_api.py` — Updated Tests

- **`init_app_state` fixture:** Added `app.state.rate_limiter = InMemoryRateLimiter(limit=100, window=60)`
- **`test_rate_limit_jail`:** Replaced `_rate_limit_buckets` access with `app.state.rate_limiter` swap
- **`test_health`:** Added `redis_connected` field assertion
- **New test `test_rate_limit_headers_present`:** Verifies all 3 headers on every response
- **New test `test_rate_limit_headers_decrement`:** Verifies remaining decreases between requests
- **New test `test_rate_limit_headers_on_429`:** Verifies headers + JSON body on rate-limit exceeded
- **New test `test_health_redis_connected_field`:** Verifies `redis_connected` is boolean in health
- **New test `test_rate_limit_graceful_fallback`:** Verifies no 5xx even with broken limiter

### `docker-compose.yml` — Redis Service

- Added `redis:7-alpine` service with healthcheck
- Added `SOC_DB_REDIS_URL=redis://redis:6379/0` environment variable on soc-db service
- Graceful `depends_on` — app falls back to in-memory if Redis unreachable

### Test Results

**558 passed, 1 skipped** — all existing tests continue to pass with zero modifications to test logic. Only import/access patterns updated.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

None — all security-relevant surfaces covered in threat model.

## Self-Check: PASSED

- `python -c "from api.main import app"` succeeds
- `HealthResponse(redis_connected=False)` model_dump includes the field
- Rate limit headers verified via integration tests
- Health endpoint returns `redis_connected` field
- All 558 tests pass (1 skipped)
