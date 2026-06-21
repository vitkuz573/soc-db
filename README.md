# SOC-DB

[![GitHub Pages](https://img.shields.io/badge/Web%20UI-vitkuz573.github.io/soc--db-2ea44f)](https://vitkuz573.github.io/soc-db/)
[![Swagger](https://img.shields.io/badge/Swagger-API%20Docs-85EA2D)](https://vitkuz573.github.io/soc-db/docs/swagger.html)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12_|_3.13_|_3.14-blue?logo=python)](https://www.python.org/)
[![Ruff](https://img.shields.io/badge/code%20style-ruff-000000)](https://github.com/astral-sh/ruff)
[![Changelog](https://img.shields.io/badge/changelog-Keep%20a%20Changelog-E05735)](CHANGELOG.md)
[![Contributing](https://img.shields.io/badge/contributing-guide-2ea44f)](CONTRIBUTING.md)
[![Code of Conduct](https://img.shields.io/badge/code%20of%20conduct-Contributor%20Covenant-ff69b4)](CODE_OF_CONDUCT.md)
[![Repo](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fvitkuz573.github.io%2Fsoc-db%2Fdata%2Findex.json&query=%24.total&label=chips&color=success)](https://github.com/vitkuz573/soc-db)
[![Roadmap](https://img.shields.io/badge/roadmap-view-ff69b4)](ROADMAP.md)

Enterprise-grade SoC / CPU identifier database.

- **1096+ chips** across **23 vendors**
- JSON Schema validated
- [GitHub Pages frontend](https://vitkuz573.github.io/soc-db/) with search, filter, sort, and detailed chip view
- [Swagger API docs](https://vitkuz573.github.io/soc-db/docs/swagger.html)
- Automated Wikipedia scraper pipeline
- REST API (FastAPI) with JSON, CSV, and gzipped export

## Quick Start

```bash
pip install -e .
make scrape     # scrape Wikipedia data for all vendors
make validate   # validate all JSON files
make server     # start local web UI at http://localhost:8000/
soc-db stats    # CLI statistics
```

## Architecture

```
soc-db/
├── src/soc_db/       # Python package (installable)
│   ├── common.py         # Shared utilities, enrichment, vendor knowledge
│   ├── parsers.py        # Wikipedia cell parsers
│   ├── cli.py            # soc-db CLI (entry point)
│   ├── scraper_wikipedia.py
│   └── scraper_apple.py
├── api/              # FastAPI REST server
├── data/             # JSON data files (one per vendor)
├── tests/            # Test suite (pytest)
├── schema/           # JSON Schema
├── scripts/          # Legacy runner scripts
├── deploy/           # Systemd timer for auto-update
├── docs/             # OpenAPI spec + Swagger UI for GitHub Pages
└── pyproject.toml    # Project metadata & tooling config
```

## CLI Usage

```bash
soc-db list                    # List vendors
soc-db query --vendor qualcomm # Query Qualcomm chips
soc-db query --year 2024       # Chips from 2024
soc-db query --min-cores 8     # 8+ core chips
soc-db query --search "snapdragon 8 gen" --json
soc-db show sm8250_kona        # Show chip details
soc-db stats                   # Database statistics
soc-db enrich                  # Re-apply enrichment
```

## REST API

```bash
make server  # start at http://localhost:8000
curl http://localhost:8000/vendors
curl http://localhost:8000/chips?vendor=Qualcomm&limit=5
curl http://localhost:8000/chips/sm8250_kona
curl http://localhost:8000/stats
curl http://localhost:8000/export/csv
```

API docs: [Swagger UI](https://vitkuz573.github.io/soc-db/docs/swagger.html)

## Development

```bash
make install-dev     # Install dev dependencies + pre-commit
make lint            # Ruff lint + format check
make typecheck       # mypy type checking
make test            # Run tests
make test-cov        # Test with coverage
```

## Data Format

Each chip entry follows [JSON Schema](schema/chip-schema.json):

```json
{
  "id": "sm8250_kona",
  "name": "Snapdragon 870",
  "vendor": "Qualcomm",
  "codename": "kona",
  "model": "SM8250-AC",
  "cores": 8,
  "architecture": "ARMv8.2-A",
  "gpu": "Adreno 650",
  "process": "7nm",
  "year": 2021,
  "completeness": 0.723
}
```

## Scraping Pipeline

| Vendor | File | Chips | Source |
|--------|------|-------|--------|
| Qualcomm | `data/qualcomm.json` | 262 | List of Snapdragon processors |
| MediaTek | `data/mediatek.json` | 264 | List of MediaTek processors |
| Samsung | `data/exynos.json` | 74 | Exynos page |
| HiSilicon | `data/kirin.json` | 61 | HiSilicon page |
| Google | `data/tensor.json` | 5 | Google Tensor page |
| Apple | `data/apple.json` | 17 | Apple A-series + M-series |
| Rockchip | `data/rockchip.json` | 29 | Rockchip page |
| Allwinner | `data/allwinner.json` | 24 | Allwinner Technology page |
| Amlogic | `data/amlogic.json` | 24 | Amlogic page (transposed tables) |
| Nvidia | `data/nvidia.json` | 19 | Tegra page |
| TI OMAP | `data/ti_omap.json` | 18 | OMAP page |
| Intel Atom | `data/intel_atom.json` | 212 | List of Intel Atom processors |
| Ingenic | `data/ingenic.json` | 10 | Ingenic page |
| NXP i.MX | `data/nxp_imx.json` | 6 | NXP i.MX page |

Run `make scrape` to refresh all data from Wikipedia.

## Project Status

SOC-DB follows **semantic versioning** (see [CHANGELOG](CHANGELOG.md)).
Data format is versioned via `data/index.json` and may evolve with minor bumps.

## Community

- [Contributing Guide](CONTRIBUTING.md) — how to help
- [Code of Conduct](CODE_OF_CONDUCT.md) — community standards
- [Security Policy](SECURITY.md) — how to report vulnerabilities
- [Issue Templates](https://github.com/vitkuz573/soc-db/issues/new/choose) — bug, feature, data issue

## Enterprise Features

- **Structured logging** — all `print()` replaced with `logging` calls
- **Type checking** — mypy configuration in `pyproject.toml`
- **Linting** — Ruff with comprehensive ruleset
- **Formatting** — Ruff auto-formatter
- **Testing** — pytest with 46+ unit tests
- **Pre-commit hooks** — enforce quality gates before every commit
- **Multi-stage Docker build** — smaller, more secure production image
- **Installable package** — `pip install -e .` for `soc-db` CLI

## License

MIT — see [LICENSE](LICENSE).

## Links

- **Web UI**: https://vitkuz573.github.io/soc-db/
- **Swagger Docs**: https://vitkuz573.github.io/soc-db/docs/swagger.html
- **Repository**: https://github.com/vitkuz573/soc-db
- **API Docs**: https://vitkuz573.github.io/soc-db/docs/api.html
- **Changelog**: https://github.com/vitkuz573/soc-db/blob/main/CHANGELOG.md
