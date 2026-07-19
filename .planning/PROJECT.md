# SoC Database (soc-db)

## Current Milestone: v3.1 Data Collection Run

**Goal:** Run all 11 scrapers against live sources, collect real data, replace legacy_v2 provenance.

**Target features:**
- COLLECT: Launch all scrapers — TechPowerUp, NotebookCheck, Geekbench, Qualcomm, MediaTek, Intel/AMD, Apple, Wikipedia, Apple DT, Wikidata
- PROVENANCE: Replace legacy_v2 with real source IDs
- QUALITY: Completeness ≥0.80, chip count > 5000

## What This Is

Enterprise-grade open database of SoC / CPU identifiers. Provides enrichment, lookup, and validation for 1746+ SoCs from 37 vendors including Qualcomm, MediaTek, Samsung, Apple, and more. Ships as a pip-installable Python package with CLI, REST API, and web UI.

## Core Value

Accurate, queryable, up-to-date SoC identification data that developers and tools can rely on as a single source of truth.

## Requirements

### Validated

- ✓ Chip data for 37 vendors across 1746+ entries — v2.0.0
- ✓ JSON Schema validation on every change — v2.0.0
- ✓ REST API with search, filter, pagination — v2.0.0
- ✓ CLI with list/query/show/stats/enrich commands — v2.0.0
- ✓ Wikipedia scraper pipeline — v2.0.0
- ✓ Web UI at GitHub Pages — v2.0.0
- ✓ 100% test coverage (405 tests) — v2.0.0
- ✓ Docker multi-stage build — v2.0.0
- ✓ CI pipeline (lint, typecheck, test, validate, security) — v2.0.0
- ✓ Pre-commit hooks — v2.0.0
- ✓ Structured JSON logging — v2.0.0
- ✓ Per-domain enrichment modules (cpu, gpu, memory, year, modem) — v2.1
- ✓ Snapshot test for ALL 1746 chips before/after refactoring — v2.1
- ✓ SQLite database with zero-data-loss JSON migration — v2.1
- ✓ FTS5 full-text search — v2.1
- ✓ Dual-read mode via `SOC_DB_USE_JSON=true` — v2.1
- ✓ Async database access via aiosqlite for API — v2.1
- ✓ Async chip cache with TTL-based invalidation — v2.1
- ✓ Redis-backed sliding window rate limiter — v2.1
- ✓ In-memory fallback when Redis unavailable — v2.1
- ✓ OpenTelemetry tracing for FastAPI + core library — v2.1
- ✓ Prometheus business metrics endpoint — v2.1
- ✓ Replace hardcoded VENDOR_KNOWLEDGE with Wikidata SPARQL — v2.1
- ✓ Weekly CI refresh of vendor knowledge — v2.1

### Active

- [ ] **COLLECT-01**: Run TechPowerUp scraper — 4000+ CPU/SoC
- [ ] **COLLECT-02**: Run NotebookCheck scraper — benchmarks per chip
- [ ] **COLLECT-03**: Run Geekbench scraper — CPU/GPU scores
- [ ] **COLLECT-04**: Run Qualcomm/MediaTek/Intel/AMD/Apple official scrapers
- [ ] **COLLECT-05**: Run Wikipedia scraper through BaseScraper framework
- [ ] **COLLECT-06**: Update provenance legacy_v2 → real source IDs
- [ ] **COLLECT-07**: Verify: completeness ≥0.80, chips > 5000

### Out of Scope

- New scraper development — all 11 scrapers exist, just need execution
- API/CLI changes — v3.0 shipped everything needed
- CI/CD — deferred

## Context

Codebase shipped v2.1 with all six enterprise hardening workstreams complete. Current chip count: 1761 entries across 43 vendors. Average completeness ranges from 0.19 to 0.54 — many vendors have only 1-2 placeholder entries. Gaps: Qualcomm (431 chips, but missing 2024-2026 models), Apple (41 — missing M3/M4), MediaTek (292 — missing Dimensity 9000+ series), Intel Atom (289 — legacy only), new vendors (HiSilicon Kirin 9000s+, Samsung Exynos 2400+, RISC-V). Existing scrapers: Wikipedia, Apple, Linux DeviceTree, Wikidata SPARQL. Need to add official vendor sources (Qualcomm Developer Network, MediaTek Helio/Dimensity listing, Apple Tech Specs).

## Constraints

- **Python 3.12+** — must remain compatible
- **JSON Schema backward compatibility** — existing `data/*.json` must migrate cleanly
- **API backward compatibility** — v1 endpoints must not break
- **CLI backward compatibility** — existing commands and output formats preserved
- **GitHub Pages integrity** — `docs/` directory (index.html, 404.html, swagger.html) must NEVER be touched or broken

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| SQLite as database backend | Built-in, zero-dependency, FTS5, `aiosqlite` for async | ✅ Good — 1761 chips migrated, 0 data loss |
| `aiosqlite` for async access | Native async, no thread pool, battle-tested | ✅ Good — `AsyncConnectionPool` with Semaphore throttling |
| Redis for rate limiter shared state | Multi-worker safe without sticky sessions | ✅ Good — sliding window via sorted sets with in-memory fallback |
| OpenTelemetry SDK + Prometheus | Industry standard, no vendor lock-in | ✅ Good — FastAPI auto-instrumentation, `/metrics` endpoint |
| Wikidata SPARQL for vendor knowledge | Authoritative, auto-updating, no manual maps | ✅ Good — 22 vendor QIDs, exponential backoff, TTL caching |
| Per-domain enrichment modules | Replace monolithic `enrich_one()` with domain experts | ✅ Good — 14 modules, snapshot regression on 1746 chips |
| In-place VENDOR_KNOWLEDGE mutation | All consumers see merged data without import changes | ⚠️ Revisit — module-level mutable state causes test isolation issues |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-19 after v3.0 milestone start*
