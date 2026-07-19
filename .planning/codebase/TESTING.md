# Testing

Last updated: 2026-07-19

## Test Framework

- **pytest** >=8.0 — primary test framework
- **pytest-asyncio** — async test support (asyncio_mode = "auto")
- **pytest-cov** — coverage reporting (fail_under: 60%)
- **pytest-benchmark** — performance benchmarks
- **hypothesis** — property-based testing
- **httpx** — async HTTP client for API integration tests
- **unittest.mock** — mocking for external calls

## Running Tests

```bash
make test              # pytest with verbose output
make test-cov          # pytest with coverage report
make validate          # JSON Schema validation of all data files
make ci                # lint → typecheck → security → test → validate
```

## Test Structure

```
tests/
├── conftest.py               # Shared fixtures
├── validate.py                # Data validation script (not pytest)
├── unit/                      # Unit tests
│   ├── test_common.py         # common.py functions (1279+ lines, largest test file)
│   ├── test_cli.py            # CLI smoke tests
│   ├── test_config.py         # Config tests
│   ├── test_models.py         # Pydantic model tests
│   └── test_parsers.py        # Wikipedia parser tests
├── integration/               # Integration tests
│   ├── test_api.py            # FastAPI endpoint tests (201 lines)
│   └── test_cli.py            # CLI integration tests
└── property/                  # Property-based tests
    └── test_enrich_one.py     # Hypothesis tests for enrich_one
└── benchmark/                 # Benchmark tests
    └── test_enrich_one.py     # enrich_one performance benchmarks
```

## Test Categories

### Unit Tests (`tests/unit/`)

**test_common.py** — Most comprehensive test file:
- `TestClean` — 8 tests for `clean()` function
- `TestSlug` — 6 tests for `slug()` function
- `TestExtractInt` — 6 tests for `extract_int()`
- `TestExtractFreq` — 7 tests for `extract_freq()`
- `TestExtractProcess` — 3 tests for `extract_process()`
- `TestExtractModel` — 6 tests for `extract_model()`
- `TestHas` — 5 tests for `_has()`
- `TestMergeChips` — 5 tests for `merge_chips()`
- `TestMatchExisting` — 5 tests for `_match_existing()`
- `TestFetch` — 2 tests for `fetch()` (cached + network)
- `TestEnrichOne` — 44 tests covering specific chip scenarios
- `TestEnrichAll` — 2 tests for batch enrichment
- `TestYearInference` — ~100 parametrized tests + 80+ individual year tests

**test_cli.py** — Subprocess-based smoke tests (help, list command)

**test_config.py** — Settings class tests

**test_models.py** — Pydantic model validation tests

**test_parsers.py** — Wikipedia table cell parser tests

### Integration Tests (`tests/integration/`)

**test_api.py** (201 lines):
- `test_root` — root endpoint metadata
- `test_chips_list` — chip listing + pagination
- `test_chip_by_id` — single chip lookup (sm8550_ac)
- `test_chip_not_found` — 404 handling
- `test_stats` — database statistics
- `test_schema` — JSON Schema endpoint
- `test_export_json` — full export
- `test_health` / `test_health_not_ready` — liveness probe
- `test_metrics` — metrics endpoint
- `test_x_request_id` — request ID header propagation
- `test_rate_limit_jail` — rate limiter enforcement
- `test_search_qualcomm` — full-text search
- `test_api_key_auth` — authentication middleware
- `test_validation_error` — 422 validation
- `test_404_format` — error response format

**test_cli.py** — End-to-end CLI integration tests

### Property-Based Tests (`tests/property/`)

**test_enrich_one.py** (60 lines):
- Uses Hypothesis `@given(chip_dict())` strategy
- `test_always_has_input_keys` — id/name/vendor always preserved
- `test_preserves_valid_year` — valid years unchanged
- `test_architecture_from_vendor_knowledge` — known vendors get architecture
- `test_memory_type_is_lpddr5_or_newer` — year-appropriate memory
- `test_no_exceptions` — never crashes on random input
- 100 examples per test

### Benchmark Tests (`tests/benchmark/`)

**test_enrich_one.py** (32 lines):
- `test_enrich_one_throughput` — runs `enrich_one()` on all chips
- `test_enrich_one_single` — single-chip benchmark

### Data Validation (`tests/validate.py`)

Not pytest — standalone script run via `make validate`:
- Validates JSON Schema syntax
- Checks every data file: required fields (id, name, vendor), unique IDs, type correctness
- Rebuilds `data/index.json` with vendor counts and completeness
- Exit code 1 on any failure

## Coverage

- **Target**: 60% line coverage minimum (`fail_under = 60`)
- **Source**: `soc_db` package only
- **Excluded**: `tests/*`, `scraper_*.py`, `parsers.py`, `__main__.py`, `cli.py`
- **Command**: `make test-cov`

## Fixtures (`tests/conftest.py`)

```python
@pytest.fixture
def sample_chip():          # Full Qualcomm Snapdragon 865 chip dict
    return {
        "id": "sm8250_kona",
        "name": "Snapdragon 865",
        "vendor": "Qualcomm",
        "model": "SM8250",
        "cores": 8,
        "architecture": "ARMv8.2-A",
        "gpu": "Adreno 650",
        "process_nm": 7,
        "year": 2020,
        "completeness": 0.85,
    }

@pytest.fixture
def minimal_chip():          # Minimal chip dict (3 required fields)
    return {"id": "test123", "name": "Test SoC", "vendor": "TestVendor"}

@pytest.fixture
def temp_data_dir():         # Temporary directory for data file tests
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)
```

## Key Test Patterns

1. **Parametrized year inference** — 100+ `@pytest.mark.parametrize` cases testing all vendor year-inference logic
2. **Mock external HTTP** — `unittest.mock.patch('soc_db.common.urlopen')` for fetch tests
3. **Async API tests** — `httpx.AsyncClient` with `ASGITransport` for FastAPI tests
4. **Hypothesis fuzzing** — Random chip dicts with `@given` to find edge cases
5. **Benchmark realism** — Uses real chip data from `data/*.json` for benchmarks

## CI Integration

`.appveyor.yml` runs:
1. `make ci` (lint → typecheck → test → validate)
2. `make security` (bandit)
3. `pre-commit run --all-files` (non-blocking)

Test matrix: Python 3.12, 3.13 (required) and 3.14 (allowed failure).
