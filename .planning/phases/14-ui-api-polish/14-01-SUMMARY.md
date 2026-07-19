---
phase: 14
plan: 01
type: sequential
title: UI/API Polish
description: Chip comparison API endpoint, quality dashboard API endpoint, CLI completeness/source/fields filters
requirements: [UIPLUS-01, UIPLUS-02, UIPLUS-03]
status: complete
completed: 2026-07-19
duration: ~25 min
tags: [api, cli, quality, comparison, ux]
provides: [UIPLUS-01, UIPLUS-02, UIPLUS-03]
tech-stack:
  added: []
  patterns: [FastAPI sub-path routing, QualityScorer report serialization, argparse aliases, provenance-based filtering]
key-files:
  created:
    - .planning/phases/14-ui-api-polish/14-PLAN.md
  modified:
    - api/main.py (compare endpoint + quality dashboard + root docs)
    - src/soc_db/cli.py (--completeness-min alias, --source filter, --fields projection)
    - tests/integration/test_api.py (compare + quality tests)
    - tests/integration/test_cli.py (filter flag tests)
decisions:
  - "Comparison skip fields: provenance, sources, updated, _dedup_strategy, rating, benchmarks, cache excluded from comparison since they are system/internal"
  - "--completeness-min is an alias for existing --completeness (backward compatible)"
  - "--source filter matches against provenance field values; only works in JSON mode since SQLite DB lacks provenance column"
  - "quality-report CLI command already existed; no changes needed"
metrics:
  duration_minutes: 25
  tasks_completed: 4
  files_modified: 5
  tests_added: 12
  commit_count: 2
---

# Phase 14 Plan 01: UI/API Polish — Summary

## One-Liner

Added chip comparison endpoint (`GET /v1/chips/{id}/compare?with={id2}`), quality dashboard endpoint (`GET /v1/quality`), and CLI filtering enhancements (`--completeness-min`, `--source`, `--fields` for `soc-db query`) — all backward compatible.

## Objective

Polish the API and CLI with chip comparison, a quality dashboard, and advanced CLI filtering capabilities — making the dataset more explorable for end users.

## Tasks Executed

### Task 1: Chip comparison endpoint (UIPLUS-01)

**Endpoint:** `GET /v1/chips/{chip_id}/compare?with={other_id}`

Returns side-by-side comparison of two chips:
- `chip1` / `chip2`: The full chip records
- `diffs`: Array of `{field, value1, value2}` for fields that differ
- `common_count`: Number of fields with identical values
- `diff_count`: Number of fields with different values
- `total_compared_fields`: Total fields compared

System/internal fields (provenance, sources, benchmarks, rating, cache) are excluded from comparison.

**Files:** `api/main.py` — added `_COMPARE_SKIP_FIELDS` constant and `compare_chips()` endpoint.

### Task 2: Quality dashboard endpoint (UIPLUS-02)

**Endpoint:** `GET /v1/quality`

Returns the full `QualityReport.to_dict()` output directly from the existing `QualityScorer`. Includes:
- `summary`: Total chips and vendors
- `field_group_summary`: Average fill rates by field group
- `vendors`: Per-vendor fill rates, source diversity, and conflict metrics

**Files:** `api/main.py` — added `quality_dashboard()` endpoint. Updated root endpoint docs.

### Task 3: CLI improvements (UIPLUS-03)

Added to `soc-db query`:
- `--completeness-min` (alias: `--completeness`) — filter by minimum completeness score (0-1)
- `--source <name>` — filter chips by provenance source name (matches against `provenance` dict values)
- `--fields <comma-separated>` — field projection for CSV/JSON/table output

The `quality-report` CLI command already existed and required no changes.

**Files:** `src/soc_db/cli.py` — added argument definitions and filtering/projection logic.

### Task 4: Tests

- **API tests (5):** `test_compare_chips`, `test_compare_chips_same`, `test_compare_chips_not_found_chip1`, `test_compare_chips_not_found_chip2`, `test_compare_chips_missing_with_param`, `test_quality_dashboard`
- **CLI tests (7):** `test_query_completeness_min`, `test_query_completeness_legacy_alias`, `test_query_source_filter`, `test_query_fields_projection`, `test_query_fields_csv`, `test_quality_report_cli`, `test_quality_report_json`

**Files:** `tests/integration/test_api.py`, `tests/integration/test_cli.py`

**Coverage:** All 12 new tests pass. All existing tests (unit + integration) remain passing.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical] `--completeness` flag already existed but as an undocumented alias**
- **Found during:** Task 3 implementation
- **Issue:** The plan specified `--completeness-min` but `--completeness` already existed. Both should work.
- **Fix:** Added `--completeness-min` as an alias for `--completeness` using argparse dest reuse.
- **Files modified:** `src/soc_db/cli.py`
- **Commit:** `a809dcd`

## Known Issues / Notes

- The `--source` CLI filter matches against `provenance` field values. Currently only `legacy_v2` provenance exists across all chips. The `provenance` column is not present in the SQLite schema, so this filter only works in JSON mode (`SOC_DB_USE_JSON=true`).

## Commit History

| Commit | Message |
|--------|---------|
| `a809dcd` | feat(14-ui-api-polish): chip compare endpoint, quality dashboard, CLI completeness/source/fields filters |
| `c05e6bc` | test(14-ui-api-polish): add tests for chip compare, quality dashboard, CLI filters |

## Self-Check: PASSED

- [x] `GET /v1/chips/{id}/compare?with={id2}` — verified returns diffs, common count, correct chip IDs
- [x] `GET /v1/quality` — verified returns quality report with summary, vendors, field groups
- [x] `soc-db query --completeness-min 0.5` — verified filters correctly
- [x] `soc-db query --completeness 0.5` — legacy alias still works
- [x] `soc-db query --source legacy_v2` — verified filters by provenance
- [x] `soc-db query --fields id,name,vendor` — verified field projection works
- [x] `soc-db quality-report` — verified quality report output works
- [x] All existing unit tests pass (33 tests)
- [x] All existing CLI integration tests pass (11 tests)
- [x] New API endpoint tests pass (5 tests)
- [x] Backward compatible — no existing endpoints or CLI flags changed
