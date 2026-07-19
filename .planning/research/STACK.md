# Technology Stack — v3.0 Full SoC Coverage

**Project:** soc-db v3.0 — Massive Data Collection Pipeline
**Researched:** 2026-07-19
**Confidence:** HIGH

> **Scope:** This document covers NEW dependencies for v3.0's data collection, deduplication, and validation features. All v2.1 dependencies (FastAPI, uvicorn, pydantic, aiosqlite, beautifulsoup4, opentelemetry, redis, etc.) remain unchanged. See `.planning/research/STACK.md` (v2.1 version) for the existing stack.

## Executive Summary

v3.0 transforms the project from a Wikipedia-scraping + enrichment pipeline into a multi-source data collection engine. The stack needs three capability additions:

1. **Production-grade HTTP** — replace the hobby-grade `fetch()` (stdlib `urllib` + disk cache) with async HTTP, retry logic, connection pooling, and anti-bot impersonation.
2. **Structured data deduplication** — NOT probabilistic (no recordlinkage/splink), but a deterministic multi-source merge engine that exploits the SoC domain's unique identifiers (model numbers).
3. **Data quality at scale** — cross-source validation, completeness tracking, outlier detection, and automated PR workflows.

**Key insight:** The SoC domain has natural unique keys (Qualcomm SM8550, MediaTek MT6983, Apple T8130). Probabilistic record linkage (recordlinkage, splink) is overkill and counterproductive — it introduces uncertainty where none exists. A deterministic merge engine with vendor-specific ID extractors is the right approach.

---

## Recommended New Dependencies

### Core Scraping Stack

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `httpx` | >=0.28 | Async HTTP client for all new scrapers | Full async/await support, HTTP/2, connection pooling, timeouts. `requests`-compatible API. Replaces `urllib.request` in new code. **But keep `requests` for existing scrapers** (Wikipedia, Apple) — no need to rewrite them. |
| `curl-cffi` | >=0.15 | Anti-bot HTTP with browser impersonation | Impersonates Chrome/Firefox TLS/JA3 fingerprints. Required for GSMArena, DeviceSpecifications, and Geekbench (all block plain `requests`/`httpx` user-agents). Also supports asyncio via `AsyncSession`. Pre-compiled wheels for all platforms. **DO NOT use Selenium/Puppeteer** — curl-cffi handles anti-bot at the HTTP layer without browser overhead. |
| `selectolax` | >=0.4 | High-speed HTML parsing for high-volume pages | 3-4x faster than BeautifulSoup+lxml for bulk parsing (Lexbor backend in Cython). Use for GSMArena/DeviceSpecifications pages where 5000+ pages need parsing. **Keep BeautifulSoup for existing scrapers** — its forgiving parser is better for Wikipedia infoboxes with broken HTML. |
| `tenacity` | >=9.0 | Retry logic with exponential backoff | Replaces the ad-hoc `time.sleep(1)` in `common.py`. Decorator-based, async-compatible, configurable retry strategies, and jitter support. Required for vendor API rate limits and flaky scrape targets. |
| `jmespath` | >=1.1 | JSON query expressions for API responses | Vendor API responses (Qualcomm Developer Network, DeviceTree) return nested JSON. JMESPath extracts specific fields without writing nested `dict.get()` chains. Much cleaner than manual path traversal. |

### Data Deduplication & Merge

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| *(custom)* | — | `DedupEngine` class in `soc_db/dedup/` | Deterministic multi-source merge using vendor-specific model number extractors. Each vendor gets a `Matcher` subclass that knows how to extract unique IDs from that source's format. **See Architecture section below.** |
| `rapidfuzz` | >=3.6 | Fuzzy string matching for name dedup fallback | C-accelerated Levenshtein/Jaro-Winkler for cases where model numbers disagree (e.g., "8 Gen 2" vs "Snapdragon 8 Gen 2"). 10-100x faster than `difflib`. Only used as fallback when deterministic matching fails. |

### Data Quality & Validation

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **Pydantic v2 validators** | *(already have)* | Cross-field validation at scale | Add `@model_validator(mode='after')` methods to the existing `Chip` model. No new validation library needed — Pydantic v2's validator system handles cross-field checks (e.g., `clock_max >= clock_min`, year + process node consistency). |
| `pandas` | >=2.2 | Bulk statistical quality checks | DataFrames for completeness scoring, field correlation analysis, outlier detection across 5000+ chips. Not required at runtime — used in CI/audit scripts. Consider adding as dev dependency only. |

