# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- 100% test coverage (405 tests), dead code removal, T-prefix bug fix
- SOC-DB logo in light and dark variants
- Industry-standard governance: CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md, issue/PR templates
- GH Pages redesign with hero section, animations, URL filters, skeleton loading, 404 page
- Swagger UI documentation on GitHub Pages
- `.editorconfig`, `.gitattributes`, FUNDING.yml, repo topics, labels
- `make ci` target (CI-agnostic)

### Changed

- Redesigned README in industry-standard style
- Upgraded typing, linting, documentation, ADRs, roadmap, migration guide
- Massive enterprise repo structure refactoring
- Replaced PyPI badge with static version badge

### Fixed

- Badge rendering (PyPI → static version badge)
- Coverage improved from 60% to 100% (179 → 405 tests)
- Lint and typecheck fixes

## [2.0.0] - 2026-06-21

### Added

- Enterprise schema v2 with completeness scoring
- CLI, REST API, and Docker support
- Enterprise Wikipedia scraper extracting all infobox fields (CPU, GPU, memory, modem, connectivity, display, camera, video, DSP, NPU, charging, cluster config)
- Automated pipeline (`make pipeline`) with fixed column detection
- Memory clock inference and expanded vendor knowledge
- Auto-deploy timer
- Linux DeviceTree scraper with 9 new vendors (+71 chips)
- Inference of `process_nm`, `memory_type`, `storage_type` from year when missing

### Changed

- Enriched enterprise field coverage across all vendors

### Fixed

- Pipeline error counting false positives (average completeness 0.359)
- Google: handle transposed Wikipedia tables and prune garbage entries
- MediaTek: strip "(now managed and sold to X)" from names/models/IDs
- Strip Wikipedia citation brackets `[123]` from all fields

## [1.0.0] - 2026-06-21

### Added

- Initial release: 61 SoC entries, 6 vendors, JSON Schema, GH Pages UI
- Automated Wikipedia scraper pipeline (636 chips across 6 vendors)
- Expanded to 14 vendors, 1171 chips with full Wikipedia scraper pipeline
- Dynamic `index.json` with all 14 vendors
