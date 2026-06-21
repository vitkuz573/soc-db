# SOC-DB API Reference

Base URL: `https://vitkuz573.github.io/soc-db/`

## Endpoints

### `GET /data/index.json`
Returns the database index with version, vendor summaries, and entry counts.

### `GET /data/{vendor}.json`
Returns an array of chip entries for a specific vendor.

| Vendor | File |
|--------|------|
| Qualcomm | `qualcomm.json` |
| MediaTek | `mediatek.json` |
| Samsung | `exynos.json` |
| HiSilicon | `kirin.json` |
| Google | `tensor.json` |
| Apple | `apple.json` |

## Query Parameters (client-side)

All filtering is performed client-side. See the [web UI](https://vitkuz573.github.io/soc-db/) for interactive search, filtering, and sorting.

## Schema

The JSON Schema for chip entries is available at:

```
https://vitkuz573.github.io/soc-db/schema/chip-schema.json
```

## Example

```bash
# Get all Qualcomm chips
curl https://vitkuz573.github.io/soc-db/data/qualcomm.json

# Get index
curl https://vitkuz573.github.io/soc-db/data/index.json
```
