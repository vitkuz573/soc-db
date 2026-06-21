# ADR 0002: Python Package Structure

## Status
Accepted

## Context
SOC-DB started as flat scripts. For v2.0.0, we needed a proper installable
package to support the CLI entry point, CI integration, and PyPI publishing.

## Decision
- Use `src/` layout (`src/soc_db/`) with `pyproject.toml` (PEP 621)
- Setuptools as build backend
- CLI entry point via `[project.scripts]` in `pyproject.toml`
- Legacy `bin/soc-db` kept as a shim for backward compatibility

## Consequences
- Clean separation of package code vs scripts/tools
- `pip install -e .` gives you the `soc-db` CLI
- `scripts/` directory retained temporarily; new code goes in `src/`
