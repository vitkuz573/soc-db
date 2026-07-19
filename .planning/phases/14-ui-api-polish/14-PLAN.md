---
phase: 14
plan: 01
type: sequential
title: UI/API Polish
description: Chip comparison endpoint, quality dashboard, CLI completeness/source filters
autonomous: true
requirements: [UIPLUS-01, UIPLUS-02, UIPLUS-03]
---

# Phase 14 Plan 01: UI/API Polish

## Objective

Polish the API and CLI with chip comparison, a quality dashboard, and advanced CLI filtering capabilities — making the dataset more explorable for end users.

## Tasks

### Task 1: Chip comparison endpoint (UIPLUS-01)

- Add `GET /v1/chips/{chip_id}/compare?with={other_id}` to `api/main.py`
- Loads both chips by ID, compares all fields
- Returns: `{chip1, chip2, diffs: [{field, value1, value2, changed}], common_count, diff_count, total_fields}`
- Backward compatible — new endpoint only
- Fields with same value are grouped as "common fields" count
- Fields with different values are listed individually with both values

### Task 2: Quality dashboard endpoint (UIPLUS-02)

- Add `GET /v1/quality` to `api/main.py`
- Uses existing `QualityScorer` to generate a per-vendor quality report
- Returns: `{summary: {total_chips, total_vendors}, field_group_summary, vendors: {vendor: {fill_rates, source_diversity, conflict}}}`
- Backward compatible — new endpoint only

### Task 3: CLI improvements (UIPLUS-03)

- Add `--completeness-min` (alias `--completeness`) to `soc-db query` — filter by minimum completeness score
- Add `--source` to `soc-db query` — filter chips by provenance source name
- Add `--fields` to `soc-db query` — field projection (only show specified fields)
- Ensure `soc-db quality-report` command works correctly (already exists)
- All existing flags remain backward compatible

### Task 4: Tests

- Add API integration tests for `/v1/chips/{id}/compare?with={id2}`
- Add API integration tests for `/v1/quality`
- Add CLI tests for `--completeness-min`, `--source`, `--fields`
- All existing tests must still pass

### Task 5: Summary & state update

- Write 14-01-SUMMARY.md
- Update STATE.md (advance plan, record metrics)
- Update ROADME.md progress
- Mark UIPLUS-01, UIPLUS-02, UIPLUS-03 complete in REQUIREMENTS.md

## Success Criteria

1. `GET /v1/chips/{id}/compare?with={id2}` returns chip comparison with diff data
2. `GET /v1/quality` returns quality report from QualityScorer
3. CLI supports `--completeness-min`, `--source`, `--fields` flags
4. All existing tests pass
5. Backward compatible API and CLI
