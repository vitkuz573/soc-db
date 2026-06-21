<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/vitkuz573/soc-db/main/docs/logo-dark.svg">
    <img alt="SOC-DB" src="https://raw.githubusercontent.com/vitkuz573/soc-db/main/docs/logo-light.svg" width="280">
  </picture>
</p>

<p align="center">
  <em>Enterprise-grade open database of SoC / CPU identifiers.</em>
</p>

<p align="center">
  <a href="https://pypi.org/project/soc-db/"><img src="https://img.shields.io/pypi/v/soc-db?label=version&logo=python" alt="PyPI"></a>
  <a href="https://pypi.org/project/soc-db/"><img src="https://img.shields.io/pypi/pyversions/soc-db?logo=python" alt="Python"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="License"></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/badge/code%20style-ruff-000000" alt="Ruff"></a>
  <a href="https://vitkuz573.github.io/soc-db/"><img src="https://img.shields.io/badge/web%20ui-github%20pages-2ea44f" alt="Web UI"></a>
  <a href="https://vitkuz573.github.io/soc-db/docs/swagger.html"><img src="https://img.shields.io/badge/api-swagger-85EA2D" alt="Swagger"></a>
  <a href="https://github.com/vitkuz573/soc-db"><img src="https://img.shields.io/github/stars/vitkuz573/soc-db?style=flat&label=stars&logo=github" alt="Stars"></a>
</p>

```python
>>> from soc_db.common import load_all, enrich_one
>>> chips = load_all()
>>> len(chips)
1096
>>> chips[0]
{'id': 'sm8250_kona', 'name': 'Snapdragon 870', 'vendor': 'Qualcomm', ...}
>>> enrich_one(chips[0])
{'id': 'sm8250_kona', 'memory_type': 'LPDDR5', 'process_nm': 7, 'completeness': 0.723, ...}
```

---

