---
phase: 06-wikidata
plan: 01
subsystem: enrichment
tags: [wikidata, sparql, vendor-knowledge, enrichment]
requires: [01-04]
provides: [WIKIDATA-01, WIKIDATA-02]
affects: [enrich, cli, config]
tech-stack:
  added: [SPARQLWrapper>=2.0]
  patterns: [TTL caching, lazy import, exponential backoff]
key-files:
  created:
    - src/soc_db/wikidata.py
    - src/soc_db/enrich/_vendor_data_wikidata.py
    - data/vendor_overrides.json
    - .github/workflows/wikidata-refresh.yml
    - tests/unit/test_wikidata.py
    - tests/integration/test_wikidata.py
  modified:
    - pyproject.toml
    - src/soc_db/config.py
    - src/soc_db/enrich/_vendor_data.py
    - src/soc_db/cli.py
    - tests/conftest.py
metrics:
  duration: "~45 min"
  tasks: 3
  files_created: 6
  files_modified: 5
  unit_tests: 24
  integration_tests: 12
status: complete
---

# Phase 6 Plan 1: Wikidata Knowledge Sync — Summary

**One-liner:** Built end-to-end Wikidata SPARQL pipeline: query module with caching and exponential backoff, merge layer with override support, CLI `wikidata-refresh` subcommand, and weekly CI workflow — all opt-in via `SOC_DB_USE_WIKIDATA=false` (default).

## Objectives Met

1. **`src/soc_db/wikidata.py`** — queries Wikidata for process node (P2175), GPU (P488), and architecture (P10620) per vendor, with TTL caching, exponential backoff (1s-16s), and dry-run mode
2. **`src/soc_db/enrich/_vendor_data_wikidata.py`** — merges Wikidata results with hardcoded VENDOR_KNOWLEDGE, applies `data/vendor_overrides.json` manual corrections
3. **`data/vendor_overrides.json`** — empty override file ready for manual entries
4. **`src/soc_db/cli.py`** — `wikidata-refresh [--dry-run]` subcommand added
5. **`.github/workflows/wikidata-refresh.yml`** — weekly schedule (Monday 06:00 UTC), dry-run by default, creates PR via peter-evans/create-pull-request
6. **`_vendor_data.py`** — VENDOR_KNOWLEDGE conditionally reassigns when `SOC_DB_USE_WIKIDATA=true`
7. **All 400+ existing tests pass** without modification
8. **`docs/` directory untouched**

## Task Execution

### Task 1: Core Wikidata SPARQL module with caching and backoff

- Added `SPARQLWrapper>=2.0` to pyproject.toml
- Added `use_wikidata: bool = False` to config.py (SOC_DB_USE_WIKIDATA env var)
- Created `src/soc_db/wikidata.py` with:
  - `VENDOR_QIDS` dict mapping 22 vendors (from scraped QIDs + Google/AMD) to Wikidata QIDs
  - `_build_process_query`, `_build_gpu_query`, `_build_architecture_query` — SPARQL builders using P2175/P488/P10620
  - `run_sparql()` with exponential backoff (1s, 2s, 4s, 8s, 16s max, 5 retries)
  - `_cached_sparql()` with TTL disk caching (24h default, same pattern as `fetch()` in common.py)
  - `refresh_vendor_knowledge(dry_run=False)` — iterates VENDOR_QIDS, queries all 3 properties, returns structured dict; dry_run=True logs and returns {}
- 24 unit tests created covering query strings, response parsing, caching, backoff, dry-run mode

### Task 2: Merge layer with overrides, wire into VENDOR_KNOWLEDGE

- Created `data/vendor_overrides.json` with empty `{}`
- Created `src/soc_db/enrich/_vendor_data_wikidata.py` with:
  - `load_overrides()` — reads vendor_overrides.json, caches result
  - `merge_vendor_knowledge()` — deep-copies VENDOR_KNOWLEDGE, merges Wikidata results per-field, applies overrides
  - `get_vendor_knowledge()` — entry point: checks settings.use_wikidata, lazy-imports wikidata module, falls back on error
- Updated `_vendor_data.py` to conditionally reassign VENDOR_KNOWLEDGE at module load time when SOC_DB_USE_WIKIDATA=true
- Merge layer uses in-place mutation of VENDOR_KNOWLEDGE dict so all consumers see updated data

### Task 3: CLI command, GitHub Actions workflow, integration tests

- Added `cmd_wikidata_refresh` handler and subparser to `cli.py`
- Created `.github/workflows/wikidata-refresh.yml` with:
  - `schedule` trigger (cron: `0 6 * * 1`) — runs dry-run
  - `workflow_dispatch` trigger with dry_run choice
  - PR creation via peter-evans/create-pull-request@v6
- Added `use_wikidata_true` fixture to conftest.py
- 12 integration tests covering CLI help, dry-run, vendor structure, workflow YAML validation

## Key Decisions

- **SOC_DB_USE_WIKIDATA=false by default** — all existing tests pass unchanged; Wikidata mode is opt-in
- **Lazy import pattern** — `_vendor_data_wikidata.py` imports `refresh_vendor_knowledge()` inside `get_vendor_knowledge()`, avoiding SPARQLWrapper import at module level when Wikidata mode is disabled
- **In-place dict mutation** — VENDOR_KNOWLEDGE is mutated at module level so all consumers (imported as `from soc_db.enrich._vendor_data import VENDOR_KNOWLEDGE`) see the updated reference
- **Dry-run returns {}** — `refresh_vendor_knowledge(dry_run=True)` logs per-vendor stats and returns empty dict; CLI prints summary from logged output
- **Wikidata takes precedence** for known items; overrides win over everything
- **YAML `on:` trigger** — pyyaml parses `on:` as boolean `True`; test handles both `data.get("on")` and `data.get(True)` forms

## Deviations from Plan

None — plan executed exactly as written.

## Verification Results

| Check | Status |
|-------|--------|
| Unit tests (`tests/unit/` - all 533) | ✅ Pass |
| Integration tests (`tests/integration/test_wikidata.py` - 12) | ✅ Pass |
| Snapshot test (`tests/snapshot/test_enrich_snapshot.py`) | ✅ Pass |
| Existing CLI tests (`tests/integration/test_cli.py` - 4) | ✅ Pass |
| Ruff lint (all modified files) | ✅ Pass |
| Mypy type check (wikidata.py, _vendor_data_wikidata.py) | ✅ Pass |
| CLI smoke test (`soc-db wikidata-refresh --help`) | ✅ Pass |
| GHA workflow YAML validation | ✅ Pass |
| No docs/ files modified | ✅ Pass |

## Self-Check

- `src/soc_db/wikidata.py`: ✅ Created, imports clean, ruff+ mypy+ pass
- `src/soc_db/enrich/_vendor_data_wikidata.py`: ✅ Created, merge logic correct
- `data/vendor_overrides.json`: ✅ Created with `{}`
- `src/soc_db/cli.py`: ✅ wikidata-refresh subcommand working
- `.github/workflows/wikidata-refresh.yml`: ✅ Exists, valid YAML, has schedule + PR step
- `tests/unit/test_wikidata.py`: ✅ 24 tests, all pass
- `tests/integration/test_wikidata.py`: ✅ 12 tests, all pass
- Commit 1 (37b9c8e): ✅ core module + merge layer + unit tests
- Commit 2 (18dad64): ✅ CLI + CI + integration tests

## Self-Check: PASSED
