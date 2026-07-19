# Phase 4: RLIMIT — Redis-Backed Rate Limiting - Context

**Gathered:** 2026-07-19
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — smart discuss skipped)

<domain>
## Phase Boundary

Redis-backed sliding window rate limiter with transparent in-memory fallback for multi-worker safety.

Requirements: RLIMIT-01, RLIMIT-02

Success criteria:
1. API rate limits enforced via Redis shared state across multiple workers
2. When Redis is unavailable, rate limiter falls back to in-memory mode transparently (no 5xx errors)
3. Health endpoint reports Redis connectivity status
4. Rate limit headers (X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset) in API responses
</domain>

<decisions>
## Implementation Decisions

### the agent's Discretion
All implementation choices are at the agent's discretion — pure infrastructure phase.

### Key constraints from research
- redis[hiredis] >=5.0 (not 8.x — pin to <8.0 to avoid RESP3 protocol issues)
- slowapi library for FastAPI integration (or manual middleware)
- In-memory fallback must ship in SAME PR as Redis
- socket_connect_timeout=2 for Redis connection
- Rate limit headers must match standard format
- Health endpoint reports Redis status
</decisions>

<code_context>
## Existing Code Insights

### Key Files
- `api/main.py` — current in-memory rate limiter (sliding window, per-IP via defaultdict + asyncio.Lock)
- `src/soc_db/config.py` — SOC_DB_API_RATE_LIMIT, SOC_DB_API_RATE_LIMIT_WINDOW settings
- `tests/integration/test_api.py` — API tests

### Current Pattern
- In-memory sliding window per IP using defaultdict[list[float]]
- Asyncio.Lock for thread safety (single-worker only)
- No rate limit headers in responses
- 429 response with retry_after but no standard headers
</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase.

Key constraints:
- redis-py pin <8.0 (7.x line)
- hiredis C parser for performance
- Fallback must be transparent — no errors when Redis is down
- Rate limit headers in all API responses
- All existing tests must pass
- GitHub Pages must NOT be touched</specifics>

<deferred>
## Deferred Ideas

- Multi-worker deployment testing — Phase 5 or separate
</deferred>
