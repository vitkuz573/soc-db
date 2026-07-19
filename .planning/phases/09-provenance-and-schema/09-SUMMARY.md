# Phase 9: Provenance & Schema — Summary

**Completed:** 2026-07-19

## What Was Done

- **30 new fields** added to Chip model (market_segment, charging, Wi-Fi, AV1, AI TOPS, PCIe, USB, Bluetooth ver, satellite, GNSS, fingerprint, display, camera, ISP, DSP, security, cache, die_size, etc.)
- **`src/soc_db/provenance.py`** — ProvenanceTracker, ConflictResolver, apply_provenance with system field filtering
- **Provenance applied** to all 1761 existing chips as `legacy_v2`
- **FIELD_GROUPS/FIELD_WEIGHTS** updated to cover all new fields
- **Snapshot updated** for all 1761 chips

## Verification

- **Unit tests**: 638 passed (all existing + provenance tests)
- **Provenance**: all chips have per-field provenance tracking
- **New fields**: all optional — no API/CLI breakage
