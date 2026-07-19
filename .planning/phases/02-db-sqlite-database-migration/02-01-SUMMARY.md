---
phase: 02-db-sqlite-database-migration
plan: 01
status: complete
subsystem: db
tags: [sqlite, fts5, migration, cli]
requires: []
provides: [src/soc_db/db/__init__.py, src/soc_db/db/connection.py, src/soc_db/db/schema.py, src/soc_db/db/queries.py, src/soc_db/db/migrate.py]
affects: [src/soc_db/config.py, src/soc_db/cli.py]
tech-stack:
  added: [sqlite3 (stdlib), FTS5]
  patterns: [dual-read (SQLite/JSON fallback), lazy import, single-transaction migration]
key-files:
  created:
    - src/soc_db/db/__init__.py
    - src/soc_db/db/connection.py
    - src/soc_db/db/schema.py
    - src/soc_db/db/queries.py
    - src/soc_db/db/migrate.py
  modified:
    - src/soc_db/config.py
    - src/soc_db/cli.py
    - .gitignore
decisions:
  - 'Schema includes extra fields (source, connectivity, dsp) found in JSON data but not in Chip Pydantic model — prevents data loss during migration'
  - 'FTS5 uses external content mode (content=chips) to avoid duplicating text in the index'
  - 'JSON fallback uses lazy import of cli._load_all_json() to avoid circular deps'
  - 'Migration validates all 1761 chips field-by-field with 0 mismatches'
metrics:
  duration: null
  completed_date: 2026-07-19
---

# Phase 2 Plan 1: DB Package Core — Summary

Created the foundational SQLite database package (`src/soc_db/db/`) with connection management, full schema (68 columns), all query functions with dual-read SQLite/JSON fallback, and the JSON-to-SQLite migration tool. Added `SOC_DB_USE_JSON` and `SOC_DB_PATH` settings. 1761 chips migrated and validated with 0 field mismatches across 43 vendors.

## Tasks Executed

### Task 1: db package foundation
- `src/soc_db/db/__init__.py` — re-exports all public API
- `src/soc_db/db/connection.py` — `get_connection()`, `get_connection_cached()`, `get_db_path()` with WAL mode, Row factory, connection cache
- `src/soc_db/db/schema.py` — `create_tables()`, `drop_tables()`, `rebuild_fts()` with full 68-column chips table (all Chip model fields + extra `source`, `connectivity`, `dsp`), FTS5 virtual table (`chips_fts`) with `porter unicode61` tokenizer, indexes on vendor/year/architecture/gpu

### Task 2: Config + dual-read queries
- `src/soc_db/config.py` — added `db_path` (Path, default `data/soc-db.db`) and `use_json` (bool, default `False`) from `SOC_DB_PATH`/`SOC_DB_USE_JSON` env vars
- `src/soc_db/db/queries.py` — `get_all()`, `get_by_id()`, `search()` (FTS5 MATCH with LIKE fallback), `get_stats()`, `get_vendors()`, `filter_chips()` (dynamic WHERE with pagination)
- All query functions implement dual-read: check `settings.use_json` and either use SQLite or fall back to `cli._load_all_json()`
- `.gitignore` — added `data/soc-db.db*`

### Task 3: Migration tool + CLI cmd_migrate
- `src/soc_db/db/migrate.py` — `migrate()`, `validate_migration()`, `ensure_migrated()`
  - Batch INSERT (500/batch), single-transaction for atomicity
  - INSERT OR REPLACE for idempotent re-migration
  - `--force` flag drops and recreates tables
  - `ensure_migrated()` auto-migrates on first query if DB doesn't exist
- `src/soc_db/cli.py` — added `cmd_migrate()` and `migrate` subcommand with `--force` flag

## Migration Results

- **Total chips:** 1,761
- **Vendors:** 43
- **Validation:** PASS — 0 mismatches, 0 missing IDs, 0 extra IDs

## Deviations from Plan

### [Rule 1 - Bug] Fixed FTS5 rebuild syntax for external content
- **Found during:** Task 3 verification
- **Issue:** `INSERT INTO chips_fts(chips_fts, rowid, ...) VALUES('rebuild', ...)` is incorrect for external content tables — the correct syntax is `INSERT INTO chips_fts(chips_fts) VALUES('rebuild')` which re-scans the content table
- **Fix:** Changed `rebuild_fts()` to use the `'rebuild'` command

### [Rule 2 - Missing fields] Added extra JSON fields to schema
- **Found during:** Task 3 validation
- **Issue:** JSON data contains fields (`source`, `connectivity`, `dsp`) not in the Chip Pydantic model. Without adding these, migration would lose data (983/150 mismatches initially)
- **Fix:** Added `source` (TEXT), `connectivity` (TEXT), `dsp` (TEXT) columns to the schema and migration column list

### [Rule 2 - Missing migration fix] validate_migration() didn't use correct db_path
- **Found during:** Task 3 verification
- **Issue:** `validate_migration()` called `get_all()` without passing a connection, causing it to query the default database instead of the temp test database
- **Fix:** Changed `validate_migration()` to open a connection to the specified `db_path` and pass it to `get_all()`

## Verification Results

- ✅ All module imports resolve
- ✅ Schema verification: chips table created with 68 columns, all required columns present
- ✅ FTS5 virtual table created and functional
- ✅ Indexes on vendor/year/architecture/gpu
- ✅ Migration: 1761 chips inserted, validated with 0 mismatches
- ✅ Force re-migration produces same count
- ✅ FTS5 search: "snapdragon" → 217 results, "adreno" → 239 results, "mt6983" → 2 results
- ✅ CLI `soc-db migrate --force` runs successfully
- ✅ ruff lint checks pass (0 errors)

## Self-Check: PASSED

All created files verified to exist:
- `src/soc_db/db/__init__.py` ✓
- `src/soc_db/db/connection.py` ✓
- `src/soc_db/db/schema.py` ✓
- `src/soc_db/db/queries.py` ✓
- `src/soc_db/db/migrate.py` ✓
- `src/soc_db/config.py` (modified) ✓
- `src/soc_db/cli.py` (modified) ✓
- `.gitignore` (modified) ✓

Commits:
- `11761a1`: feat(02-01): create db package foundation
- `e7fec0f`: feat(02-01): add SOC_DB_USE_JSON/SOC_DB_PATH config, implement dual-read queries
- `31a5dfb`: feat(02-01): build migration tool and CLI cmd_migrate
