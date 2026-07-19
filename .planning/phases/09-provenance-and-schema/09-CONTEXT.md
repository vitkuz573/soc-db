# Phase 9: Provenance & Schema - Context

**Gathered:** 2026-07-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Field-level provenance tracking and 30 new Chip model fields.

Requirements: PROV-01, PROV-02

Success criteria:
1. Every chip field carries `{field_name}: source_id` provenance tag
2. ConflictResolver logs field-level conflicts — no last-writer-wins
3. 30 new fields added (charging, Wi-Fi version, AI TOPS, PCIe, market_segment, etc.)
4. All 1761 existing chips get `legacy_v2` provenance
5. Completeness scoring covers all 95 fields
</domain>

<code_context>
## Existing Code Insights

### Key Files
- `src/soc_db/models.py` — Chip model (95 fields)
- `src/soc_db/enrich/scoring.py` — completeness scoring
- `src/soc_db/scraping/base.py` — BaseScraper, ChipScrapeResult (Phase 8)
- `data/*.json` — existing chip data

### Current State
- Chip model has 95 fields
- `completeness` score uses FIELD_GROUPS + FIELD_WEIGHTS
- No provenance tracking per field
- sources: {} dict exists but is always empty
</code_context>

<specifics>
## Specific Ideas

1. Add `_provenance` dict to Chip model: {field_name: source_id}
2. Create ProvenanceTracker: records source per field on write
3. Create ConflictResolver: logs when multiple sources disagree
4. Add 30 new fields: market_segment, charging_max_w, wifi_version_numeric, modem_5g_mmwave, video_decode_av1, ai_int8_tops, pcie_version, usb_version_numeric, etc.
5. Migrate all 1761 existing chips to mark all fields as legacy_v2
6. Update completeness scoring to cover all 95-125 fields
</specifics>
