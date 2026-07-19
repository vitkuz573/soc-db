# Code Conventions

Last updated: 2026-07-19

## Python Style

- **Line length**: 160 characters (`pyproject.toml:73`)
- **Indentation**: 4 spaces (tabs only in `Makefile`)
- **Quotes**: Double quotes preferred (consistent across codebase)
- **Type hints**: Used throughout; `from __future__ import annotations` in newer files
- **Target version**: Python 3.12+ (uses `|` union syntax, `dict[str, Any]`, etc.)

## Ruff Configuration

**Selected rules** (`pyproject.toml:77`):
- `E` — pycodestyle errors
- `F` — pyflakes
- `I` — import sorting
- `N` — naming
- `W` — pycodestyle warnings
- `UP` — pyupgrade (modern syntax)
- `B` — bugbear
- `SIM` — simplify
- `ARG` — unused arguments
- `C4` — comprehensions
- `ISC` — implicit string concat
- `PIE` — pie
- `T20` — print statements
- `RET` — return
- `SLF` — self/class attribute access
- `SLOT` — slots
- `YTT` — year 2038
- `ASYNC` — async
- `FURB` — refurb

**Per-file ignores**: `tests/*` allows `S101` (assert), `D*` (docstrings), `T201` (print); `cli.py` allows `T201`, `E501`; `scraper_*.py` and `parsers.py` have specific overrides

## Naming

| Construct | Convention | Example |
|---|---|---|
| Modules | `snake_case` | `common.py`, `log_config.py` |
| Classes | `PascalCase` | `Chip`, `Settings`, `JSONFormatter` |
| Functions | `snake_case` | `enrich_one()`, `extract_model()` |
| Private helpers | `_leading_underscore` | `_has()`, `_match_existing()` |
| Constants | `UPPER_CASE` | `DATA_DIR`, `VENDOR_FILES`, `FIELD_GROUPS` |
| CLI functions | `cmd_*` prefix | `cmd_list`, `cmd_query`, `cmd_show` |
| Test classes | `Test*` prefix | `TestClean`, `TestEnrichOne` |
| Test functions | `test_*` prefix | `test_basic_fill`, `test_qualcomm_sm8550` |

## Docstrings

- **Format**: Google-style with `Args:` and `Returns:` sections
- **Required**: All public functions and methods have docstrings
- **Module-level**: Triple-quoted docstring at top of every file
- **CLI functions**: Include subcommand description and args

Example (`src/soc_db/common.py:23-48`):
```python
def fetch(url: str, ttl: int = 86400) -> str:
    """Fetch a URL with caching.

    Args:
        url: The URL to fetch.
        ttl: Time-to-live in seconds for the cache (default 86400).

    Returns:
        The response body as a UTF-8 decoded string.
    """
```

## Error Handling

- **CLI**: Exit with `sys.exit(1)` and print to stderr on not-found (`cli.py:167`)
- **API**: `HTTPException` with structured `{"error": ..., "detail": ...}` responses
- **Global exception handler**: Catches unhandled exceptions, returns 500 with detail only in DEBUG mode (`api/main.py:104-110`)
- **Validation errors**: Return 422 with error details (`api/main.py:96-101`)
- **Logging**: All exceptions are logged via `logger.exception()` before re-raising
- **No blanket excepts**: `# nosec` comments on intentional bare `urlopen` call

## Logging

- **Framework**: stdlib `logging` with structured JSON output
- **Format**: JSON to stderr by default (`SOC_DB_LOG_FORMAT=json`)
- **Level**: Configurable via `SOC_DB_LOG_LEVEL` (default: `WARNING`)
- **Custom formatter**: `JSONFormatter` in `log_config.py` adds timestamp, level, logger, module, function, line, and extra fields
- **Extra context**: Request logging includes `request_id`, `method`, `path`, `query`, `status`, `duration_ms`, `client_host`, `user_agent`
- **Uvicorn**: Access logs suppressed (`WARNING` level) to avoid double-logging

## Imports

- **Standard library first**, then third-party, then local (`isort` via ruff)
- `from __future__ import annotations` in newer/migrated files
- Lazy imports within functions for CLI (`argparse` imported inside `main()`)
- Lazy imports for heavy modules (`csv`, `io` imported inside command handlers)

## CLI Design

- Single entry point `soc-db` via `[project.scripts]` in `pyproject.toml`
- Subcommands: `list`, `query`, `show`, `stats`, `enrich`
- `argparse` with `add_subparsers`
- Shared `--json`, `--csv` flags for machine-readable output
- Default output is formatted ASCII tables via `fmt_table()`

## API Design

- Prefix: `/v1/` for all data endpoints
- Pagination: `limit` (default 100, max 10000) + `offset`
- Filtering: Query parameters (`vendor`, `arch`, `gpu`, `year`, `min_cores`, `min_completeness`)
- Search: `q` parameter with inverted-index full-text search
- Sorting: `sort` + `order` (asc/desc)
- Field projection: `fields` comma-separated whitelist
- CORS: Wide open (`allow_origins: ["*"]`)
- Auth: Optional X-API-Key header

## Pattern: Enrichment Pipeline

The `enrich_one()` function is a sequential pipeline of ~12 stages:

1. Cleanup (strip editorial suffixes)
2. Model fallback
3. Memory clock/bus inference
4. Architecture from VENDOR_KNOWLEDGE
5. Process node (vendor map → year heuristic)
6. GPU (vendor map → vendor default → year default)
7. Year inference (vendor-specific regex patterns)
8. NPU inference
9. Modem inference
10. Wi-Fi / Bluetooth (year-based)
11. Storage type (year-based)
12. Aliases, completeness score, sources

Each stage checks `if not chip.get("field"):` before filling, preserving existing data.

## Pattern: Dedup/Merge in Scrapers

`write_vendor_file()` in `src/soc_db/common.py`:
- Loads existing vendor JSON
- Matches new chips by ID → model → name (case-insensitive)
- Updates existing records (never overwrites non-empty values)
- Adds genuinely new records
- Prunes stale entries (completeness < 0.28 or GPU-only entries)
- Runs enrichment before writing

## Testing Conventions

- Test classes: `class TestFeature:` (PascalCase)
- Test methods: `def test_scenario(self):` (snake_case)
- Fixtures in `conftest.py`: `sample_chip`, `minimal_chip`, `temp_data_dir`
- Parametrized tests: `@pytest.mark.parametrize` for year inference (~100 cases)
- Property tests: Hypothesis `@given` strategies for fuzz testing
- Mock external calls: `unittest.mock.patch` for `fetch()`, `urlopen`
- Async tests: `@pytest.mark.asyncio` with `httpx.AsyncClient`
