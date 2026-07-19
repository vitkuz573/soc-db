---
phase: 03-async-async-data-layer
plan: 01
subsystem: async-db-foundation
tags: ["aiosqlite", "connection-pool", "async-queries", "ttl-cache"]
requires: []
provides: ["AsyncConnectionPool", "get_all_async", "get_by_id_async", "search_async", "get_vendors_async", "get_stats_async"]
affects: ["api/main.py", "src/soc_db/db/__init__.py"]
tech-stack:
  added: ["aiosqlite>=0.20"]
  patterns: ["async connection pool with Semaphore", "async query functions with dual-read fallback"]
key-files:
  created: ["tests/unit/test_queries_async.py"]
  modified: ["pyproject.toml", "requirements.txt", "src/soc_db/config.py", "src/soc_db/db/connection.py", "src/soc_db/db/queries.py", "src/soc_db/db/__init__.py"]
  verified: 6
decisions:
  - "Pool size default 5, configurable via SOC_DB_ASYNC_POOL_SIZE env var"
  - "Async functions use _ensure_async_conn helper for optional connection parameter"
  - "Connection lifecycle managed by caller, not by query functions"
  - "aiosqlite 0.22.1 installed (satisfies >=0.20 constraint)"
  - "Async/sync parity verified: same results for same input data"
metrics:
  duration: "24m 54s (both plans)"
  completed_date: "2026-07-19"
status: complete

# Phase 3 Plan 1: Async DB Foundation — Summary

Created the async database foundation: aiosqlite dependency, configurable connection pool, and async query functions that mirror the existing synchronous queries. All async functions pass correctness parity tests against their sync equivalents and support dual-read (SQLite / JSON) fallback.

## Tasks

### Task 1: Add aiosqlite dependency + async pool config

- Added `aiosqlite>=0.20` to pyproject.toml and requirements.txt
- Added `async_pool_size: int = 5` to config.py Settings class (SOC_DB_ASYNC_POOL_SIZE)
- Installed aiosqlite 0.22.1
- **Commit:** 0974fb7

### Task 2: Async connection pool + async query functions

- Added `AsyncConnectionPool` class to connection.py with acquire/release/close lifecycle, asyncio.Semaphore throttling, WAL mode, Row factory
- Added `get_async_connection()` singleton factory
- Added 5 async query functions to queries.py: `get_all_async`, `get_by_id_async`, `search_async`, `get_vendors_async`, `get_stats_async`
- All async functions support dual-read (SQLite / JSON) fallback
- Updated `__init__.py` exports with all new async symbols
- Verified: pool initialises correctly, async functions return 1761 chips, async/sync parity confirmed
- **Commit:** 29f325a

### Task 3: Async query unit tests

- Created `tests/unit/test_queries_async.py` with 14 async query tests
- Test coverage: correctness parity, individual lookups, searches (basic, no results, concurrent), JSON fallback, pool acquire/release, concurrent queries via `asyncio.gather`
- Fixed chip IDs to use only IDs present in both temp test DB and main DB
- All 14 tests pass
- **Commit:** 776cdeb

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed chip IDs in test_get_by_id_async_matches_sync**

- **Found during:** Task 3 test execution
- **Issue:** Test used chip IDs (`mt6983`, `kirin9000`, `apple_m1`) that don't exist in the temp database created by the `db_conn` fixture. The `migrate()` function creates a temp DB from JSON files which may have different chip ID coverage than the main DB.
- **Fix:** Reduced test IDs to `sm8550_ac` and `exynos2200` — confirmed to exist in both databases
- **Commit:** 776cdeb

## Verification Results

- `python -m pytest tests/unit/test_queries_async.py -v --tb=short` — **14 passed**
- `python -m pytest tests/unit/test_db_dual_read.py -v --tb=short` — **7 passed** (no regression)
- `python -m pytest tests/unit/test_db_fts.py -v --tb=short` — **6 passed** (no regression)
- Pool initialisation: `python -c "from soc_db.db.connection import get_async_connection; p=get_async_connection(); print(f'Pool ready, max_size={p._max_size}')"` — **Pool ready, max_size=5**

## Success Criteria

- [x] pyproject.toml and requirements.txt both list `aiosqlite>=0.20`
- [x] `src/soc_db/config.py` has `async_pool_size: int = 5`
- [x] `src/soc_db/db/connection.py` has `AsyncConnectionPool` class with acquire/release/close + `get_async_connection()` factory
- [x] `src/soc_db/db/queries.py` has 5 async query functions
- [x] ALL async functions support dual-read (use_json=True fallback)
- [x] `src/soc_db/db/__init__.py` exports all new async symbols
- [x] `tests/unit/test_queries_async.py` has 14 passing tests
- [x] All existing DB tests continue to pass (no regression)
