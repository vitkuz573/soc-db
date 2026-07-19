---
phase: 04-rlimit-redis-backed-rate-limiting
plan: 01
subsystem: Rate Limiting
tags: [redis, rate-limiting, core-library, in-memory-fallback]
requires: []
provides: [RateLimiter protocol, InMemoryRateLimiter, RedisRateLimiter, create_rate_limiter factory]
affects: [api/main.py, src/soc_db/config.py, pyproject.toml]
tech-stack:
  added: [redis[hiredis]>=5.0,<8.0]
  patterns: [Protocol-based abstraction, factory with fallback, lazy Redis import]
key-files:
  created: [src/soc_db/rate_limit.py, tests/unit/test_rate_limit.py]
  modified: [pyproject.toml, src/soc_db/config.py]
decisions:
  - "Pin redis<8.0 to avoid RESP3 protocol breakage with hiredis C parser"
  - "In-memory fallback ships in same PR as Redis (transparent degradation)"
  - "socket_connect_timeout=2 prevents hang on unreachable Redis"
  - "Lazy 'import redis.asyncio' in RedisRateLimiter so redis-py is optional at module import time"
  - "InMemoryRateLimiter uses asyncio.Lock for concurrent-safety (single-worker dev)"
  - "Redis sliding-window uses two pipelines: prune+count (atomic) then ZADD+EXPIRE"
  - "EXPIRE TTL=2×window for safety margin even if key is never checked again"
metrics:
  duration: ~12 min
  completed_date: "2026-07-19"
status: complete
---

# Phase 4 Plan 1: Core Rate Limiter Library Summary

One-liner: Rate limiter library with dual implementation (Redis + in-memory) under a shared `RateLimiter` protocol, with a factory that provides transparent in-memory fallback when Redis is unreachable.

## What Was Built

### `src/soc_db/rate_limit.py` — Core Rate Limiter Module

- **`RateLimiter` Protocol** (`@runtime_checkable`): Defines `check(key) -> tuple[bool, int, int, float]`, `is_redis_connected`, and `active_clients`. Both implementations satisfy this protocol.

- **`InMemoryRateLimiter`**: Refactored sliding-window from the previous inline pattern in `api/main.py`. Uses `defaultdict[list[float]]` with `asyncio.Lock`. Prunes expired entries on each check. Returns `(allowed, limit, remaining, reset_timestamp)`.

- **`RedisRateLimiter`**: Sliding window via Redis sorted sets:
  - Lazy connect with `socket_connect_timeout=2`
  - Pipeline 1: `ZREMRANGEBYSCORE` + `ZCARD` (prune + count)
  - Pipeline 2: `ZADD` + `EXPIRE` (record + TTL)
  - Key format: `ratelimit:{client_id}`
  - EXPIRE TTL = 2×window for safety
  - On any Redis exception: force reconnect, raise `ConnectionError`

- **`create_rate_limiter()` Factory**:
  - `redis_url=None` or `""` → returns `InMemoryRateLimiter`
  - `redis_url` set but unreachable → logs warning, returns `InMemoryRateLimiter`
  - `redis_url` set and reachable → returns `RedisRateLimiter`
  - **Never raises or returns a broken limiter**

### Configuration

- `pyproject.toml`: Added `"redis[hiredis]>=5.0,<8.0"` to `dependencies`
- `src/soc_db/config.py`: Added `redis_url: str | None = None` (env: `SOC_DB_REDIS_URL`)

### Dependency Versions

- redis 7.4.1 installed (within 5.0,<8.0 pin)
- hiredis 3.4.0 installed (C parser for performance)

### Unit Tests (`tests/unit/test_rate_limit.py`)

| Test Class | Tests | Description |
|---|---|---|
| `TestInMemoryRateLimiter` | 7 | allows, blocks, window slides, multi-key independence, remaining decrement, is_redis_connected, active_clients |
| `TestRedisRateLimiter` | 5 | allowed (mocked pipeline), blocked, connection error, is_redis_connected lifecycle, reconnect on failure |
| `TestCreateRateLimiter` | 4 | None URL, empty URL, invalid URL fallback, valid URL returns Redis |

All **16 tests pass** with no warnings.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

None — all security-relevant surfaces covered in threat model.

## Self-Check: PASSED

- `src/soc_db/rate_limit.py` exists and imports cleanly
- `tests/unit/test_rate_limit.py` exists with 16 tests, all passing
- redis installed successfully: 7.4.1 with hiredis 3.4.0
- Config field `redis_url` accessible at `settings.redis_url`
