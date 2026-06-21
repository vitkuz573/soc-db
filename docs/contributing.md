# Contributing

See the main [Contributing Guide](../CONTRIBUTING.md) for full details.

## Quick Reference

```bash
make install-dev     # set up dev environment
make lint            # ruff check
make typecheck       # mypy
make test            # pytest
make validate        # JSON Schema validation
```

### Data Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique slug (e.g. `sm8250_kona`) |
| `name` | string | Marketing name |
| `vendor` | string | Vendor name |
| `cores` | integer | CPU core count |
| `year` | integer | Release year |
| `process` | string | Process node |
| `architecture` | string | ISA (e.g. `ARMv8.2-A`) |

See [JSON Schema](../schema/chip-schema.json) for all fields and validation rules.
