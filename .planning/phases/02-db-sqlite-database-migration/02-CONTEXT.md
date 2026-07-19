# Phase 2: DB — SQLite Database Migration - Context

**Gathered:** 2026-07-19
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — smart discuss skipped)

<domain>
## Phase Boundary

SQLite database replaces flat JSON files with FTS5 full-text search and dual-read rollback via `SOC_DB_USE_JSON` env var.

Requirements: DB-01, DB-02, DB-03

Success criteria:
1. Migration tool transfers all 1746 chips from JSON to SQLite with zero data loss (field-by-field diff passes)
2. User can search chips with FTS5 full-text search and get equivalent or better results than v2.0 custom inverted index
3. User can set `SOC_DB_USE_JSON=true` and instantly fall back to JSON file store for rollback
4. All existing CLI commands (list, query, show, stats, enrich) work identically with SQLite backend
5. Existing JSON files remain untouched as frozen source of truth
</domain>

<decisions>
## Implementation Decisions

### the agent's Discretion
All implementation choices are at the agent's discretion — pure infrastructure phase.

### Key constraints from research
- SQLite with FTS5 — DuckDB rejected (no async driver, OLAP-optimized)
- aiosqlite for async (Phase 3), stdlib sqlite3 for sync (CLI)
- Dual-read via `SOC_DB_USE_JSON=true` env var
- Migration tool: CLI command `soc-db migrate`
- Pydantic models as contract between DB and API response
- `data/soc-db.db` — SQLite file in data/ directory (not published to GitHub Pages)
</decisions>

<code_context>
## Existing Code Insights

### Key Files
- `src/soc_db/common.py` — `load_all()`, `enrich_all()`, `write_vendor_file()`
- `src/soc_db/cli.py` — `cmd_list()`, `cmd_query()`, `cmd_show()`, `cmd_stats()`, `cmd_enrich()`
- `api/main.py` — `get_chips()`, `load_all()`, `_build_search_index()`, `_search_chips()`
- `src/soc_db/models.py` — Pydantic Chip model (95 fields)
- `data/*.json` — 44 vendor files (source of truth)
- `tests/unit/test_common.py`, `tests/integration/test_api.py`, `tests/conftest.py`

### Established Patterns
- All data loading goes through `load_all()` in both CLI and API
- Search uses custom inverted index (`_build_search_index()` + `_search_chips()`)
- CLI uses sync I/O, API runs async (FastAPI with asyncio)

### Integration Points
- Every command that reads chip data must be updated to support both SQLite and JSON backends
- Search must switch from custom inverted index to FTS5
- Migration must handle all 44 vendor files and their varying schemas
</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase.

Key constraints:
- `data/*.json` remains as frozen source of truth — never deleted
- `SOC_DB_USE_JSON=true` provides instant rollback
- Migration is additive — JSON files are never modified during migration
- SQLite schema must accommodate all 95+ fields from Chip model
- FTS5 virtual table for full-text search on chip data
- API backward compatibility: response shapes must not change
</specifics>

<deferred>
## Deferred Ideas

- DuckDB analytics export — v2.2+
</deferred>
