---
phase: 07-governance-and-safety
plan: 01
subsystem: governance
tags:
  - legal
  - compliance
  - scraping
  - documentation
requires: []
provides:
  - Scraping compliance matrix for all 11 current and planned sources
  - C&D response procedure
  - robots.txt compliance policy
affects:
  - "data/LEGAL.md"
  - "All scraper development in Phases 8-14 references this document"
tech-stack:
  added: []
  patterns:
    - GFM tables for structured compliance data
    - Risk level taxonomy: Low / Medium / High
key-files:
  created:
    - "data/LEGAL.md"
  modified: []
decisions:
  - "GSMArena and DeviceSpecifications deferred to Phase 14 for legal review"
  - "Apple Tech Specs assigned Medium risk (ToS prohibits scraping but factual specs likely not copyrightable)"
  - "NotebookCheck assigned High risk (broad robots.txt Disallow: /)"
status: complete
metrics:
  duration: "~5 min"
  completed_date: "2026-07-19"
tasks_completed: 1
requirements: [GOV-01]
---

# Phase 7 Plan 1: Legal Matrix Summary

**One-liner:** Created `data/LEGAL.md` with scraping compliance matrix covering all 11 current and planned sources, including ToS links, robots.txt status, risk levels, C&D response plan, and jurisdictional notes.

## What Was Built

### `data/LEGAL.md`

A comprehensive compliance reference document covering:

- **Disclaimer** — prominently displayed "NOT LEGAL ADVICE" warning
- **Current Sources** table — Wikipedia, Wikidata, Apple Tech Specs, Linux DeviceTree
- **Planned Sources** table — TechPowerUp, NotebookCheck, Geekbench Browser, Qualcomm, MediaTek, Intel ARK, AMD
- **robots.txt Compliance Policy** — checked before every scrape, cached with 24h TTL, fail-open
- **C&D Response Plan** — 6-step halt-and-archive procedure
- **Jurisdictional Notes** — US (Feist, hiQ, Van Buren), EU (Database Directive, GDPR, TDM exception), UK
- **Source-Specific Notes** — GSMArena/DeviceSpecifications deferred to Phase 14
- **Future Review Queue** — tracks sources awaiting legal review

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

None.

## Self-Check: PASSED

- `data/LEGAL.md` exists and passes content checks
- 11 sources documented with ToS links, robots.txt status, and risk levels
- C&D response plan documented
- Disclaimer prominently displayed
- GSMArena references Phase 14
