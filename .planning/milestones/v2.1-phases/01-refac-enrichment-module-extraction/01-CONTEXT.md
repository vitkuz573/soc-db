# Phase 1: REFAC — Enrichment Module Extraction - Context

**Gathered:** 2026-07-19
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — smart discuss skipped)

<domain>
## Phase Boundary

Enrichment pipeline uses per-domain modules (cpu, gpu, memory, year, modem) instead of monolithic `enrich_one()`, with zero regression verified by snapshot test.

Requirements: REFAC-01, REFAC-02

Success criteria:
1. All 1746 chips produce identical enrichment output after refactoring (snapshot test passes)
2. Developer can read and modify enrichment logic in per-domain files instead of one 700-line function
3. CI pipeline runs snapshot test on every commit to detect enrichment regression
4. Year inference priority ordering is explicitly documented per domain
</domain>

<decisions>
## Implementation Decisions

### the agent's Discretion
All implementation choices are at the agent's discretion — pure infrastructure phase.
</decisions>

<code_context>
## Existing Code Insights

### Key File
- `src/soc_db/common.py` (1561 lines) — contains monolithic `enrich_one()` (~700 lines), `VENDOR_KNOWLEDGE`, `FIELD_GROUPS`, `FIELD_WEIGHTS`
- `src/soc_db/models.py` — Pydantic Chip model (95 fields)
- `tests/unit/test_common.py` — existing tests, including ~180 year inference parametrized cases
- `tests/property/test_enrich_one.py` — Hypothesis property tests
- `tests/benchmark/test_enrich_one.py` — pytest-benchmark tests

### Established Patterns
- Google-style docstrings
- `from __future__ import annotations` in newer/migrated files
- Ruff line length 160, target py312
- mypy strict (with exemptions for scripts/tests/parsers/scrapers)

### Integration Points
- `enrich_one()` is called from `enrich_all()` which is called from `write_vendor_file()` and CLI `cmd_enrich()`
- `VENDOR_KNOWLEDGE` maps are consumed inline within `enrich_one()`
- Chip dicts flow from JSON → `enrich_one()` → JSON/Pydantic/API response

### Critical Risk
- Year inference is a 530-line priority-ordered if/elif chain with `break` statements — ordering changes silently change years for 1746 chips
- Snapshot test must capture ALL chips' enrichment output BEFORE any refactoring
</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. Open to standard approaches for module extraction.

Key constraints from research:
- `common.py` should remain as a re-export shim during migration to avoid breaking imports
- Use `TYPE_CHECKING` guards and `__future__ import annotations` to prevent circular imports
- Year inference priority ordering must be explicitly documented in its own module
- Per-domain modules under `src/soc_db/enrich/` (cpu.py, gpu.py, memory.py, year.py, modem.py)
</specifics>

<deferred>
## Deferred Ideas

None — phase scope is well-defined.
</deferred>