### CI / Auto-PR Workflow

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `GitPython` | >=3.1 | Programmatic git operations for auto-PR | Required for the "scraper runs → creates branch → commits data → opens PR" workflow. Handles branch creation, commit, push, and PR body generation. **Caution:** GitPython is in maintenance mode — use it for simple porcelain operations only (commit/push), not complex rebase workflows. Do not install in production — only in CI runner. |
| `gh` CLI | *(system)* | GitHub PR creation via GitHub Actions | `gh pr create` in CI is simpler and more reliable than using PyGithub or similar. The GitPython + `subprocess.run("gh pr create ...")` combo covers all needs. |

### Additional Data Sources

| Source | Access Method | Why This Method |
|--------|---------------|-----------------|
| **GSMArena** | Scrape device pages (curl-cffi + selectolax) | No public API. Each device page has a "Chipset" field. URL pattern: `https://www.gsmarena.com/{device_id}.php`. Start from brand listing pages. ~15000 devices total, ~5000+ relevant (have SoC info). |
| **DeviceSpecifications** | Scrape (curl-cffi + selectolax) | Similar to GSMArena. Structured spec tables per device. Less traffic protection than GSMArena. |
| **Geekbench Browser** | Scrape search results (curl-cffi) | No public API. Search by processor name at `https://browser.geekbench.com/v6/cpu/search?q={soc_name}`. Returns HTML result cards. Rate limit aggressively. |
| **Antutu** | Scrape ranking pages (curl-cffi) | No public API. Ranking pages at `https://www.antutu.com/en/ranking/rank.htm`. Requires browser impersonation. |
| **Qualcomm Developer Network** | Scrape product listing pages | `https://developer.qualcomm.com/product-categories` — structured product cards with model numbers, specs. |
| **MediaTek** | Scrape product pages | `https://www.mediatek.com/products` — product listing with filter by category. |

---

## NOT to Add

| Technology | Why NOT | What To Do Instead |
|------------|---------|-------------------|
| **Scrapy** | Framework overhead for simple page scraping. Our scrapers are per-source modules (like existing `scraper_wikipedia.py`), not a crawl pipeline. Scrapy's middleware/extension system is unused complexity. | `httpx` + `tenacity` for HTTP; `selectolax` for parsing. Keep the module-per-source pattern. |
| **Selenium / Playwright / Puppeteer** | Browser automation is 50-100x slower than HTTP scraping. None of the target sources require JavaScript rendering for core data (GSMArena, Geekbench, DeviceSpecifications all render data in HTML). | `curl-cffi` with browser impersonation handles anti-bot at the HTTP layer. If a source absolutely requires JS (unlikely for spec data), use `Playwright` with `headless=True` as a last resort — but this should be a future concern, not v3.0. |
| **recordlinkage** | Probabilistic record linkage for structured hardware identifiers is wrong. SoCs have unique model numbers (SM8550, MT6983, T8130). There is no "fuzzy match" problem to solve — the ID is the ID. Recordlinkage is designed for name/address dedup where no unique key exists. | Build a deterministic `DedupEngine` with vendor-specific `Matcher` implementations. |
| **splink** | Same problem as recordlinkage — probabilistic matching for data that has deterministic unique keys. Splink's DuckDB backend is powerful but unnecessary for 5000 records. Deterministic matching is O(n) with hash lookups; probabilistic is O(n²) pair generation. | Deterministic merge engine. |
| **PostgreSQL / DuckDB / ClickHouse** | SQLite handles 5000 records easily. FTS5 works. Adding a database server adds deployment complexity (Docker, connections, backups) with zero benefit at this scale. | Keep SQLite. The existing dual-read (SQLite + JSON) pattern handles it. Can revisit at 100K+ chips. |
| **Celery / Redis Queue / Task workers** | Scraping is a batch operation, not a background task queue. Running scrapers sequentially with retries is simpler and more debuggable than queue-based orchestration. | `tenacity` for retries. A simple `Pipeline` class that runs scrapers in order, collecting results. |
| **Apache Airflow / Prefect** | Data pipeline orchestration is overkill for a single-machine batch process. Airflow requires a database, scheduler, and workers. Prefect adds similar complexity. Scraper runs are triggered manually or on a cron schedule. | GitHub Actions cron trigger + simple CLI (`soc-db scrape --all`). |
| **Great Expectations** | Heavy framework (500+ MB) for data quality checks. The SoC schema has 95 fields — most are optional nullable. GE's expectation suite concept doesn't map well to optional fields with per-vendor patterns. | Pydantic validators + custom completeness scoring (already exists: `compute_completeness()`). Add cross-source conflict detection as a simple Python module. |
| **pandera** | Schema validation library built on pandas. Overkill when Pydantic already validates all 95 fields at serialization time. pandera adds a second validation layer with different syntax. | Pydantic `@model_validator` for everything. |
| **pgvector / vector embeddings** | Not relevant. SoC identification is exact match on model numbers, not semantic similarity search. | FTS5 for name search. Model number regex for exact match. |
| **gRPC / tRPC** | Not adding a second API layer. REST works, exists, and is consumed. | Keep FastAPI REST. |
| **SQLAlchemy** | The project uses raw JSON/dict patterns for data. SQLAlchemy's ORM would conflict with the existing enrichment pipeline that mutates dicts in-place. The data layer is aiohttp-based write-through JSON. | Keep existing dual-read pattern. |

