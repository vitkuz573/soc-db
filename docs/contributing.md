# Contributing to SOC-DB

## Adding a new SoC

1. Fork the repository.
2. Edit the appropriate data file in `data/` (e.g., `qualcomm.json` for Snapdragon chips).
3. Add a new entry following the [JSON Schema](../schema/chip-schema.json).

### Required fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique lowercase identifier (e.g., `sm8250_kona`) |
| `name` | string | Marketing name (e.g., `Snapdragon 870`) |
| `vendor` | string | Must be one of: `Qualcomm`, `MediaTek`, `Samsung`, `HiSilicon`, `Google`, `Apple`, `Intel`, `AMD` |
| `cores` | integer | Number of CPU cores |
| `architecture` | string | ISA (e.g., `ARMv8.2-A`) |
| `year` | integer | Release year |

### Optional fields

| Field | Type | Description |
|-------|------|-------------|
| `codename` | string | Internal platform codename |
| `model` | string | Exact model number |
| `revision` | string | Stepping/revision |
| `threads` | integer | Thread count (if different from cores) |
| `gpu` | string | Integrated GPU |
| `process` | string | Fabrication node (e.g., `7nm`) |
| `max_freq` | string | Maximum clock frequency |
| `cache` | object | Cache hierarchy (`l1`, `l2`, `l3`) |
| `devices` | string[] | Known devices using this SoC |
| `alternative_names` | string[] | Aliases |

## Validation

Before submitting, run the validation script:

```bash
python tests/validate.py
```

## Pull Request

1. Commit your changes to a new branch.
2. Open a PR against `main`.
3. The CI pipeline will automatically validate your JSON and update the index.
4. After merge, changes are deployed to GitHub Pages.
