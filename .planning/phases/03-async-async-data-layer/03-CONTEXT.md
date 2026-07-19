# Phase 3: ASYNC — Async Data Layer - Context

**Gathered:** 2026-07-19
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — smart discuss skipped)

<domain>
## Phase Boundary

API server uses async database access via `aiosqlite` without blocking the event loop.

Requirements: ASYNC-01, ASYNC-02

Success criteria:
1. API server uses async connection pool (aiosqlite) — no `asyncio.to_thread()` wrappers for DB access
2. Chip cache (`get_chips()`) operates asynchronously with TTL-based invalidation, not synchronous preloading
3. API handles concurrent requests without event loop blocking
4. Enrichment pipeline profiling determines if ProcessPoolExecutor is needed for CPU-bound work
</domain>

<decisions>
## Implementation Decisions

### the agent's Discretion
All implementation choices are at the agent's discretion — pure infrastructure phase.

### Key constraints from research
- aiosqlite >=0.20 for async DB access
- No thread pools — native async connection
- CLI stays on sync sqlite3 (no async needed there)
- Connection pool with max_size configurable via env var
- TTL-based cache for chip data (configurable via SOC_DB_CACHE_TTL)
</decisions>

<code_context>
## Existing Code Insights

### Key Files
- `src/soc_db/db/connection.py` — sync connection (needs async counterpart)
- `src/soc_db/db/queries.py` — query functions (need async versions)
- `api/main.py` — get_chips(), load_all_async(), middleware
- `src/soc_db/config.py` — settings
- `tests/integration/test_api.py` — API integration tests

### Current Pattern
- `get_chips()` loads ALL chips synchronously on cache miss
- `load_all_async()` exists but wraps sync load_all in asyncio.to_thread()
- Search index built synchronously in get_chips()
</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase.

Key constraints:
- aiosqlite dependency must be added to pyproject.toml
- Async connection pool must be configurable
- TTL-based cache invalidation period must be configurable
- enrichment_one() is CPU-bound — benchmark to decide if ProcessPoolExecutor needed
- All existing tests must pass
- GitHub Pages must NOT be touched
</specifics>

<deferred>
## Deferred Ideas

None
</deferred>