- **1096+ chips** across **23 vendors** — Qualcomm, MediaTek, Samsung, Apple, Intel, and more
- **JSON Schema validated** — every field is documented and checked
- **REST API + CLI** — query from the terminal or over HTTP
- **Web UI** at [vitkuz573.github.io/soc-db](https://vitkuz573.github.io/soc-db/) — search, filter, sort, drill into any chip
- **Wikipedia scraper pipeline** — semi-automated data collection
- **Type-safe, linted, tested** — `make ci` enforces quality before every commit

---

<details>
<summary><b>Table of Contents</b></summary>

- [Quick Start](#quick-start)
- [Features](#features)
- [Design Principles](#design-principles)
- [CLI Usage](#cli-usage)
- [REST API](#rest-api)
- [Data Format](#data-format)
- [Architecture](#architecture)
- [Development](#development)
- [Project Status](#project-status)
- [Contributing](#contributing)
- [License](#license)

</details>

---

## Quick Start

```bash
pip install soc-db          # or: pip install -e .
soc-db list                 # list all vendors and chip counts
soc-db query --year 2024    # chips released in 2024
soc-db stats                # database statistics
```

### Web UI

```bash
make server    # http://localhost:8000
```

Or visit the live instance: [vitkuz573.github.io/soc-db](https://vitkuz573.github.io/soc-db/)

---

## Features

- **Multi-source query** — filter by vendor, architecture, GPU, year, core count, clock speed, completeness, free-text search
- **Structured enrichment** — automatically infers memory type, process node, GPU, NPU, modem, Wi-Fi, Bluetooth, release year from model number
- **Multiple output formats** — JSON, CSV, gzipped JSON for the API; pretty-print or JSON for the CLI
- **Completeness scoring** — every chip has a weighted completeness metric (0–1) based on field coverage
- **CLI-first design** — `soc-db query --json | jq` pipelines naturally
- **Docker-ready** — multi-stage Dockerfile for production deployment
- **All data is JSON** — human-readable, diff-friendly, CI-friendly

---

## Design Principles

1. **Data over code.** A chip entry should be self-describing. The enrichment layer is a convenience, not a dependency.
2. **One source of truth.** Every chip lives in exactly one JSON file. The index is generated, not authored.
3. **Validate everything.** Schema validation runs on every change. If it doesn't validate, it doesn't ship.
4. **CLI == API.** The same query engine powers both `soc-db query` and the REST API. No duplication.
5. **Gradual typing.** New code is fully typed; legacy code is wrapped, not rewritten.
6. **Ship as a package.** `pip install soc-db` installs the CLI, the library, and all data.
7. **Human-first diffs.** JSON is formatted, sorted, and reviewed in pull requests — never minified or mangled.

---

## CLI Usage

```bash
# List all vendors
soc-db list
soc-db list --vendor qualcomm

# Query chips
soc-db query --arch ARMv8 --min-cores 8
soc-db query --vendor mediatek --year 2024 --json
soc-db query --search "snapdragon 8 gen" --csv --limit 20

# Drill into a chip
soc-db show sm8250_kona

# Database stats
soc-db stats
soc-db stats --json | jq '.total_chips'

# Re-apply enrichment to all data files
soc-db enrich
```

---

## REST API

| Endpoint | Description |
|---|---|
| `GET /vendors` | List all vendors |
| `GET /chips` | Query chips (supports `vendor`, `arch`, `gpu`, `year`, `min_cores`, `min_ghz`, `completeness`, `search`, `offset`, `limit`, `fields`) |
| `GET /chips/{id}` | Single chip by slug |
| `GET /stats` | Database statistics |
| `GET /export/csv` | Full database as CSV |
| `GET /export/json.gz` | Full database as gzipped JSON |

```bash
curl http://localhost:8000/vendors
curl http://localhost:8000/chips?vendor=Qualcomm&limit=5
curl http://localhost:8000/chips/sm8250_kona
```

Full API docs: [Swagger UI](https://vitkuz573.github.io/soc-db/docs/swagger.html)

---

## Data Format

Every chip entry follows the [JSON Schema](schema/chip-schema.json):

```json
{
  "id": "sm8250_kona",
  "name": "Snapdragon 870",
  "vendor": "Qualcomm",
  "model": "SM8250-AC",
  "architecture": "ARMv8.2-A",
  "cores": 8,
  "gpu": "Adreno 650",
  "process": "7nm",
  "process_nm": 7,
  "memory_type": "LPDDR5",
  "memory_clock": 3200,
  "year": 2021,
  "completeness": 0.723
}
```

The full schema is at [`schema/chip-schema.json`](schema/chip-schema.json). Core fields:

| Field | Type | Description |
|---|---|---|
| `id` | `string` | Unique slug (e.g. `sm8250_kona`) |
| `name` | `string` | Marketing name |
| `vendor` | `string` | Vendor name |
| `model` | `string` | Model number |
| `year` | `integer` | Release year |
| `architecture` | `string` | ISA / architecture |
| `process_nm` | `integer` | Process node in nanometres |
| `cores` | `integer` | CPU core count |
| `gpu` | `string` | GPU name |
| `memory_type` | `string` | RAM type |
| `completeness` | `float` | Weighted field coverage (0–1) |

---

## Architecture

```
soc-db/
├── src/soc_db/       # Python package (pip-installable)
│   ├── common.py         # Shared utilities, enrichment, vendor knowledge
│   ├── parsers.py        # Wikipedia table cell parsers
│   ├── cli.py            # soc-db CLI (entry point)
│   ├── scraper_wikipedia.py
│   └── scraper_apple.py
├── api/              # FastAPI REST server
├── data/             # JSON data files (one per vendor)
├── tests/            # Test suite (pytest, 46+ tests)
├── schema/           # JSON Schema
├── docs/             # OpenAPI spec + Swagger UI
├── deploy/           # Systemd timer for auto-update
├── scripts/          # Legacy (deprecated) runner scripts
└── pyproject.toml    # Project metadata & tooling config
```

---

## Development

```bash
git clone https://github.com/vitkuz573/soc-db.git
cd soc-db
python3 -m venv .venv && source .venv/bin/activate
make install-dev     # install dependencies + pre-commit hooks
make ci              # lint → typecheck → test → validate
```

### Quality gates

| Command | What it does |
|---|---|
| `make lint` | Ruff lint + format check |
| `make typecheck` | mypy strict (core modules) |
| `make test` | pytest (46+ tests) |
| `make test-cov` | Test with coverage report |
| `make validate` | JSON Schema validation (all 1096 chips) |
| `make security` | Bandit security audit |
| `make ci` | All of the above |

### Scraping pipeline

| Vendor | File | Chips | Source |
|---|---|---|---|
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

---

## Project Status

SOC-DB follows **semantic versioning** ([CHANGELOG](CHANGELOG.md)). The data format is versioned via `data/index.json` and evolves with minor bumps. See the [Roadmap](ROADMAP.md) for planned features.

1000+ chips curated, enriched, and validated. New vendors and corrections accepted via pull request.

---

## Contributing

Contributions of any size are welcome — data corrections, new chips, code improvements, documentation.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide.

### Quick checklist

1. Run `make ci` — all checks must pass
2. Add or update tests where appropriate
3. Update `CHANGELOG.md` if the change is user-facing
4. Open a pull request

---

## License

[MIT](LICENSE) — free to use, modify, and distribute.

---

<p align="center">
  <sub>Built with ❤️ for developers who need to know what's inside their SoC.</sub>
</p>