---

## Integration with Existing Scrapers

### What Stays

| Scraper | Status | Reason |
|---------|--------|--------|
| `scraper_wikipedia.py` | **Keep** | 1761 chips from 12 vendors. Still the best single-source baseline. Add it as source "wikipedia" in dedup engine. |
| `scraper_apple.py` | **Keep** | Apple silicon T-number mapping. Source of truth for A/M-series model numbers. |
| `wikidata.py` | **Keep** | SPARQL queries for vendor knowledge (process nodes, GPU families, etc.). This is lookup data, not chip entries. |

### What Changes

| Module | Change | Rationale |
|--------|--------|-----------|
| `common.py` (fetch function) | **Deprecate** for new code | Stdlib `urllib` + disk cache is insufficient for 50+ vendors. New scrapers use `httpx` with Redis-backed cache or proper file-based cache with TTL. The old `fetch()` stays for backward compat with Wikipedia/Apple scrapers. |
| `common.py` (merge_chips, enrich_one, enrich_all) | **Keep** and extend | The existing merge logic (`_match_existing()`) handles single-source dedup. v3.0 needs `DedupEngine` for multi-source merge and conflict resolution. The enrichment pipeline + scoring can stay as-is. |
| `parsers.py` | **Keep** and extend | Cell parsers for Wikipedia tables can be reused for GSMArena/DeviceSpecification spec tables. Add new parsers for benchmark data and vendor API JSON responses. |

### New Modules Needed

```
src/soc_db/
  dedup/                   # NEW — Deduplication engine
    __init__.py
    engine.py              # DedupEngine — orchestrates multi-source merge
    matchers.py            # Base Matcher + vendor-specific implementations
    conflicts.py           # Conflict detection and resolution strategies
  scrapers/                # NEW — Pull scraper modules into subdirectory
    __init__.py
    base.py                # BaseScraper class with shared httpx/tenacity setup
    gsmarena.py            # GSMArena scraper
    devicespecs.py         # DeviceSpecifications scraper
    geekbench.py           # Geekbench benchmark scraper
    antutu.py              # Antutu benchmark scraper
    qualcomm.py            # Qualcomm Developer Network scraper
    mediatek.py            # MediaTek product page scraper
  pipeline.py              # NEW — Orchestrates all scrapers -> dedup -> enrich -> write
  validate.py              # NEW — Cross-source validation and quality checks
```

---

## Architecture: DedupEngine Design

```
                      ┌──────────────────┐
                      │  Pipeline         │
                      │  (orchestrator)   │
                      └────────┬─────────┘
                               │
               ┌───────────────┼───────────────┐
               ▼               ▼               ▼
        ┌──────────┐    ┌──────────┐    ┌──────────┐
        │Scraper A │    │Scraper B │    │Scraper C │
        │(GSMArena)│    │(Geekbench)│   │(Wikipedia)│
        └────┬─────┘    └────┬─────┘    └────┬─────┘
             │                │               │
             ▼                ▼               ▼
        ┌─────────────────────────────────────────┐
        │           DedupEngine                    │
        │                                          │
        │  1. Extract vendor + model from each     │
        │     source using vendor-specific matcher │
        │  2. Index by (vendor, model_number)      │
        │  3. Merge fields with conflict resolution│
        │  4. Track source provenance per field    │
        └────────────────┬────────────────────────┘
                         │
                         ▼
        ┌─────────────────────────────────────────┐
        │        enrich_one() (existing)           │
        └────────────────┬────────────────────────┘
                         │
                         ▼
        ┌─────────────────────────────────────────┐
        │   write_vendor_file() (existing)         │
        └─────────────────────────────────────────┘
```

### Matcher Strategy Per Vendor

