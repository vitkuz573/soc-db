# Phase 6: WIKIDATA — Wikidata Knowledge Sync - Context

**Gathered:** 2026-07-19
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — smart discuss skipped)

<domain>
## Phase Boundary

Hardcoded `VENDOR_KNOWLEDGE` maps replaced with Wikidata SPARQL queries for process node, GPU, and architecture, with scheduled CI refresh.

Requirements: WIKIDATA-01, WIKIDATA-02

Success criteria:
1. Enrichment pipeline uses Wikidata SPARQL queries for process node, GPU model, and architecture data instead of hardcoded dicts
2. Weekly CI workflow refreshes vendor knowledge from Wikidata
3. SPARQL results are validated before overwriting maps (dry-run mode; never auto-publish)
4. Failed SPARQL queries don't corrupt existing vendor maps — retry with exponential backoff
</domain>

<decisions>
## Implementation Decisions

### the agent's Discretion
All implementation choices are at the agent's discretion — pure infrastructure phase.

### Key constraints
- SPARQLWrapper >=2.0 for Wikidata queries
- Wikidata properties: P2175 (process node), P488 (GPU), P10620 (architecture), P1552 (has quality)
- Dry-run mode before overwriting maps
- Exponential backoff on failed queries
- Weekly CI workflow via GitHub Actions or cron
</decisions>

<code_context>
## Existing Code Insights

### Key Files
- `src/soc_db/enrich/_vendor_data.py` — VENDOR_KNOWLEDGE dict with hardcoded maps
- `src/soc_db/enrich/gpu.py` — GPU inference from VENDOR_KNOWLEDGE
- `src/soc_db/enrich/process.py` — process node inference
- `src/soc_db/enrich/year.py` — year inference
- `src/soc_db/common.py` — VENDOR_KNOWLEDGE re-exports
- `scripts/scraper_wikidata_sparql.py` — existing SPARQL scraper (legacy)

### Current Pattern
- VENDOR_KNOWLEDGE manually maintained dict with process_map, gpu_map, architecture per vendor
- New chip releases require code change
- Wikidata scraper exists in scripts/ but is not integrated with enrichment
</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase.

Key constraints:
- SPARQLWrapper must be added to dependencies
- Wikidata queries must be cached (TTL-based, like existing fetch())
- VENDOR_KNOWLEDGE becomes a generated artifact from Wikidata
- Manual overrides still possible (local overrides file)
- All existing tests must pass
- GitHub Pages must NOT be touched
</specifics>

<deferred>
## Deferred Ideas

- Auto-PR workflow for data corrections — deferred to v2.2+
</deferred>
