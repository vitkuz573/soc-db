# Technical Concerns & Technical Debt

Last updated: 2026-07-19

## Known Technical Debt

### 1. Year Inference — Monolithic Regex in `enrich_one()`
- **Location**: `src/soc_db/common.py:799-1328`
- **Issue**: The year-inference logic is a giant chain of ~40 `if/elif` regex blocks within a single function. This is fragile, hard to test in isolation, and has overlapping patterns that can produce incorrect results.
- **Impact**: Year inference errors could propagate to all derived fields (process node, memory type, modem, Wi-Fi).
- **Suggestion**: Extract a dedicated `infer_year(chip) -> int | None` function with a registry of per-vendor strategies.

### 2. VENDOR_KNOWLEDGE — Hardcoded Maps
- **Location**: `src/soc_db/common.py:392-702`
- **Issue**: Process maps, GPU maps, and architecture defaults are hardcoded for 7 vendors. Any new chip release requires a code change.
- **Impact**: Stale data — e.g. the most recent Qualcomm GPU map entry is `qcm6490` (Adreno 643), missing newer chips like SM8750.
- **Suggestion**: Consider a data-driven approach or automated source for vendor knowledge.

### 3. Scripts/ Directory — Legacy Code
- **Location**: `scripts/` (13 files)
- **Issue**: Contains deprecated duplicate implementations (`scripts/scraper_wikipedia.py`, `scripts/parsers.py`, `scripts/common.py`) that overlap with `src/soc_db/`. These exist as standalone runner scripts and are not maintained to the same quality standard.
- **Impact**: Confusion about which code is authoritative. `scripts/` is excluded from pre-commit.
- **Suggestion**: Deprecate formally, or migrate scripts to use `src/soc_db` as import.

### 4. Ruff Per-File Ignores
- **Location**: `pyproject.toml:79-87`
- **Issue**: Several files have broad ruff exceptions:
  - `cli.py` — allows `T201` (print), `E501` (line length), `C401`
  - `parsers.py` — allows `N806` (non-lowercase variable), `E501`, `F841` (unused variable)
  - `scraper_*.py` — allows various rules
- **Impact**: These files are effectively not linted, hiding quality issues.
- **Suggestion**: Fix violations and remove per-file ignores.

### 5. mypy Exemptions
- **Location**: `pyproject.toml:104-106`
- **Issue**: `scripts.*`, `tests.*`, `api.*`, `bin.*`, `soc_db.parsers`, `soc_db.scraper_*` are all `ignore_errors = true`
- **Impact**: Type errors in these files go undetected.
- **Suggestion**: Gradual typing rollout with increasing strictness.

### 6. `# nosec` Comments
- **Location**: `src/soc_db/common.py:44`, `src/soc_db/config.py:25`
- **Issue**: `urlopen(req, timeout=30)  # nosec` and `bind 0.0.0.0  # nosec` bypass bandit security checks.
- **Impact**: While justified (controlled URLs, containerized deployment), these bypasses should be documented and periodically reviewed.

### 7. Deprecated `requests` Dependency
- **Location**: `pyproject.toml:33` (dependency), `requirements.txt:4`
- **Issue**: The `requests` library is listed as a dependency but is not used in the core library. `src/soc_db/common.py` uses `urllib.request.urlopen()` directly. Only legacy scripts use `requests`.
- **Impact**: Unnecessary dependency in production installs.
- **Suggestion**: Move `requests` to dev dependencies or remove entirely.

## Security Concerns

### Low — Optional API Key
- API key authentication is optional and disabled by default (`api_key: str | None = None`)
- Running in production without authentication exposes the full chip database
- CORS is wide open (`allow_origins: ["*"]`)

### Low — Hardcoded Cache in /tmp
- `CACHE_DIR` defaults to `/tmp/soc-db-cache/` (world-readable)
- Cached Wikipedia pages could contain sensitive content if URLs change

### Informational — Bandit/Safety in CI
- `make security` runs bandit and safety scans
- Pre-commit hook detects private keys
- These are good practices already in place

## Performance Concerns

### 1. Synchronous File I/O in API
- **Issue**: `load_all()` reads all 44 JSON files synchronously on cache miss
- **Impact**: The first request after cache TTL expiry blocks the event loop (~300ms for 1000+ chips)
- **Suggestion**: Use `asyncio.to_thread()` (partially done — `load_all_async()` exists but `get_chips()` still calls sync `load_all()`)

### 2. In-Memory Data Store
- **Issue**: All chip data is loaded into memory (~5-10MB for 1000+ chips)
- **Impact**: Not suitable for large-scale deployments
- **Suggestion**: This is by design (flat JSON files), but worth documenting the scaling limit

### 3. Search Index Rebuild
- **Issue**: Full inverted index rebuild on every cache refresh
- **Impact**: Degrades during cache refresh; unnecessary if data hasn't changed

## Code Quality Concerns

### 1. Large Function Sizes
- `enrich_one()` — ~700 lines (the largest function in the codebase)
- `write_vendor_file()` — ~70 lines with complex merge logic
- `main()` in `cli.py` — ~50 lines of argument parser setup

### 2. Duplicated Logic
- `load_all()` is implemented identically in both `cli.py` and `api/main.py`
- `fmt_table()` in `cli.py` — ASCII table formatting could be shared
- Scraper logic exists in both `src/soc_db/` and `scripts/`

### 3. Parser Complexity
- `parsers.py` (264 lines) handles Wikipedia infobox parsing for many different table formats
- Layout changes on Wikipedia could silently break scrapers
- No validation that scraped data conforms to schema

## Test Quality Concerns

### 1. Missing Test Coverage
- `scraper_*.py` — covered by ruff/mypy exceptions and coverage exclusion
- `parsers.py` — covered but excluded from coverage
- `api/main.py` — some integration tests but limited coverage
- Error paths (network failures, malformed data) are lightly tested

### 2. Test Data Duplication
- Year inference tests in `test_common.py` contain ~180 individual test methods
- Many tests are trivial (`assert result is not None`) rather than exact-value assertions

## Documentation Gaps

- ADRs exist but cover only 3 decisions (out of date since the project has evolved)
- No API versioning strategy documented
- No documented procedure for adding a new vendor
- Scraper pipeline setup not fully documented
- Docker deployment requires manual systemd timer installation

## What's Working Well

- Comprehensive year-inference test coverage (100+ parametrized cases)
- Strong CI pipeline with linting, typechecking, tests, security scan
- Pre-commit hooks enforce code quality at commit time
- JSON Schema validation catches data format issues
- Property-based testing with Hypothesis catches edge cases
- Modular architecture with shared core library
- Good separation between library, API, and scripts
- Structured logging with request tracing
- Docker multi-stage build for minimal production images
- Architecture Decision Records document key design choices
