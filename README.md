# SOC-DB

Enterprise-grade SoC / CPU identifier database.

- **1171+ chips** across 14 vendors
- JSON Schema validated
- GitHub Pages frontend with search, filter, sort, and detailed chip view
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
├── tests/            # Test suite
│   ├── unit/             # pytest unit tests
│   └── validate.py       # Data validation script
├── schema/           # JSON Schema
├── scripts/          # Legacy runner scripts (backward compat)
├── deploy/           # Systemd timer for auto-update
├── docs/             # Documentation
├── .github/          # CI/CD pipelines
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

## Development

```bash
make install-dev     # Install dev dependencies + pre-commit
make lint            # Ruff lint + format check
make typecheck       # mypy type checking
make test            # Run tests
make test-cov        # Test with coverage
make ci              # Full CI pipeline locally
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
| Qualcomm | `data/qualcomm.json` | 299 | List of Snapdragon processors |
| MediaTek | `data/mediatek.json` | 315 | List of MediaTek processors |
| Samsung | `data/exynos.json` | 98 | Exynos page |
| HiSilicon | `data/kirin.json` | 95 | HiSilicon page |
| Google | `data/tensor.json` | 12 | Google Tensor page |
| Apple | `data/apple.json` | 17 | Apple A-series + M-series |
| Rockchip | `data/rockchip.json` | 29 | Rockchip page |
| Allwinner | `data/allwinner.json` | 29 | Allwinner Technology page |
| Amlogic | `data/amlogic.json` | 16 | Amlogic page (transposed tables) |
| Nvidia | `data/nvidia.json` | 14 | Tegra page |
| TI OMAP | `data/ti_omap.json` | 16 | OMAP page |
| Intel Atom | `data/intel_atom.json` | 212 | List of Intel Atom processors |
| Ingenic | `data/ingenic.json` | 13 | Ingenic page |
| NXP i.MX | `data/nxp_imx.json` | 6 | NXP i.MX page |

Run `make scrape` to refresh all data from Wikipedia.

## Enterprise Features

- **Structured logging** — all `print()` replaced with `logging` calls
- **Type checking** — mypy configuration in `pyproject.toml`
- **Linting** — Ruff with comprehensive ruleset
- **Formatting** — Ruff auto-formatter
- **Testing** — pytest with coverage
- **CI/CD** — GitHub Actions: lint, typecheck, test, auto-scrape
- **Pre-commit hooks** — enforce quality gates before every commit
- **Multi-stage Docker build** — smaller, more secure production image
- **Installable package** — `pip install -e .` for `soc-db` CLI

## License

MIT

## Links

- **Web UI**: https://vitkuz573.github.io/soc-db/
- **Repository**: https://github.com/vitkuz573/soc-db
- **API Docs**: https://vitkuz573.github.io/soc-db/docs/api.html
