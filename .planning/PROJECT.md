# SoC Database (soc-db)

## Current State: v2.1 Full Enterprise Hardening — SHIPPED

**Completed:** 2026-07-19 | **6 phases, 13 plans, 209 files changed**

All six enterprise hardening workstreams shipped:
- ✅ **REFAC**: Monolithic enrichment split into 14 per-domain modules with snapshot regression
- ✅ **DB**: SQLite with FTS5 replacing flat JSON, dual-read JSON rollback via `SOC_DB_USE_JSON`
- ✅ **ASYNC**: Non-blocking async data layer via aiosqlite with TTL-based chip cache
- ✅ **RLIMIT**: Redis-backed rate limiter with transparent in-memory fallback
- ✅ **OBSERVE**: OpenTelemetry tracing + Prometheus business metrics at `/metrics`
- ✅ **WIKIDATA**: Dynamic vendor knowledge from Wikidata SPARQL with weekly CI refresh

**Next:** Planning v2.2 — Enterprise Delivery (CI/CD, Data Quality, API Mesh, Plugins)

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

(Next milestone requirements TBD — run `/gsd-new-milestone`)

### Out of Scope

- VS Code / Copilot plugins — deferred to v2.2+
- GraphQL endpoint — deferred to v2.2+
- WebSocket streaming — deferred to v2.3+
- Machine-readable errata database — long-term only

## Context

Codebase shipped v2.1 with all six enterprise hardening workstreams complete. Technical debt from v2.0 fully paid down: enrichment now modular (14 domain modules), data stored in SQLite with FTS5, async data layer via aiosqlite, Redis-backed rate limiting with fallback, OpenTelemetry tracing + Prometheus metrics, and dynamic Wikidata SPARQL vendor knowledge. Codebase at ~103K LOC added across 209 files. All 558 tests pass. Next focus: v2.2 Enterprise Delivery — CI/CD unification, data quality, API Mesh, and plugins.

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
*Last updated: 2026-07-19 after v2.1 milestone completion*
