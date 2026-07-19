# SoC Database (soc-db)

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

- [ ] **REFAC-01**: Split `common.py` enrichment into per-domain modules
- [ ] **DB-01**: Replace flat JSON files with SQLite/DuckDB
- [ ] **RELEASE-01**: PyPI publish with CHANGELOG-based release automation
- [ ] **ASYNC-01**: Async data layer with non-blocking I/O
- [ ] **VALIDATE-01**: Data validation dashboard in CI + auto-PR for Wikidata corrections
- [ ] **TEST-01**: Property-based testing for enrichment pipeline
- [ ] **RATELIMIT-01**: Redis-backed rate limiter
- [ ] **OBSERVE-01**: OpenTelemetry tracing + Prometheus metrics
- [ ] **WIKIDATA-01**: Auto-generate vendor knowledge maps from Wikidata SPARQL

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

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| SQLite as database backend | Built-in, zero-dependency, FTS5, `aiosqlite` for async | — Pending |
| `aiosqlite` for async access | Native async, no thread pool, battle-tested | — Pending |
| Redis for rate limiter shared state | Multi-worker safe without sticky sessions | — Pending |
| OpenTelemetry SDK + Prometheus | Industry standard, no vendor lock-in | — Pending |
| Wikidata SPARQL for vendor knowledge | Authoritative, auto-updating, no manual maps | — Pending |

---
*Last updated: 2026-07-19 after v2.1 milestone start*
