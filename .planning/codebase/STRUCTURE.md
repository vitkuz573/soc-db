# Directory Structure

Last updated: 2026-07-19

```
soc-db/
├── pyproject.toml              # Project metadata, tooling config, dependencies
├── makefile                    # Task runner (install, lint, test, scrape, server, etc.)
├── README.md                   # Project docs with examples
├── ROADMAP.md                  # Planned features by version
├── CHANGELOG.md                # Release history
├── CONTRIBUTING.md             # Contribution guide
├── CONTRIBUTORS.md             # List of contributors
├── MIGRATION.md                # Data migration notes
├── SECURITY.md                 # Security policy
├── CODE_OF_CONDUCT.md          # Code of conduct
├── LICENSE                     # MIT license
├── .editorconfig               # Editor settings
├── .gitignore                  # Git ignore patterns
├── .gitattributes              # Git attributes
├── .dockerignore               # Docker build exclusions
├── .pre-commit-config.yaml     # Pre-commit hooks
├── .appveyor.yml               # Appveyor CI config
│
├── src/                        # Python package (pip-installable)
│   └── soc_db/
│       ├── __init__.py         # Package init, __version__
│       ├── __main__.py         # python -m soc_db entry
│       ├── cli.py              # CLI argument parser + command handlers (276 lines)
│       ├── common.py           # Shared utilities, enrichment, VENDOR_KNOWLEDGE (1482+ lines)
│       ├── config.py           # Pydantic-settings configuration (40 lines)
│       ├── log_config.py       # Structured JSON logging (107 lines)
│       ├── models.py           # Pydantic data models (142 lines)
│       ├── parsers.py          # Wikipedia cell parsers (264 lines)
│       ├── scraper_wikipedia.py # Wikipedia scraper (511 lines)
│       ├── scraper_apple.py    # Apple Silicon scraper
│       └── py.typed            # PEP 561 marker
│
├── api/                        # FastAPI REST server
│   ├── main.py                 # FastAPI app + routes (477 lines)
│   └── requirements.txt        # API-specific deps
│
├── data/                       # JSON data files (one per vendor)
│   ├── index.json              # Auto-generated index
│   ├── qualcomm.json           # 262 chips
│   ├── mediatek.json           # 264 chips
│   ├── exynos.json             # 74 chips
│   ├── intel_atom.json         # 212 chips
│   ├── kirin.json              # 61 chips
│   ├── apple.json              # 17 chips
│   ├── rockchip.json           # 29 chips
│   ├── allwinner.json          # 24 chips
│   ├── amlogic.json            # 24 chips
│   ├── nvidia.json             # 19 chips
│   ├── ti_omap.json            # 18 chips
│   ├── nxp_imx.json            # 6 chips
│   ├── ingenic.json            # 10 chips
│   └── ... (32 more vendor files)
│
├── schema/
│   └── chip-schema.json        # JSON Schema draft-07 (366 lines)
│
├── tests/                      # Test suite
│   ├── conftest.py             # Shared fixtures (sample_chip, minimal_chip, temp_data_dir)
│   ├── validate.py             # Data validation + index builder (127 lines)
│   ├── unit/
│   │   ├── test_common.py      # Unit tests for common.py (1279+ lines)
│   │   ├── test_cli.py         # CLI smoke tests
│   │   ├── test_config.py      # Config tests
│   │   ├── test_models.py      # Model tests
│   │   └── test_parsers.py     # Parser tests
│   ├── integration/
│   │   ├── test_api.py         # FastAPI integration tests (201 lines)
│   │   └── test_cli.py         # CLI integration tests
│   ├── property/
│   │   └── test_enrich_one.py  # Hypothesis property-based tests (60 lines)
│   └── benchmark/
│       └── test_enrich_one.py  # pytest-benchmark tests (32 lines)
│
├── scripts/                    # Legacy runner scripts
│   ├── pipeline.py             # Full automation pipeline
│   ├── scraper_wikipedia.py    # Legacy Wikipedia scraper
│   ├── scraper_apple.py        # Legacy Apple scraper
│   ├── scraper_wikidata.py     # Wikidata scraper
│   ├── scraper_wikidata_sparql.py # SPARQL-based scraper
│   ├── scraper_linux_dt.py     # Linux DT scraper
│   ├── common.py               # Shared script utilities
│   ├── parsers.py              # Legacy parsers
│   ├── migrate.py              # Data migration tool
│   ├── extract_wikitables.py   # Wiki table extraction
│   ├── enrich_from_dts.py      # DTS enrichment
│   └── run_all.sh              # Run-all script
│
├── docs/                       # Documentation site
│   ├── api.md                  # API documentation
│   ├── openapi.json            # OpenAPI specification
│   ├── swagger.html            # Swagger UI
│   ├── logo-dark.svg           # Dark logo
│   ├── logo-light.svg          # Light logo
│   ├── contributing.md         # Contributing docs
│   └── adr/                    # Architecture Decision Records
│       ├── 0001-record-architecture-decisions.md
│       ├── 0002-python-package-structure.md
│       └── 0003-json-schema-and-enrichment.md
│
├── deploy/                     # Systemd deployment
│   ├── soc-db-update.service   # Oneshot service
│   └── soc-db-update.timer     # Periodic timer
│
├── bin/                        # Shell utilities
│   ├── soc-db                  # CLI wrapper
│   └── auto-deploy.sh          # Auto-deployment script
│
├── .github/                    # GitHub configuration
│   ├── FUNDING.yml
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── ISSUE_TEMPLATE/
│       ├── 01_bug_report.yml
│       ├── 02_feature_request.yml
│       ├── 03_data_issue.yml
│       └── config.yml
│
├── .benchmarks/                # pytest-benchmark artifacts
├── .hypothesis/                # Hypothesis test examples
├── .mypy_cache/                # mypy cache
├── .ruff_cache/                # ruff cache
├── .pytest_cache/              # pytest cache
├── .coverage                   # Coverage data
└── .venv/                      # Virtual environment (not committed)
```

## Naming Conventions

- **Python files**: `snake_case.py`
- **Directories**: `snake_case/`
- **Chip IDs**: `lowercase_underscore_separated` (e.g. `sm8250_kona`)
- **Data files**: `vendor_name.json` (e.g. `qualcomm.json`, `nxp_imx.json`)
- **Test files**: `test_<module>.py`
- **CLI commands**: lowercase short verbs (`list`, `query`, `show`, `stats`, `enrich`)
- **API endpoints**: `/v1/plural` (`/v1/chips`, `/v1/vendors`)
- **Environment variables**: `SOC_DB_UPPERCASE`

## Key File Locations

| What | Path |
|---|---|
| Package entry point | `src/soc_db/cli.py:main()` |
| Core enrichment logic | `src/soc_db/common.py` |
| Pydantic data models | `src/soc_db/models.py` |
| API server | `api/main.py` |
| JSON Schema | `schema/chip-schema.json` |
| All chip data | `data/*.json` |
| Auto-generated index | `data/index.json` |
| Wikipedia scrapers | `src/soc_db/scraper_wikipedia.py`, `src/soc_db/scraper_apple.py` |
| Legacy scripts | `scripts/*.py` |
| Unit tests | `tests/unit/test_*.py` |
| API integration tests | `tests/integration/test_api.py` |
| Property-based tests | `tests/property/test_enrich_one.py` |
| Benchmarks | `tests/benchmark/test_enrich_one.py` |
| Data validation | `tests/validate.py` |
| CI config | `.appveyor.yml` |
| Docker config | `Dockerfile`, `docker-compose.yml` |
| Make targets | `Makefile` |
| ADRs | `docs/adr/*.md` |
