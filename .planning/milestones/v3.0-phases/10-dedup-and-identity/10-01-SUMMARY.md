---
phase: 10-dedup-and-identity
plan: 01
subsystem: dedup
tags: [dedup, uuid, identity, matching, backward-compat]
requires: []
provides: [DedupEngine, chip_uuid, DedupEngine.match]
affects: [src/soc_db/common.py]
tech-stack:
  added: [rapidfuzz>=3.6]
  patterns: [multi-strategy matcher, UUID5 fingerprint, circular-import-safe lazy imports]
key-files:
  created:
    - src/soc_db/dedup.py
  modified:
    - src/soc_db/common.py
decisions:
  - DedupEngine.match preserves old _match_existing behavior via ID fast-path + name fallback
  - Lazy imports in dedup.py avoid circular import between common.py and dedup.py
  - chip["uuid"] is a separate field from chip["id"]; slug-based IDs are unchanged
metrics:
  duration: ~15 min
  completed: "2026-07-19"
status: complete
---

# Phase 10 Plan 01: DedupEngine & UUID Identity — Summary

**One-liner:** Created DedupEngine with multi-strategy matcher (exact → alias → regex → Wikidata → fuzzy/fast-text) and deterministic UUID5 from (vendor, model) fingerprints, integrated into `write_vendor_file()` and `enrich_one()`.

## What was built

1. **`src/soc_db/dedup.py`** — New module with:
   - `chip_uuid(vendor, model)` → deterministic UUID5 hex string (32 chars, no hyphens)
   - `CHIP_ALIASES` — 51 alias mappings (codename → model, e.g., "kalama" → "sm8550")
   - `DedupEngine` class with 5+1 matching strategies:
     1. `exact_model` — case-insensitive model comparison
     2. `alias` — normalized model lookup in alias registry
     3. `regex` — `extract_model()` from common.py
     4. `wikidata_qid` — shared Wikidata QID
     5. `fuzzy` — rapidfuzz `token_sort_ratio >= 85` with exact vendor match
     6. `name` — fallback exact name match (preserves old `_match_existing` behavior)
   - `canonical_id()` → UUID5 or slug fallback for backward compat
   - `batch_match()` and `deduplicate()` for bulk operations
   - Graceful degradation when rapidfuzz is not installed

2. **`src/soc_db/common.py`** — Modified:
   - `write_vendor_file()` now uses `DedupEngine.match()` for all merge decisions
   - UUID populated on existing and new chips during read/write
   - `_match_existing()` delegates to DedupEngine with ID fast-path preserved
   - `enrich_one()` adds `uuid` field to every chip

## Key Decisions

- **Circular import resolution:** `dedup.py` uses lazy imports (`from soc_db.common import extract_model as _extract_model`) inside method bodies to avoid the circular dependency chain `common.py → dedup.py → common.py`.
- **Backward compatibility:** `_match_existing()` keeps ID-based fast-path and delegates the rest to `DedupEngine`, preserving all existing test behavior.
- **UUID isolation:** `chip["uuid"]` is always separate from `chip["id"]`. The slug-based ID system is untouched.

## Commit History

- `f77b3a1` — feat(10-dedup): create DedupEngine with UUID5 + multi-strategy matcher
- `76da5df` — feat(10-dedup): integrate DedupEngine into common.py
- `7b261e0` — fix(10-dedup): circular import fix + name fallback in DedupEngine

## Verification

- ✅ `python3 -c "from soc_db.dedup import DedupEngine, chip_uuid; ..."` — clean import
- ✅ All 5 strategies verified: exact_model, alias, regex, wikidata_qid, fuzzy
- ✅ `enrich_one()` produces uuid on output chips
- ✅ `_match_existing()` backward compatible — all existing tests pass
