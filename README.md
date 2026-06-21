# SOC-DB

Enterprise-grade SoC / CPU identifier database.

- **1171+ chips** across 14 vendors
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
