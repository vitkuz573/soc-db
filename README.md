# SOC-DB

Enterprise-grade SoC / CPU identifier database.

- **636+ chips** across 6 vendors (Qualcomm, MediaTek, Samsung, HiSilicon, Google, Apple)
- JSON Schema validated
- GitHub Pages frontend with search, filter, sort, and detailed chip view
- Automated Wikipedia scraper pipeline (`make scrape`)

## Quick Start

```bash
make scrape     # scrape Wikipedia data for all vendors
make validate   # validate all JSON files
make server     # start local web UI at http://localhost:8080/
```

## Scraping Pipeline

Automatic extraction from Wikipedia tables:

| Vendor | Data file | Source |
|--------|-----------|--------|
| Qualcomm | `data/qualcomm.json` | List of Snapdragon processors |
| MediaTek | `data/mediatek.json` | List of MediaTek processors |
| Samsung | `data/exynos.json` | Exynos page |
| HiSilicon | `data/kirin.json` | HiSilicon page |
| Google | `data/tensor.json` | Google Tensor page |
| Apple | `data/apple.json` | Apple A-series + M-series (name mapping) |

Run `bash scripts/run_all.sh` to refresh all data from Wikipedia.

## Data Format

Each chip entry follows the [JSON Schema](schema/chip-schema.json):

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
  "devices": ["POCO F4", "OnePlus 9R"]
}
```

## Project Structure

```
soc-db/
├── data/             # JSON data files (one per vendor)
│   ├── index.json
│   └── {vendor}.json
├── scripts/          # Wikipedia scrapers
│   ├── common.py
│   ├── scraper_wikipedia.py
│   ├── scraper_apple.py
│   └── run_all.sh
├── index.html        # GitHub Pages web UI
├── docs/
│   ├── api.md
│   └── contributing.md
├── schema/
│   └── chip-schema.json
├── tests/
│   └── validate.py
├── Makefile
├── package.json
└── LICENSE
```

## License

MIT

## Links

- **Web UI**: https://vitkuz573.github.io/soc-db/
- **Repository**: https://github.com/vitkuz573/soc-db
