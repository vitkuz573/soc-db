# Migration Guide

## v1.0.0 → v2.0.0

v2.0.0 was a complete rewrite of the project structure. Key changes:

### Package relocation
- **Old**: `scripts/common.py`, `scripts/parsers.py` (flat scripts)
- **New**: `src/soc_db/common.py`, `src/soc_db/parsers.py` (installable package)

**Action**: Update imports from `from common import X` to `from soc_db.common import X`.

### CLI entry point
- **Old**: `bin/soc-db` (standalone script)
- **New**: `soc-db` (installed via `pip install -e .`)

**Action**: Run `pip install -e .` to get the new CLI entry point. The old `bin/soc-db` still works as a shim.

### Data format
- JSON Schema updated to v2. New fields: `process_nm`, `memory_type`, `storage_type`, `cluster_config`, `charging`, `npu`, `aliases`, `sources`, `updated`, `completeness`.

**Action**: Run `make enrich` to update existing data files.

### Removed
- GitHub Actions CI (replaced with alternative CI solutions)
- Legacy backward-compat shims in `scripts/`

## v2.0.0 → v2.1.0

*Not yet released — this section will be updated when v2.1.0 ships.*
