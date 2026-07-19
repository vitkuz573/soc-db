# Technology Stack

Last updated: 2026-07-19

## Languages

- **Python 3.12+** — primary language (requires `>=3.12`, tested on 3.12–3.14)
- **JavaScript/HTML/CSS** — static web UI (`index.html`, `404.html`, `docs/swagger.html`)

## Runtime

- **CPython** — standard runtime
- **Docker** — multi-stage production container (`Dockerfile`)
- **Systemd timer** — auto-update deployment (`deploy/soc-db-update.{service,timer}`)

## Package Management

- **pip + setuptools** — build system (`pyproject.toml` with `[build-system] requires = ["setuptools>=75.0"]`)
- **`pip install -e .`** — editable development install
- **`requirements.txt`** — runtime deps (beautifulsoup4, lxml, requests, fastapi, uvicorn, pydantic)
- **`requirements-dev.txt`** / **`requirements-dev.lock`** — dev dependencies

## Core Dependencies

| Package | Version | Purpose |
|---|---|---|
| `fastapi` | >=0.110 | REST API framework (`api/main.py`) |
| `uvicorn[standard]` | >=0.29 | ASGI server |
| `pydantic` | >=2.5 | Data models (`src/soc_db/models.py`) |
| `pydantic-settings` | >=2.2 | Environment-based config (`src/soc_db/config.py`) |
| `beautifulsoup4` | >=4.12 | HTML parsing for Wikipedia scrapers |
| `lxml` | >=5.1 | XML/HTML parser backend for BeautifulSoup |
| `requests` | >=2.31 | HTTP client (used by legacy scripts) |

## Dev Dependencies

| Package | Version | Purpose |
|---|---|---|
| `pytest` | >=8.0 | Test framework |
| `pytest-asyncio` | >=0.21 | Async test support |
| `pytest-cov` | >=5.0 | Coverage reporting |
| `pytest-benchmark` | >=4.0 | Benchmark tests |
| `hypothesis` | >=6.100 | Property-based testing |
| `httpx` | >=0.27 | Async HTTP client for API tests |
| `ruff` | >=0.4 | Linter + formatter |
| `mypy` | >=1.8 | Static type checker |
| `pre-commit` | >=3.6 | Git hook automation |
| `bandit` | >=1.7 | Security linter |
| `safety` | >=3.0 | Dependency vulnerability scanner |

## Key Libraries (stdlib)

- `argparse` — CLI argument parsing (`src/soc_db/cli.py`)
- `json` — data serialization (all data files are JSON)
- `hashlib` — URL cache key generation
- `re` — extensive regex usage for year/model extraction
- `collections.defaultdict` — vendor aggregation, rate-limiting
- `pathlib.Path` — filesystem operations throughout
- `urllib.request` — HTTP fetch for scrapers (no `requests` in core lib)
- `asyncio` — async server lifecycle
- `gzip` — compressed export endpoint
- `csv` — CSV export endpoint + CLI
- `signal` — graceful shutdown
- `uuid` — request ID generation
- `logging` + `logging.config` — structured logging

## Infrastructure & CI

- **Appveyor** — CI (`master` branch, matrix: 3.12, 3.13, 3.14)
- **pre-commit** — git hooks (ruff lint, ruff-format, mypy, JSON/YAML check, trailing whitespace, merge-conflict, private-key detection)
- **Docker Compose** — local deployment with healthcheck
- **Makefile** — task runner (install, lint, typecheck, test, validate, scrape, server, docker-build, release)
- **GitHub Pages** — documentation site + Swagger UI
- **GitHub Issues/PRs** — templates in `.github/`

## Configuration

- `.editorconfig` — indentation: 4 spaces (Python), 2 spaces (YAML/JS/HTML), tabs (Makefile)
- `pyproject.toml` — ruff config (line-length 160, target py312), mypy strict config, pytest config, coverage config
- `.pre-commit-config.yaml` — pre-commit hook definitions
- `.gitignore` — Python/IDE/OS artifacts
- `.dockerignore` — Docker build context exclusions
- `SOC_DB_*` env vars — runtime config (`src/soc_db/config.py`)

## Version

Current: `2.1.0-dev` (in `pyproject.toml` and `src/soc_db/__init__.py`)