| Vendor | Primary Key | Matcher Strategy |
|--------|-------------|------------------|
| Qualcomm | SM/SDM/MSM/APQ/SC/QCS model numbers | Regex `\b(SM\d{3,}|SDM\d{3,}|MSM\d{3,}|APQ\d{3,})\b` |
| MediaTek | MT followed by 4+ digits | Regex `\b(MT\d{4,})\b` |
| Apple | APL/T-number | Known mapping dict (existing) |
| Samsung | Exynos number | Regex `\b(Exynos\s*\d{4,})\b` |
| HiSilicon | Kirin number | Regex `\b(Kirin\s*\d{3,})\b` |
| Google | GS number | Regex `\b(GS\d{3})\b` |
| Rockchip | RK number | Regex `\b(RK\d{3,})\b` |
| Others | Name-based matching | Fuzzy match on name (rapidfuzz, threshold 0.85) + year proximity filter |

### Conflict Resolution Rules

When two sources provide different values for the same field:

1. **Official source wins** — Qualcomm Developer Network > GSMArena > Wikipedia
2. **More complete record wins** — compare `completeness` score
3. **Freshness wins** — prefer newer `updated` date
4. **Specificity wins** — prefer values with units/numbers over generic strings

The engine logs all conflicts to a report for manual review, rather than silently overwriting.

---

## Updated `pyproject.toml` Dependencies

```toml
dependencies = [
    # Existing (v2.1) — unchanged
    "beautifulsoup4>=4.12",
    "lxml>=5.1",
    "requests>=2.31",
    "aiosqlite>=0.20",
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
    "pydantic>=2.5",
    "pydantic-settings>=2.2",
    "redis[hiredis]>=5.0,<8.0",
    "opentelemetry-api>=1.25",
    "opentelemetry-sdk>=1.25",
    "opentelemetry-instrumentation-fastapi>=0.45b",
    "prometheus-client>=0.20",
    "SPARQLWrapper>=2.0",

    # New (v3.0 data collection)
    "httpx>=0.28",
    "curl-cffi>=0.15",
    "selectolax>=0.4",
    "tenacity>=9.0",
    "jmespath>=1.1",
    "rapidfuzz>=3.6",
]

[project.optional-dependencies]
dev = [
    # Existing dev deps — unchanged
    "pytest>=8.0",
    "pytest-asyncio>=0.21",
    "pytest-cov>=5.0",
    "ruff>=0.4",
    "mypy>=1.8",
    "pre-commit>=3.6",
    "bandit>=1.7",
    "safety>=3.0",
    "httpx>=0.27",
    "hypothesis>=6.100",
    "pytest-benchmark>=4.0",

    # New (v3.0)
    "pandas>=2.2",
    "GitPython>=3.1",
]
```

---

## Installation Commands

```bash
# Core scraping additions
pip install httpx>=0.28 curl-cffi>=0.15 selectolax>=0.4 tenacity>=9.0 jmespath>=1.1 rapidfuzz>=3.6

# Dev additions
pip install pandas>=2.2 GitPython>=3.1
```

---

## Configuration Additions

```python
# New settings in config.py for v3.0
scrape_rate_limit: float = 1.0       # Seconds between requests (comply with robots.txt)
scrape_cache_ttl: int = 86400 * 7    # Cache fresh scrapes for 7 days
scrape_user_agent_rotate: bool = True  # Rotate user agents per request
dedup_conflict_strategy: str = "official_wins"  # official|completeness|freshness|report
source_priority: list[str] = [        # Official sources first
    "qualcomm", "mediatek", "apple", "samsung",
    "gsmarena", "devicespecs", "wikipedia", "wikidata",
    "linux_dt", "geekbench", "antutu"
]
benchmark_cache_ttl: int = 86400 * 30  # Benchmark data changes slowly
```

---

## Sources

- httpx v0.28.1: https://pypi.org/project/httpx/ (HIGH — Dec 2024 release)
- curl-cffi v0.15.0: https://pypi.org/project/curl-cffi/ (HIGH — Apr 2026, latest stable)
- selectolax v0.4.11: https://pypi.org/project/selectolax/ (HIGH — Jul 2026, Lexbor backend)
- tenacity v9.1.4: https://pypi.org/project/tenacity/ (HIGH — Feb 2026)
- jmespath v1.1.0: https://pypi.org/project/jmespath/ (HIGH — Jan 2026)
- rapidfuzz v3.6+: https://pypi.org/project/rapidfuzz/ (HIGH — actively maintained)
- GitPython v3.1.52: https://pypi.org/project/GitPython/ (HIGH — Jul 2026, maintenance mode noted)
- Pandas v2.2+: https://pypi.org/project/pandas/ (HIGH — stable)
- Existing scraper architecture: codebase analysis of `scraper_wikipedia.py`, `scraper_apple.py`, `common.py` (HIGH)
- GSMArena scraping analysis: site structure observed via page fetch (MEDIUM — no official API)
- Geekbench Browser: 403 observed on direct fetch, confirms anti-bot measures (HIGH)
- Model number patterns: `parsers.py` existing extraction patterns (HIGH)
