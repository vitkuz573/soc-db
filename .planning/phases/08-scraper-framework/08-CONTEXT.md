# Phase 8: Scraper Framework - Context

**Gathered:** 2026-07-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Plugin-based scraper framework with multi-tier anti-bot HTTP, per-source rate limiting, and schema drift detection.

Requirements: FRAME-01, FRAME-02, FRAME-03, FRAME-04

Success criteria:
1. New scraper = single file inheriting BaseScraper, auto-registered via SourceRegistry
2. Failed HTTP auto-escalates through httpx -> curl-cffi -> Playwright tiers
3. Per-source rate limiter with exponential backoff + jitter + failure isolation
4. Schema drift detection alerts when selectors yield <80% of expected fields
5. Wikipedia scraper migrated to prove pattern
</domain>

<code_context>
## Existing Code Insights

### Key Files
- `src/soc_db/scraper_wikipedia.py` — existing Wikipedia scraper (511 lines)
- `src/soc_db/scraper_apple.py` — Apple scraper
- `src/soc_db/common.py` — fetch(), enrich_one(), shared utilities
- `src/soc_db/robots.py` — robots.txt checker (Phase 7)
- `scripts/` — legacy duplicate scrapers

### Established Pattern
- Module-per-scraper in src/soc_db/
- Each scraper calls write_vendor_file() to merge data
- fetch() provides TTL-cached HTTP
- No framework, no base class
</code_context>

<specifics>
## Specific Ideas

1. BaseScraper with lifecycle: check_robots -> fetch -> parse -> dedup -> write
2. HTTPSource with tiered escalation (basic -> impersonated -> browser)
3. SourceRegistry auto-discovers scrapers by convention
4. RateLimiter per source (tenacity-based)
5. Schema drift: expected field count per source, alert on mismatch
6. Migrate Wikipedia scraper to prove pattern

Key deps: httpx, curl-cffi, selectolax, tenacity (from research)
</specifics>
