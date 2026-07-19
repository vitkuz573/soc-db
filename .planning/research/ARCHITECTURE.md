# Architecture Research: Multi-Source Scraper Framework with Field-Level Provenance

**Domain:** SoC database — multi-source data collection pipeline
**Researched:** 2026-07-19
**Confidence:** HIGH

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SURFACES (unchanged)                               │
│  ┌───────────────────┐  ┌──────────────────┐  ┌───────────────────────────┐ │
│  │  CLI (argparse)   │  │  REST API (FastAPI)│  │  Web UI (GitHub Pages)  │ │
│  │  soc-db query/... │  │  /v1/chips, /vendors│  │  docs/: static HTML/JS  │ │
│  └────────┬──────────┘  └────────┬─────────┘  └──────────────┬────────────┘ │
│           │                      │                            │              │
├───────────┴──────────────────────┴────────────────────────────┴──────────────┤
│                      QUERY LAYER (unchanged)                                 │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │  soc_db.db.queries — sync + async read path (SQLite FTS5 / JSON dual) │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                      │                                       │
├──────────────────────────────────────┴───────────────────────────────────────┤
│                         DATA LAYER (extended)                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │  data/*.json (per-vendor SOURCE OF TRUTH) — NEW: provenance fields     │  │
│  │  data/soc-db.db (SQLite read replica, auto-migrated)                    │  │
│  │  data/provenance.db (NEW — SQLite: field-level source tracking)         │  │
│  │  data/quality_reports/ (NEW — per-vendor, per-field quality scores)     │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
│                                      ▲                                        │
├──────────────────────────────────────┴───────────────────────────────────────┤
│                           ▲  WRITE LAYER (NEW)                                │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │  soc_db.scraping — UNIFIED SCRAPER FRAMEWORK (replaces scripts/)        │  │
│  │                                                                          │  │
│  │  ┌────────────────┐  ┌────────────────┐  ┌─────────────────────────┐    │  │
│  │  │ BaseScraper    │  │ SourceRegistry │  │ ProvenanceTracker       │    │  │
│  │  │ (abstract)     │◄─│ (discovery +   │  │ (field → source mapping) │    │  │
│  │  └───────┬────────┘  │  registration) │  └──────────┬──────────────┘    │  │
│  │          │           └────────────────┘             │                    │  │
│  │  ┌───────┴──────────────────────────────────────────┴────────────────┐  │  │
│  │  │  ConflictResolver — cross-source merge + priority arbitration     │  │  │
│  │  └───────────────────────────────────────────────────────────────────┘  │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
│                                      │                                        │
├──────────────────────────────────────┴───────────────────────────────────────┤
│                       ENRICHMENT LAYER (enhanced)                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │  soc_db.enrich — per-domain modules (14 existing + batch orchestrator)  │  │
│  │  NEW: BatchEnricher — processes chips in batches with progress tracking │  │
│  │  NEW: QualityScorer — per-vendor + per-field quality metrics            │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
│                                      │                                        │
├──────────────────────────────────────┴───────────────────────────────────────┤
│                      INFRASTRUCTURE LAYER (enhanced)                          │
│  ┌──────────────────────┐  ┌───────────────────┐  ┌───────────────────────┐  │
│  │ Rate Limiter (Redis) │  │ Telemetry (OTel)  │  │ CI Pipeline (GHA)    │  │
│  │ + in-memory fallback │  │ + Prometheus      │  │ NEW: auto PR workflow│  │
│  └──────────────────────┘  └───────────────────┘  └───────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### What Changes vs What Stays

| Component | Status | Rationale |
|-----------|--------|-----------|
| CLI (soc_db/cli.py) | UNCHANGED | No new CLI commands needed — scrapers are infra, not user-facing |
| REST API (api/main.py) | UNCHANGED | Backward compat required; quality data exposed via new endpoints only |
| Web UI (docs/) | UNCHANGED | GitHub Pages must NOT break — no changes to docs/ directory |
| soc_db/models.py (Chip) | EXTENDED | Add `provenance: dict[str, str]` field; keep `sources` for backward compat |
| soc_db/db/ queries | EXTENDED | Add queries for provenance data and quality reports |
| soc_db/enrich/ modules | EXTENDED | Add `BatchEnricher` orchestrator, `QualityScorer`, batch-aware enrichment |
| soc_db/common.py | REFACTORED | Remove `write_vendor_file`, `_match_existing`, `merge_chips` → move to scraper framework |
| src/soc_db/scraper_*.py | REPLACED | Inline script scrapers → framework-backed implementations |
| scripts/ directory | DEPRECATED | All scraper logic moves into `src/soc_db/scraping/`; scripts become thin wrappers then removed |
| scripts/common.py | DELETED | Duplicate of src/soc_db/common.py — source of drift, must be eliminated |
| data/*.json | EXTENDED | Add `provenance` dict per chip; no schema-breaking changes |

### Component Responsibilities

| Component | Responsibility | Implementation |
|-----------|---------------|----------------|
| **BaseScraper** | Abstract scraper contract: fetch, parse, normalize, emit typed records | `abc.ABC` with `run() → list[ChipScrapeResult]` |
| **SourceRegistry** | Discover, register, and prioritize scraper sources per vendor | Singleton dict mapping vendor → ordered list of source priorities |
| **ProvenanceTracker** | Track which source provided each field value (field → source_id) | Dict of `{field_name: source_label}` per chip, stored in chip `provenance` field |
| **ConflictResolver** | Merge multiple source outputs: assign priority, resolve conflicts, flag disputes | Rule-based: authoritative source wins; ties → `conflict` flag in `provenance` |
| **BatchEnricher** | Enrich 5000+ chips in batches with progress, checkpointing, and dedup | Chunked processing (500-chip batches), intermediate checkpoint to JSON |
| **QualityScorer** | Compute per-vendor and per-field quality metrics | Source coverage, fill rate, conflict rate, staleness — rolled up into `data/quality_reports/` |
| **AutoPR Workflow** | GitHub Actions: nightly scrape → validate → create PR with data changes | `gh` CLI in GHA, branch per run, auto-label, link to diff |

## Recommended Project Structure

```
src/soc_db/
├── __init__.py
├── __main__.py
├── cli.py                    # UNCHANGED
├── common.py                 # REFACTORED — remove write_vendor_file, _match_existing, merge_chips
├── config.py                 # UNCHANGED
├── models.py                 # EXTENDED — add ProvenanceChip or provenance field to Chip
├── parsers.py                # UNCHANGED (used by Wikipedia scraper HTML parsing)
├── log_config.py             # UNCHANGED
├── rate_limit.py             # UNCHANGED
├── telemetry.py              # UNCHANGED
├── wikidata.py               # UNCHANGED (Wikidata SPARQL for vendor knowledge refresh)
│
├── scraping/                 # NEW — unified scraper framework (replaces scripts/)
│   ├── __init__.py           #   Exports: BaseScraper, SourceRegistry, run_pipeline
│   ├── base.py               #   BaseScraper ABC, ChipScrapeResult model
│   ├── registry.py           #   SourceRegistry — source discovery, priorities, activation
│   ├── provenance.py         #   ProvenanceTracker — field → source mapping
│   ├── conflict.py           #   ConflictResolver — merge, priority, conflict detection
│   ├── pipeline.py           #   Orchestrator — run → merge → resolve → write
│   │
│   ├── sources/              # Per-source scraper implementations
│   │   ├── __init__.py       #   Auto-registers all scrapers via import side-effect or registry
│   │   ├── wikipedia.py      #   MOVED from scripts/ + src/soc_db/scraper_wikipedia.py
│   │   ├── apple.py          #   MOVED from scripts/ + src/soc_db/scraper_apple.py
│   │   ├── linux_dt.py       #   MOVED from scripts/scraper_linux_dt.py
│   │   ├── wikidata_sparql.py#   MOVED from scripts/scraper_wikidata_sparql.py
│   │   ├── qualcomm_official.py  # NEW — Qualcomm Developer Network / official specs
│   │   ├── mediatek_official.py  # NEW — MediaTek official product listings
│   │   └── techpedia.py      # NEW — Techpedia / third-party aggregator
│   │
│   └── conftest.py           # Test fixtures for scraper framework
│
├── enrich/                   # ENHANCED
│   ├── __init__.py
│   ├── _helpers.py           # UNCHANGED
│   ├── _vendor_data.py       # UNCHANGED (may get new vendor entries)
│   ├── _vendor_data_wikidata.py  # UNCHANGED
│   ├── aliases.py            # UNCHANGED
│   ├── connectivity.py       # UNCHANGED
│   ├── cpu.py                # UNCHANGED
│   ├── gpu.py                # UNCHANGED
│   ├── memory.py             # UNCHANGED
│   ├── modem.py              # UNCHANGED
│   ├── npu.py                # UNCHANGED
│   ├── process.py            # UNCHANGED
│   ├── scoring.py            # EXTENDED — add per-vendor + per-field quality scoring
│   ├── storage.py            # UNCHANGED
│   ├── year.py               # UNCHANGED
│   ├── batch.py              # NEW — BatchEnricher (chunked processing, checkpointing)
│   └── quality.py            # NEW — QualityScorer (per-vendor, per-field metrics)
│
├── db/                       # EXTENDED
│   ├── __init__.py
│   ├── connection.py         # UNCHANGED
│   ├── schema.py             # EXTENDED — add provenance columns to chips table
│   ├── queries.py            # EXTENDED — add quality report queries
│   └── migrate.py            # EXTENDED — handle provenance schema migration
│
└── cli.py                    # UNCHANGED

scripts/                      # DEPRECATED — all removed after scraper framework stabilizes
```

### Structure Rationale

- **`scraping/` as a top-level subpackage:** Scraping is a distinct concern from querying (reads vs writes). Making it a peer of `db/`, `enrich/`, etc. signals it's a first-class architectural component, not a collection of scripts.
- **`scraping/sources/` per-source isolation:** Each scraper source has different fetch, parse, and auth requirements. Isolating them prevents cross-contamination and makes adding a new source a single-file change.
- **`scraping/provenance.py` as a standalone module:** Provenance tracking cross-cuts all sources and the conflict resolver. Keeping it separate prevents circular dependencies between sources.
- **`enrich/batch.py` separated from per-domain logic:** Batch orchestration (chunking, checkpointing, progress) is infrastructure, not domain knowledge. Per-domain modules stay pure and testable.
- **`enrich/quality.py` separated from `scoring.py`:** Scoring is per-chip completeness (internal metric). Quality is per-vendor/per-field health (management metric). Different consumers, different update cadence.
- **`data/quality_reports/` as generated artifacts:** Quality reports are derived data, not source of truth. Keeping them in a subdirectory signals they can be regenerated at any time.

## Architectural Patterns

### Pattern 1: Plugin-Based Source Registration

**What:** Each scraper source inherits from `BaseScraper` and registers itself with `SourceRegistry` via a class-level decorator or metaclass. The registry maintains an ordered priority list per vendor.

**When to use:** When multiple sources compete to provide the same data and need explicit priority ordering.

**Trade-offs:**
- (+) Adding a new source is a single file: implement `BaseScraper`, add to registry.
- (+) Explicit priority per vendor means no implicit last-writer-wins.
- (-) Priority must be maintained manually; a new authoritative source might need re-prioritization.

**Example:**
```python
# scraping/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ChipScrapeResult:
    """Normalized output from any scraper source."""
    name: str
    vendor: str
    model: Optional[str] = None
    fields: dict[str, any] = field(default_factory=dict)
    # Provenance is set by the framework, not individual scrapers
    # Scrapers declare their source_id via SOURCE_ID class attr


class BaseScraper(ABC):
    """Every scraper source implements this."""
    SOURCE_ID: str = ""              # e.g. "wikipedia", "qualcomm_official"
    VENDORS: list[str] = []          # e.g. ["Qualcomm", "MediaTek"]
    PRIORITY: int = 100              # Lower = higher priority (1 = most authoritative)

    @abstractmethod
    def scrape(self) -> list[ChipScrapeResult]:
        """Fetch and parse data from source."""
        ...

    def validate(self, result: ChipScrapeResult) -> bool:
        """Optional per-source validation hook."""
        return True
```

```python
# scraping/registry.py
from typing import Optional


class SourceRegistry:
    """Global registry of scraper sources with per-vendor priority ordering."""

    _sources: dict[str, list[type[BaseScraper]]] = {}  # vendor → [scraper classes]

    @classmethod
    def register(cls, scraper_cls: type[BaseScraper]) -> None:
        for vendor in scraper_cls.VENDORS:
            cls._sources.setdefault(vendor, []).append(scraper_cls)
            # Sort by priority (ascending) so iteration is authoritative-first
            cls._sources[vendor].sort(key=lambda s: s.PRIORITY)

    @classmethod
    def get_for_vendor(cls, vendor: str) -> list[type[BaseScraper]]:
        return cls._sources.get(vendor, [])

    @classmethod
    def all_sources(cls) -> list[type[BaseScraper]]:
        seen: set[str] = set()
        result: list[type[BaseScraper]] = []
        for scrapers in cls._sources.values():
            for s in scrapers:
                if s.SOURCE_ID not in seen:
                    seen.add(s.SOURCE_ID)
                    result.append(s)
        return result
```

### Pattern 2: Field-Level Provenance via Immutable Audit Trail

**What:** Every field value in a chip record carries metadata about which source provided it. Provenance is stored as a parallel dict `{field_name: source_id}` within each chip record, alongside a `conflicts` list for fields where sources disagree.

**When to use:** When data comes from multiple sources with varying reliability and you need to trace which source contributed each fact.

**Trade-offs:**
- (+) Full traceability — answers "where did this process node come from?" at runtime.
- (+) Enables quality scoring per source (source A's GPU data is more reliable than source B's).
- (-) Storage overhead: `provenance` dict adds ~200 bytes per chip for 60 populated fields.
- (-) Complexity: conflict resolution can produce unexpected results if priority is wrong.

**Example:**
```python
# scraping/provenance.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ProvenanceTracker:
    """Tracks field-level source attribution for a single chip merge."""

    def __init__(self, chip_id: str, vendor: str):
        self.chip_id = chip_id
        self.vendor = vendor
        self._provenance: dict[str, str] = {}     # field → source_id
        self._conflicts: list[dict[str, Any]] = []  # list of conflict records

    def set_field(self, field: str, value: Any, source: str) -> None:
        """Record field value provenance. Existing values are NOT overwritten
        (first-writer-wins per priority ordering of sources)."""
        if field not in self._provenance:
            self._provenance[field] = source
        elif self._provenance[field] != source:
            # Conflict detected — both sources claim this field
            self._conflicts.append({
                "field": field,
                "winner": self._provenance[field],
                "loser": source,
                "winner_value": None,   # filled during resolution
                "loser_value": None,
            })

    def to_dict(self) -> dict[str, str]:
        return dict(self._provenance)

    @property
    def conflicts(self) -> list[dict[str, Any]]:
        return list(self._conflicts)

    @property
    def field_count(self) -> int:
        return len(self._provenance)

    @property
    def conflict_count(self) -> int:
        return len(self._conflicts)
```

### Pattern 3: Conflict Resolution with Explicit Priority Matrix

**What:** When two or more sources provide different values for the same field, a `ConflictResolver` uses a per-vendor priority matrix to decide which source wins. Ties are flagged with a `conflict` flag in the chip's `provenance` metadata.

**When to use:** When source overlap is high and silent last-writer-wins would hide data quality issues.

**Trade-offs:**
- (+) Explicit: every conflict is logged and auditable.
- (+) Tunable: per-field overrides allow "Wikipedia CPU field wins, but Qualcomm official wins for process node".
- (-) Requires maintenance: new sources need priority entries.
- (-) Not appropriate for all fields — some (like year) benefit from consensus heuristics.

**Example:**
```python
# scraping/conflict.py
from __future__ import annotations

from typing import Any


# Priority matrix: (source_a, source_b, field) → winner
# Lower number = more authoritative
SOURCE_PRIORITY: dict[str, int] = {
    "qualcomm_official":  10,
    "mediatek_official":  10,
    "apple_official":     10,
    "wikipedia":          30,
    "wikidata_sparql":    50,
    "linux_dt":           70,
    "techpedia":          90,
}

# Field-level override: some sources are authoritative for specific fields
FIELD_AUTHORITY: dict[str, dict[str, int]] = {
    "process_nm": {
        "qualcomm_official": 1,
        "wikipedia":         2,
        "linux_dt":          3,
    },
    # Default priority used if no field-level override exists
}


class ConflictResolver:
    """Resolves field-level conflicts between sources using priority ordering."""

    @staticmethod
    def resolve(
        field: str,
        values: dict[str, Any],  # source_id → value
        vendor: str = "",
    ) -> tuple[str, Any, list[str]]:
        """Return (winning_source, value, rejected_sources).

        Uses field-level AUTHORITY when available, else global SOURCE_PRIORITY.
        If priorities are equal, records all sources with equal priority as
        rejected but still picks one (first in priority order).
        """
        if not values:
            raise ValueError("No values to resolve")

        if len(values) == 1:
            source, val = next(iter(values.items()))
            return source, val, []

        # Determine priority source for this field
        field_pri = FIELD_AUTHORITY.get(field, {})

        def _priority(source: str) -> int:
            return field_pri.get(source, SOURCE_PRIORITY.get(source, 100))

        # Sort sources by priority (ascending)
        sorted_sources = sorted(values.keys(), key=_priority)
        winner = sorted_sources[0]
        winner_priority = _priority(winner)

        rejected = [s for s in sorted_sources[1:] if _priority(s) == winner_priority]

        return winner, values[winner], rejected

    @staticmethod
    def has_conflict(field: str, values: dict[str, Any]) -> bool:
        """Return True if sources disagree on this field."""
        if len(values) <= 1:
            return False
        # Conflict = not all values are equal (after trivial normalization)
        unique = {str(v).lower().strip() for v in values.values()}
        return len(unique) > 1
```

### Pattern 4: Batch Enrichment with Checkpointing

**What:** Instead of enriching 5000+ chips one at a time (current `enrich_all`), the `BatchEnricher` processes chips in fixed-size batches with intermediate checkpoint files. If the process crashes mid-way, it resumes from the last checkpoint.

**When to use:** When batch size exceeds memory limits (5000 chips × 95 fields = significant memory pressure in enrichment) or processing time is long enough that crashes are costly.

**Trade-offs:**
- (+) Crash recovery — no need to re-enrich 5000 chips from scratch.
- (+) Progress visibility — each batch logs elapsed time, per-field fill rates, and ETA.
- (-) Complexity: checkpoint management adds I/O overhead.
- (-) Batch size tuning: too small → many checkpoints; too large → memory pressure.

**Example:**
```python
# enrich/batch.py
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

BATCH_SIZE = 500
CHECKPOINT_DIR = Path("data/.checkpoints")


class BatchEnricher:
    """Enrich chips in batches with checkpoint recovery."""

    def __init__(
        self,
        enrich_fn: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
        batch_size: int = BATCH_SIZE,
    ):
        self._enrich_fn = enrich_fn
        self._batch_size = batch_size
        CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        chips: list[dict[str, Any]],
        checkpoint_id: str = "default",
    ) -> list[dict[str, Any]]:
        """Enrich all chips, resuming from checkpoint if available."""
        cp_file = CHECKPOINT_DIR / f"{checkpoint_id}.json"
        start_idx = self._load_checkpoint(cp_file)

        result = chips[:start_idx]  # Already processed chunks
        total = len(chips)

        for i in range(start_idx, total, self._batch_size):
            batch = chips[i:i + self._batch_size]
            t0 = time.time()

            enriched = self._enrich_fn(batch)
            result.extend(enriched)

            elapsed = time.time() - t0
            pct = min(100, (len(result) / total) * 100)
            rate = len(batch) / max(elapsed, 0.001)
            eta = (total - len(result)) / max(rate, 0.001)

            logger.info(
                "Batch %d/%d: %d chips in %.1fs (%.1f chips/s, ETA %.0fs) [%d%%]",
                i // self._batch_size + 1,
                (total + self._batch_size - 1) // self._batch_size,
                len(batch), elapsed, rate, eta, int(pct),
            )

            self._save_checkpoint(cp_file, len(result))

        # Clean up checkpoint on success
        cp_file.unlink(missing_ok=True)
        return result

    def _load_checkpoint(self, path: Path) -> int:
        if path.exists():
            try:
                data = json.loads(path.read_text("utf-8"))
                count = data.get("processed", 0)
                logger.info("Resuming from checkpoint: %d chips already enriched", count)
                return count
            except (json.JSONDecodeError, KeyError, OSError):
                pass
        return 0

    def _save_checkpoint(self, path: Path, count: int) -> None:
        path.write_text(json.dumps({"processed": count, "timestamp": time.time()}, indent=2))
```

### Pattern 5: Quality Scoring as Derived Data

**What:** `QualityScorer` analyzes the entire chip corpus after each scraper run and produces per-vendor and per-field quality reports. These are written to `data/quality_reports/` and can be served via API or exposed in CI.

**When to use:** When you need to track data health over time and alert on regressions.

**Trade-offs:**
- (+) Management visibility — "MediaTek GPU fill rate dropped 5% this week".
- (+) CI gates — block PRs that reduce average quality below threshold.
- (-) Computation cost: scoring 5000 chips requires reading all provenance data.
- (-) Metric design is subjective: which fields matter most?

**Example:**
```python
# enrich/quality.py
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any


class QualityScorer:
    """Compute per-vendor and per-field quality metrics from chip corpus."""

    METRICS = {
        "fill_rate": "Fraction of chips that have this field populated",
        "source_diversity": "Number of distinct sources contributing to this field",
        "conflict_rate": "Fraction of chips where sources disagree on this field",
        "staleness_days": "Days since last update for this vendor",
    }

    @staticmethod
    def score_vendor(chips: list[dict[str, Any]], vendor: str) -> dict[str, Any]:
        """Quality report for a single vendor."""
        n = len(chips)
        if n == 0:
            return {"vendor": vendor, "chips": 0}

        field_stats: dict[str, dict[str, float]] = {}
        all_fields: set[str] = set()
        for chip in chips:
            all_fields.update(chip.keys())

        for field in sorted(all_fields):
            filled = sum(1 for c in chips if c.get(field) not in (None, "", {}, [], 0))
            provenance_entries = [
                c.get("provenance", {}).get(field)
                for c in chips
                if c.get("provenance", {}).get(field)
            ]
            sources = len(set(filter(None, provenance_entries)))
            conflicts = sum(
                1 for c in chips
                if field in c.get("provenance", {})
                and c.get("provenance", {}).get("_conflicts", "").find(field) >= 0
            )

            field_stats[field] = {
                "fill_rate": round(filled / n, 4),
                "source_count": sources,
                "conflict_rate": round(conflicts / n, 4) if n else 0,
            }

        # Overall vendor quality
        weighted_fill = sum(
            fs["fill_rate"] * FIELD_WEIGHTS.get(f, 1)
            for f, fs in field_stats.items()
        ) / sum(FIELD_WEIGHTS.get(f, 1) for f in field_stats)

        return {
            "vendor": vendor,
            "chips": n,
            "avg_completeness": round(
                sum(c.get("completeness", 0) for c in chips) / n, 4
            ),
            "quality_score": round(weighted_fill, 4),
            "field_stats": field_stats,
            "updated": str(date.today()),
        }
```

## Data Flow

### Scraper Pipeline Flow (NEW — replaces scripts/pipeline.py)

```
[Trigger: make scrape, GHA schedule, or manual CLI]
    │
    ▼
┌─────────────────────────────────────┐
│  Pipeline Orchestrator              │
│  (scraping/pipeline.py)            │
│                                     │
│  1. SourceRegistry.discover()       │
│     → Load all registered scrapers  │
│                                     │
│  2. For each vendor + source:       │
│     ┌───────────────────────┐       │
│     │ source.scrape()       │       │
│     │ → returns ChipScrape  │       │
│     │   Result[]            │       │
│     └───────────┬───────────┘       │
│                 │                   │
│  3. Merge per chip across sources   │
│     ┌────────────────────────┐      │
│     │ ConflictResolver       │      │
│     │ for each field:        │      │
│     │  • priority lookup     │      │
│     │  • first-writer-wins   │      │
│     │  • flag conflicts      │      │
│     └───────────┬────────────┘      │
│                 │                    │
│  4. ProvenanceTracker records       │
│     field → source per chip         │
│                 │                    │
│  5. write_vendor_file() (new)       │
│     → merges with existing JSON     │
│     → preserves existing fields     │
│       where no source overrides     │
│     → enriches via BatchEnricher    │
│                 │                    │
│  6. QualityScorer.score()           │
│     → writes data/quality_reports/  │
│                 │                    │
│  7. Validate schema + index         │
│     → same as current validate.py   │
│                 │                    │
└─────────────────┬───────────────────┘
                  │
                  ▼
       [data/*.json updated with provenance]
       [quality_reports/ generated]
```

### Provenance-Aware Write Flow

```
        Source A (Wikipedia)        Source B (Qualcomm Official)
              │                             │
              ▼                             ▼
        ┌──────────────┐            ┌──────────────┐
        │ {name: "Snap │            │ {name: "Snap │
        │  dragon 8G2",│            │  dragon 8G2",│
        │  process_nm: │            │  process_nm: │
        │  "4",        │            │  "4 nm",     │
        │  gpu: ...}   │            │  gpu: ...}   │
        └──────┬───────┘            └──────┬───────┘
               │                           │
               ▼                           ▼
        ┌─────────────────────────────────────┐
        │         ProvenanceTracker           │
        │                                     │
        │  process_nm: source A writes "4"    │
        │    → provenance["process_nm"]="wiki"│
        │  process_nm: source B writes "4 nm" │
        │    → conflict! existing != new      │
        │    → priority: wiki has lower       │
        │      priority than qualcomm_official│
        │    → winner: source B ("4 nm")      │
        │    → conflict logged                │
        └─────────────────┬───────────────────┘
                          │
                          ▼
        ┌─────────────────────────────────────┐
        │         ConflictResolver            │
        │                                     │
        │  process_nm:                        │
        │    winner = qualcomm_official       │
        │    value = "4 nm" → parse to 4      │
        │    rejected = [wikipedia]           │
        │                                     │
        │  Result:                            │
        │  {                                  │
        │    "process_nm": 4,                 │
        │    "provenance": {                  │
        │      "process_nm": "qualcomm_official"
        │      "_conflicts": [   ← stored as JSON string │
        │        {"field":"process_nm",       │
        │         "winner":"qualcomm_official",│
        │         "loser":"wikipedia"}         │
        │      ]                              │
        │    }                                │
        │  }                                  │
        └─────────────────────────────────────┘
```

### Auto-PR Workflow (NEW)

```
[GHA Schedule: nightly at 02:00 UTC]
    │
    ▼
┌──────────────────────────────────────────┐
│  1. checkout main                        │
│  2. python -m soc_db.scraping.pipeline   │
│     → updates data/*.json                │
│     → generates quality_reports/         │
│  3. git diff --stat data/                │
│     → if no changes: exit (nothing new)  │
│  4. git checkout -b "data/update-YYYYMMDD"│
│  5. git add data/                        │
│  6. git commit -m "data: nightly update" │
│  7. gh pr create --label "data-update"   │
│     --body "$(cat quality_summary.md)"    │
│  8. Post comment with quality diff       │
└──────────────────────────────────────────┘
```

### GitHub Pages Safety

The `docs/` directory is **never touched** by any scraper or enrichment code. The static files (`index.html`, `swagger.html`, `404.html`, `openapi.json`, `logo-*.svg`, `adr/*.md`, `api.md`, `contributing.md`) are committed to `main` and deployed by GitHub Pages. The CI pipeline that updates data must explicitly exclude `docs/` from any writes.

**Guard:** `soc_db.config.Settings` has a `DATA_DIR` that points to `data/`. No code path references `docs/` for writing. Pipeline staging writes to a temporary directory and only copies `data/` subdirectory to the final location.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1,746 chips (current) | Single-threaded pipeline, in-memory enrichment, no checkpointing needed |
| 5,000 chips (target) | Batch enrichment with checkpointing (500-chip batches); provenance DB advised; quality reports generated per-run |
| 20,000 chips (future) | SQLite provenance database required (JSON provenance dict becomes too large for in-memory); parallel source scraping via ThreadPoolExecutor; incremental enrichment (only dirty chips) |
| 100,000 chips (stretch) | Scraper workers as separate processes with shared message queue (Redis Streams); enrichment as async batch job; quality metrics via scheduled materialized views |

### Scaling Priorities

1. **First bottleneck at 5,000 chips:** `enrich_all()` is `O(n)` with each chip going through 14 enrichment modules. At 5,000 chips with 14 modules each doing dict lookups, the current single-threaded pipeline takes ~8-15 minutes. **Fix:** Batch enrichment with checkpointing and the ability to skip already-enriched chips via provenance timestamps.

2. **Second bottleneck at 5,000 chips:** JSON file size. `qualcomm.json` is currently 10,000+ lines for ~430 chips. At 5,000 chips total, vendor files average 7,000+ lines each, making git diffs noisy and manual review painful. **Fix:** The auto-PR workflow addresses this — humans don't review line-by-line, they review quality diffs. JSON splitting (one file per chip family) is an option for v3.1 but adds complexity.

3. **Third bottleneck at 10,000+ chips:** `write_vendor_file()` reads the entire vendor file, enriches all entries, and writes it back. This becomes I/O-bound. **Fix:** Incremental enrichment — only run enrichment on chips that have new data (check provenance timestamps). This requires tracking "last enriched" per chip in a metadata index.

## Anti-Patterns

### Anti-Pattern 1: Duplicate Utility Code (scripts/common.py)

**What the project currently has:** `scripts/common.py` is a near-duplicate of `src/soc_db/common.py`, containing `VENDOR_FILES`, `enrich_one()`, `write_vendor_file()`, and other shared code — copy-pasted and diverging.

**Why it's wrong:** Every change must be made in two places. The `scripts/` version doesn't have the Wikidata vendor knowledge merge or the full 14-module enrichment pipeline. Scrapers run from `scripts/` use the stale copy, producing different results than the library version.

**Do this instead:** Move all scraper logic into `src/soc_db/scraping/` and delete `scripts/` entirely. `scripts/common.py` is deleted. Scripts in `scripts/` become thin `__main__` wrappers that import from `soc_db.scraping`, then are removed once the framework is stable.

### Anti-Pattern 2: Silent Last-Writer-Wins Merge

**What the project currently has:** `merge_chips()` and `write_vendor_file()` use first-writer-wins (for `name`/`model`) but last-writer-wins for most other fields via `_match_existing()`.

**Why it's wrong:** The merge order is implicit — whichever scraper runs last overwrites previous data. There's no record of which source won or that a conflict existed. Two scrapers running in different order produce different results.

**Do this instead:** Use `ProvenanceTracker` + `ConflictResolver` with explicit per-source priority. Every field value carries provenance. Conflicts are logged and auditable. Merge order is deterministic regardless of scraper execution order.

### Anti-Pattern 3: In-Place Enrichment Mutation During Write

**What the project currently has:** `write_vendor_file()` calls `enrich_all()` after merging, mutating chips in-place before writing. This means enrichment occurs during the write path, not during the scrape path.

**Why it's wrong:** Write operations should be "dumb" — they persist data. Enrichment is a separate concern. Currently, calling `write_vendor_file()` triggers HTTP requests (Wikidata SPARQL for vendor knowledge), cache reads, and CPU-heavy inference — all inside what should be a simple file write.

**Do this instead:** Separate the pipeline into explicit stages:
1. `scrape` — fetch and parse, produce normalized `ChipScrapeResult`
2. `merge` — run conflict resolution, produce merged chip dicts with provenance
3. `enrich` — apply enrichment modules (can be skipped if only adding raw data)
4. `write` — persist to JSON (dumb write, no side effects)
5. `validate` — schema + index + quality checks
6. `report` — generate quality scores

### Anti-Pattern 4: Global Mutable State for Vendor Knowledge

**What the project has:** `VENDOR_KNOWLEDGE` is a module-level dict mutated in-place by `_vendor_data_wikidata.py` when `SOC_DB_USE_WIKIDATA` is set. The PROJECT.md flags this as a known issue.

**Why it's wrong:** Mutating a module-level dict means all consumers see the merged state, even if they expected the hardcoded baseline. Test isolation breaks — tests that run after Wikidata import see different data than tests before.

**Do this instead:** Make vendor knowledge an explicit dependency injected into enrichment functions. The enrichment pipeline accepts an optional `vendor_knowledge` parameter. When absent, it reads from the immutable baseline. The Wikidata merge creates a new dict rather than mutating the global. The `_vendor_data_wikidata.py` module returns a new merged dict rather than calling `.clear()` + `.update()`.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Wikipedia (en.wikipedia.org) | HTTP GET via `soc_db.common.fetch()` with TTL cache | Wikipedia rate limits: 1 req/s. Cache TTL 86400s. No auth. |
| Linux Kernel GitHub (torvalds/linux) | GitHub API: GET /git/trees/master?recursive=1 | Cache TTL 604800s (weekly). DTS filenames don't change often. |
| Wikidata SPARQL | SPARQLWrapper via `soc_db.wikidata` | Exponential backoff. Query timeout 60s. TTL caching. Requires `SOC_DB_USE_WIKIDATA` or `--use-wikidata` flag. |
| Qualcomm Developer Network | Web scraping (if no API) or partner API | VENDOR SPECIFIC. May require API key. Need rate limiting: 10 req/s max. |
| MediaTek Official | Web scraping of product listing pages | VENDOR SPECIFIC. No documented API as of 2026. |
| Apple Tech Specs | Web scraping of support.apple.com | VENDOR SPECIFIC. Rate limit conservatively (1 req/s). |
| GitHub API (for auto-PR) | `gh` CLI in GHA runner | Token via `GITHUB_TOKEN` secret. Branch: `data/update-YYYYMMDD`. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| scraper source ↔ SourceRegistry | Class attribute registration (import-time or explicit) | No runtime coupling between sources |
| SourceRegistry ↔ Pipeline orchestrator | Method call: `registry.get_for_vendor("Qualcomm")` | Returns ordered list of `BaseScraper` classes |
| Pipeline orchestrator ↔ ProvenanceTracker | Instance per chip, passed into merge step | ProvenanceTracker is single-use per chip merge cycle |
| ProvenanceTracker ↔ ConflictResolver | ProvenanceTracker calls ConflictResolver.resolve() statically | ConflictResolver is stateless; ProvenanceTracker holds per-chip state |
| Pipeline orchestrator ↔ BatchEnricher | `BatchEnricher.run(chips, checkpoint_id)` | Enrichment is a "fire and wait" call; orchestrator passes all chips |
| QualityScorer ↔ data/*.json | Read-only scan after pipeline completes | QualityScorer is stateless; invoked at end of pipeline |
| Pipeline ↔ CI/GHA | Exit code 0/1; stdout summary ingested by GHA step | Quality diff posted as PR comment |

### File Boundary Map

| Directory | Pipeline Stage Reads | Pipeline Stage Writes | UI/API Reads |
|-----------|---------------------|----------------------|--------------|
| `data/*.json` | Merge + Enrich + Report | Pipeline write | API + CLI |
| `data/provenance.db` | Report | Pipeline write | (future) API |
| `data/quality_reports/` | — | Pipeline report step | API (future) |
| `data/.checkpoints/` | Enrich (resume) | Enrich (checkpoint) | — |
| `data/soc-db.db` | — | DB migration (after write) | API + CLI |
| `docs/` | — | **NEVER** | GitHub Pages |
| `schema/` | Validate | — (committed manually) | API |

## Phasing Recommendation

### Phase 1: Foundation — Scraper Framework Infrastructure

**Files created:** `scraping/__init__.py`, `scraping/base.py`, `scraping/registry.py`, `scraping/provenance.py`, `scraping/conflict.py`, `scraping/pipeline.py`

**Files modified:** `src/soc_db/__init__.py` (export scraping package)

**What:** Build the abstract scraper framework with `BaseScraper`, `SourceRegistry`, `ProvenanceTracker`, and `ConflictResolver`. Migrate ONE source (Wikipedia) to prove the pattern works. Write tests for merge logic.

**Does NOT touch GitHub Pages:** Only modifies `src/soc_db/scraping/*.py` and tests.

### Phase 2: Source Migration — Move Existing Scrapers

**Files created:** `scraping/sources/*.py` (wikipedia, apple, linux_dt, wikidata_sparql)

**Files deleted:** `scripts/scraper_*.py`, `scripts/common.py` (after migration complete)

**Files modified:** `scripts/pipeline.py` (point to new framework)

**What:** Migrate all 4 existing scraper sources from `scripts/` and `src/soc_db/scraper_*.py` into `scraping/sources/`. Each source implements `BaseScraper`. Legacy `scripts/` files become thin wrappers then are removed.

**Does NOT touch GitHub Pages:** Only modifies library code and deletes scripts.

### Phase 3: Provenance + Conflict Resolution

**Files modified:** `scraping/pipeline.py` (integrate provenance tracking), `scraping/provenance.py`, `scraping/conflict.py`

**What:** Wire `ProvenanceTracker` and `ConflictResolver` into the pipeline. Run a multi-source scrape and verify provenance is correctly stored in `data/*.json`. Update `Chip` model in `models.py` to include `provenance` field. Update `scoring.py` completeness calculation to factor in provenance (e.g., score higher for multi-sourced fields).

**Does NOT touch GitHub Pages.** Does modify `data/*.json` schema (adds `provenance` key) — but this is backward-compatible since Pydantic ignores extra fields.

### Phase 4: Batch Enrichment + Quality Scoring

**Files created:** `enrich/batch.py`, `enrich/quality.py`

**Files modified:** `enrich/scoring.py` (add per-vendor scoring), `scraping/pipeline.py` (integrate batch enrich + quality report)

**What:** `BatchEnricher` replaces the current `enrich_all()` call in the pipeline. `QualityScorer` generates per-vendor and per-field quality reports. Reports are written to `data/quality_reports/` as JSON.

**Does NOT touch GitHub Pages.** Quality reports are new files in `data/quality_reports/` — directory doesn't exist yet, no risk to `docs/`.

### Phase 5: New Source Scrapers (Data Expansion)

**Files created:** `scraping/sources/qualcomm_official.py`, `scraping/sources/mediatek_official.py`, `scraping/sources/techpedia.py`

**What:** Build new scrapers for Qualcomm Developer Network, MediaTek official listings, and Techpedia. Each must handle vendor-specific HTML structure and rate limits.

**Does NOT touch GitHub Pages.**

### Phase 6: Auto-PR CI Workflow

**Files created:** `.github/workflows/nightly-scrape.yml`

**Files modified:** None in `src/` or `data/`.

**What:** GitHub Actions workflow that runs nightly, executes the pipeline, creates a PR with data changes. Quality diff is included in PR body for human review.

**Does NOT touch GitHub Pages.** The workflow only touches `data/` and `.github/`. The `docs/` directory is explicitly excluded from any file operations in the workflow.

---

*Architecture research for: soc-db v3.0 Full SoC Coverage — Multi-Source Scraper Framework*
*Researched: 2026-07-19*
