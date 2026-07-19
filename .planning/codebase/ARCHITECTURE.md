# Architecture

Last updated: 2026-07-19

## Architectural Pattern

**Modular monolith** with three main surfaces:
1. **CLI** — `argparse`-based command-line interface
2. **REST API** — FastAPI async server
3. **Scraper Pipeline** — batch data collection scripts

All three surfaces share the same core library (`src/soc_db/`) and the same data store (flat JSON files).

## Design Principles

From `README.md`:
1. **Data over code** — chip entries are self-describing; enrichment is convenience, not dependency
2. **One source of truth** — every chip lives in exactly one JSON file
3. **Validate everything** — schema validation on every change
4. **CLI == API** — same query engine powers both interfaces
5. **Gradual typing** — new code is fully typed
6. **Ship as a package** — `pip install soc-db` installs CLI, library, and data
7. **Human-first diffs** — JSON is formatted and sorted

## Layer Diagram

```
┌─────────────────────────────────────────────────┐
│                  CLI (argparse)                  │
│              src/soc_db/cli.py                   │
├─────────────────────────────────────────────────┤
│              REST API (FastAPI)                  │
│                 api/main.py                      │
├─────────────────────────────────────────────────┤
│           Scrapers / Pipeline (batch)            │
│  src/soc_db/scraper_*.py  |  scripts/*.py       │
├─────────────────────────────────────────────────┤
│           Core Library (src/soc_db/)             │
│  common.py  |  models.py  |  config.py          │
│  log_config.py  |  parsers.py                    │
├─────────────────────────────────────────────────┤
│              Data Store (JSON files)             │
│   data/*.json  |  schema/chip-schema.json        │
└─────────────────────────────────────────────────┘
```

## Data Flow

### CLI Query Flow
```
soc-db query --vendor Qualcomm --json
  → cli.py:main() → cmd_query()
  → cli.py:load_all() → data/*.json (reads all vendor files)
  → filter chain (vendor, arch, gpu, year, ...)
  → JSON/CSV/table output
```

### API Request Flow
```
GET /v1/chips?vendor=Qualcomm&limit=5
  → uvicorn → FastAPI routing → api/main.py:list_chips()
  → get_chips() → cache check (TTL 300s)
    → cache miss: load_all() → data/*.json → build search index
  → filter + paginate → Pydantic validation → JSONResponse
```

### Enrichment Flow
```
soc-db enrich  (or enrich_one() called programmatically)
  → common.py:enrich_all() → enrich_one() per chip
  → Pipeline: cleanup → model fallback → memory → process → GPU
    → year inference → Wi-Fi/BT → modem → NPU → storage
    → aliases → completeness score → sources
  → Writes back to data/*.json
```

### Scraper Flow
```
make scrape (or scripts/pipeline.py)
  → fetch() Wikipedia HTML → BeautifulSoup parse
  → table extraction via parsers.py (parse_cpu, parse_gpu, etc.)
  → slug() → write_vendor_file()
    → _match_existing() for merge/update logic
    → enrich_all() before write
  → tests/validate.py → schema validation + index rebuild
```

## Key Abstractions

### `soc_db.common`
- `fetch(url, ttl)` — cached HTTP GET
- `slug(name, model)` — URL-friendly ID generation
- `enrich_one(chip)` — single-chip enrichment pipeline
- `enrich_all(chips)` — batch enrichment
- `write_vendor_file(vendor, chips)` — merge+write scraped data
- `merge_chips(a, b)` — merge two chip dicts
- `_match_existing(chip, existing)` — dedup/match logic
- `VENDOR_KNOWLEDGE` — 7 vendors with hardcoded process maps, GPU maps, architecture
- `FIELD_GROUPS` — 12 field categories for completeness scoring
- `FIELD_WEIGHTS` — weighted completeness calculation

### `soc_db.parsers`
- `parse_cpu(text)` — infobox CPU field → architecture, cores, cluster config
- `parse_gpu(text)` — GPU model + clock
- `parse_memory(text)` — memory type + max
- `parse_process(text)` — process node
- `parse_modem(text)` — modem info
- Plus: `parse_display`, `parse_camera`, `parse_video`, `parse_connectivity`, `parse_cell`

### `soc_db.models`
- **Chip** — Pydantic model (95 fields) with validation
- **ChipListResponse**, **VendorResponse**, **StatsResponse**, **HealthResponse**, **MetricsResponse**, **ErrorResponse** — API response models
- **Rating**, **Benchmarks**, **Cache** — nested sub-models

### `soc_db.config`
- **Settings** — Pydantic-settings class (env prefix `SOC_DB_`)
- Paths, logging config, API host/port/CORS, rate limits, cache TTL

### `api.main`
- FastAPI app with `lifespan` handler
- API key middleware (optional)
- Rate-limiting middleware (sliding window, per-IP)
- Request logging middleware (X-Request-ID, duration, status)
- v1 router: `/vendors`, `/chips`, `/chips/{id}`, `/stats`, `/schema`, `/export/{fmt}`
- Infra endpoints: `/health`, `/metrics`

## Entry Points

| Entry Point | Invocation | File |
|---|---|---|
| CLI | `soc-db` (or `python -m soc_db`) | `src/soc_db/cli.py:main()` |
| API server | `uvicorn api.main:app` | `api/main.py` |
| Wikipedia scraper | `python scripts/scraper_wikipedia.py` | `src/soc_db/scraper_wikipedia.py` |
| Apple scraper | `python scripts/scraper_apple.py` | `src/soc_db/scraper_apple.py` |
| Pipeline | `python scripts/pipeline.py` | `scripts/pipeline.py` |
| Validation | `python tests/validate.py` | `tests/validate.py` |
| Data validation | `make validate` | `tests/validate.py` |

## Project Boundaries

- `src/soc_db/` — pip-installable Python package (the library)
- `api/` — FastAPI server (separate from the library, uses `soc_db.*` imports)
- `scripts/` — legacy/deprecated runner scripts
- `data/` — JSON data (one file per vendor, ~44 vendors)
- `schema/` — JSON Schema
- `tests/` — test suite
- `docs/` — documentation site, OpenAPI spec, Swagger UI
- `deploy/` — systemd units for auto-deployment
- `bin/` — `auto-deploy.sh` and `soc-db` shell wrapper
