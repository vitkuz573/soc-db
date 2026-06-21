# SOC-DB

Enterprise-grade SoC / CPU identifier database.

- 100+ chips across 6 vendors (Qualcomm, MediaTek, Samsung, HiSilicon, Google, Apple)
- JSON Schema validated
- GitHub Pages frontend with search, filter, sort, and detailed chip view
- Local CLI validation (`make validate`)

## Quick Start

```bash
make validate   # validate all JSON files
make server     # start local web UI at http://localhost:8080/
```

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
├── data/           # JSON data files (one per vendor)
│   ├── index.json
│   ├── qualcomm.json
│   ├── mediatek.json
│   ├── exynos.json
│   ├── kirin.json
│   ├── tensor.json
│   └── apple.json
├── index.html      # GitHub Pages web UI (root level)
├── docs/
│   ├── api.md
│   └── contributing.md
├── schema/         # JSON Schema definition
│   └── chip-schema.json
├── tests/          # Validation scripts
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
