# Milestones

## v2.1 Full Enterprise Hardening (Shipped: 2026-07-19)

**Phases completed:** 6 phases, 13 plans

**Key accomplishments:**

- **REFAC** — Extracted monolithic enrichment into 14 per-domain modules with snapshot regression test (1746 chips verified identical)
- **DB** — SQLite database with FTS5 full-text search, zero-data-loss migration, and instant JSON rollback via `SOC_DB_USE_JSON`
- **ASYNC** — Non-blocking async data layer via aiosqlite with connection pool and TTL-based chip cache
- **RLIMIT** — Redis-backed sliding window rate limiter with transparent in-memory fallback and standard rate limit headers
- **OBSERVE** — OpenTelemetry tracing on FastAPI endpoints with Prometheus business metrics at `/metrics`
- **WIKIDATA** — Dynamic vendor knowledge from Wikidata SPARQL queries replacing hardcoded maps, with weekly CI refresh

**Stats:** 209 files changed, ~102,900 lines added, 6 OTel/Prometheus deps added

---
