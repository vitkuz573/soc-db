# Changelog

All notable changes to SOC-DB are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/),
and the project adheres to [Semantic Versioning](https://semver.org/).

## [2.0.0] — 2026-06-21

### Added
- Full enterprise project structure: `src/soc_db/` installable package
- `soc-db` CLI via `pyproject.toml` entry point
- Multi-stage Dockerfile with healthcheck
- Structured logging throughout the codebase
- 46 pytest unit tests (common utilities + parsers)
- ruff, mypy, pytest, coverage config in `pyproject.toml`
- Pre-commit hooks (ruff, mypy, trailing-whitespace)
- Swagger UI on GitHub Pages (`docs/swagger.html`)
- GitHub Pages frontend redesign: hero, animations, URL filters, skeleton loader
- Issue templates (bug, feature, data) and PR template
- CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md
- 404.html page

### Changed
- Imports use absolute paths (`from soc_db.xxx import yyy`)
- Data validation: 1096 chips across 23 vendors
- README with badges, accurate counts, GH Pages links

### Removed
- GitHub Actions CI (not available in Russia)
- Backward-compat shims from `scripts/`

## [1.0.0] — 2026-06-20

### Added
- Initial release with Wikipedia scraper pipeline
- JSON Schema validation
- GitHub Pages frontend with search, filter, sort, detail view
- FastAPI REST server with JSON, CSV, gzipped export
- Systemd timer for auto-scrape
- 14 vendors, ~1171 chips
