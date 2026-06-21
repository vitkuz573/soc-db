# ADR 0003: JSON Schema and Enrichment Strategy

## Status
Accepted

## Context
Chip data from Wikipedia is inconsistent (different columns, naming conventions,
missing fields). We need a consistent schema and a way to fill in missing data.

## Decision
- JSON Schema v2 defines ~50 fields across identity, core, process, GPU,
  memory, AI, modem, media, connectivity, lifecycle, provenance, and metadata
- Enrichment (`common.enrich_one()`) fills missing fields using:
  1. Vendor knowledge maps (process node, GPU per model)
  2. Year-based inference (memory type, Wi-Fi, Bluetooth)
  3. Model number heuristics (MediaTek MTxxxx → year)
- Completeness score tracks what fraction of weighted fields is filled

## Consequences
- Data is consistent across vendors
- Completeness score helps users gauge data quality
- Enrichment logic is complex; needs careful maintenance
