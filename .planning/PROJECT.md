# SoC Database (soc-db)

## Current Milestone: v2.1 Full Enterprise Hardening

**Goal:** Transform soc-db into production-grade infrastructure — no shims, no shortcuts, no technical debt accumulation.

**Target features:**
- REFAC: Split monolithic enrichment into per-domain modules with snapshot regression
- DB: SQLite with FTS5 replacing flat JSON, dual-read rollback
- ASYNC: Non-blocking async data layer via aiosqlite
- RLIMIT: Redis-backed rate limiter with in-memory fallback
- OBSERVE: OpenTelemetry tracing + Prometheus business metrics
- WIKIDATA: Dynamic vendor knowledge from Wikidata SPARQL

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

### Active

- [ ] **REFAC-01**: Per-domain enrichment modules (cpu, gpu, memory, year, modem)
- [ ] **REFAC-02**: Snapshot test for ALL 1746 chips before/after refactoring
- [ ] **DB-01**: SQLite database with zero-data-loss JSON migration
- [ ] **DB-02**: FTS5 full-text search
- [ ] **DB-03**: Dual-read mode via `SOC_DB_USE_JSON=true`
- [ ] **ASYNC-01**: Async database access via aiosqlite for API
- [ ] **ASYNC-02**: Async chip cache with TTL-based invalidation
- [ ] **RLIMIT-01**: Redis-backed sliding window rate limiter
- [ ] **RLIMIT-02**: In-memory fallback when Redis unavailable
- [ ] **OBSERVE-01**: OpenTelemetry tracing for FastAPI + core library
- [ ] **OBSERVE-02**: Prometheus business metrics endpoint
- [ ] **WIKIDATA-01**: Replace hardcoded VENDOR_KNOWLEDGE with Wikidata SPARQL
- [ ] **WIKIDATA-02**: Weekly CI refresh of vendor knowledge

### Out of Scope

- VS Code / Copilot plugins — deferred to v2.2+
- GraphQL endpoint — deferred to v2.2+
- WebSocket streaming — deferred to v2.3+
- Machine-readable errata database — long-term only

## Context

Codebase is mature (v2.0.0 shipped) with strong CI, 100% coverage, and comprehensive codebase maps. Well-documented technical debt in CONCERNS.md: monolithic enrichment function (800+ lines), flat JSON file store, hardcoded vendor knowledge, synchronous I/O in API, in-memory rate limiter, no observability stack. The 10 improvement workstreams in v2.1 pay down this debt enterprise-style — no shims, no shortcuts.

## Constraints

- **Python 3.12+** — must remain compatible
- **JSON Schema backward compatibility** — existing `data/*.json` must migrate cleanly
- **API backward compatibility** — v1 endpoints must not break
- **CLI backward compatibility** — existing commands and output formats preserved
- **GitHub Pages integrity** — `docs/` directory (index.html, 404.html, swagger.html) must NEVER be touched or broken

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| SQLite as database backend | Built-in, zero-dependency, FTS5, `aiosqlite` for async | — Pending |
| `aiosqlite` for async access | Native async, no thread pool, battle-tested | — Pending |
| Redis for rate limiter shared state | Multi-worker safe without sticky sessions | — Pending |
| OpenTelemetry SDK + Prometheus | Industry standard, no vendor lock-in | — Pending |
| Wikidata SPARQL for vendor knowledge | Authoritative, auto-updating, no manual maps | — Pending |

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
*Last updated: 2026-07-19 after v2.1 milestone start*
