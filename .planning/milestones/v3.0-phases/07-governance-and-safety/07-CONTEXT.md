# Phase 7: Governance & Safety - Context

**Gathered:** 2026-07-19
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — smart discuss skipped)

<domain>
## Phase Boundary

Legal review of all scraping targets and GitHub Pages filesystem boundary guard.

Requirements: GOV-01, GOV-02

Success criteria:
1. Every scraping target has documented legal basis (ToS, robots.txt, compliance matrix)
2. Filesystem boundary guard prevents pipeline writes to `docs/` — CI-enforced
3. Scraper identity strategy documented and implemented per target
4. robots.txt caching/compliance framework operational
</domain>

<decisions>
## Implementation Decisions

### the agent's Discretion
All implementation choices are at the agent's discretion — infrastructure phase.

### Key constraints
- GH Pages guard: simple write-time check, not a separate process
- Legal review: documented in data/LEGAL.md, not legal advice
- robots.txt: checked before each scrape, cached with TTL
</decisions>

<code_context>
## Existing Code Insights

### Key Files
- `api/main.py` — FastAPI app (docs/ not referenced)
- `tests/validate.py` — writes to data/index.json
- `src/soc_db/db/migrate.py` — writes to data/soc-db.db
- `scripts/` — legacy scripts that may write to files

### Risk Assessment
- No existing code writes to `docs/` — but no guard either
- robots.txt checking: not implemented in any scraper
- Legal: no existing compliance documentation
</code_context>

<specifics>
## Specific Ideas

1. Create `data/LEGAL.md` with scraping compliance matrix
2. Add `DOCS_DIR = Path("docs")` guard to common.py with CI check
3. Add robots.txt caching to fetch() in common.py
4. Document scraper identity (User-Agent per source)
</specifics>

<deferred>
## Deferred Ideas

- Legal review of GSMArena/DeviceSpecifications — Phase 14
</deferred>
