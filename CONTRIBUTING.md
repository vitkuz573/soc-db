# Contributing to SOC-DB

Thanks for your interest! SOC-DB aims to be the definitive open database of SoC/CPU identifiers. Contributions of any size — data corrections, new chips, code improvements, docs — are very welcome.

## Quick Start

```bash
git clone https://github.com/vitkuz573/soc-db.git
cd soc-db
python3 -m venv .venv && source .venv/bin/activate
make install-dev
make ci          # lint + typecheck + test
```

## Ways to Contribute

### Data

- **New chip**: add or update the vendor's JSON file in `data/`
- **Correction**: open a [Data Issue](https://github.com/vitkuz573/soc-db/issues/new?template=03_data_issue.yml)
- **New vendor**: add scraper + data file + index entry

All data must validate against `schema/chip-schema.json` — run `make validate`.

### Code

- **CLI / library**: edit files under `src/soc_db/`
- **API**: edit `api/main.py`
- **Frontend**: edit `index.html`

### Documentation

- `docs/api.md`, `docs/contributing.md`, `README.md`

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes
3. Run `make ci` — all checks must pass
4. Run `make security` — no critical vulnerabilities
5. A maintainer will review your PR

## Code Standards

- **Python**: ruff lint + mypy strict — config in `pyproject.toml`
- **Data**: JSON Schema validation + `make validate`
- **Frontend**: vanilla JS, no frameworks, works without build step
- **No print()** — use `logging` (configured in `src/soc_db/common.py`)

## Data Format

Every chip entry follows the [JSON Schema](schema/chip-schema.json). Key fields:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique slug (e.g. `sm8250_kona`) |
| `name` | string | Marketing name |
| `vendor` | string | Vendor name |
| `cores` | integer | CPU core count |
| `year` | integer | Release year |
| `process` | string | Process node (e.g. `7nm`) |
| `architecture` | string | ISA/arch (e.g. `ARMv8.2-A`) |

## Code of Conduct

All contributors must follow our [Code of Conduct](CODE_OF_CONDUCT.md).

## Questions?

Open a [Discussion](https://github.com/vitkuz573/soc-db/discussions) or an issue.
