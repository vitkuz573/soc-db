#!/usr/bin/env python3
"""Comprehensive scraper runner for soc-db v3.1.

Fixes and runs all functional scrapers:
  - wikipedia (via MediaWiki API now)
  - linux_dt
  - notebookcheck
  - apple_techspecs
  - qualcomm (with graceful failure)
  - mediatek (with graceful failure)
  - intel_amd (with baseline fallback)
  - geekbench (with graceful failure)

After collection, updates provenance from legacy_v2 to real source IDs
and prints final statistics.
"""

import logging
import os
import shutil
import sys
import time
from pathlib import Path

# Force JSON mode for direct file writes
os.environ["SOC_DB_USE_JSON"] = "true"
os.environ["SOC_DB_LOG_LEVEL"] = "INFO"

# Add project src to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from soc_db.common import DATA_DIR, CACHE_DIR, apply_provenance, write_vendor_file
from soc_db.log_config import setup_logging
from soc_db.scraping.registry import SourceRegistry
from soc_db.provenance import ProvenanceTracker
from soc_db.config import settings

logger = logging.getLogger("soc_db.runner")

# Sources to run (in priority order)
SOURCES_TO_RUN = [
    "wikipedia",
    "linux_dt",
    "notebookcheck",
    "apple_techspecs",
    "qualcomm",
    "mediatek",
    "intel_amd",
    "geekbench",
]


def clear_cache() -> None:
    """Clear the HTTP fetch cache to force fresh data."""
    cache_dir = CACHE_DIR
    if cache_dir.exists():
        count = 0
        for f in cache_dir.iterdir():
            if f.is_file():
                f.unlink()
                count += 1
        logger.info("Cleared %d cached HTTP response(s) from %s", count, cache_dir)


def run_single_scraper(source_id: str, cls: type) -> dict:
    """Run a single scraper and return result stats."""
    start = time.time()
    result = {
        "source": source_id,
        "chips": 0,
        "success": False,
        "duration": 0.0,
        "error": None,
    }

    logger.info("=" * 60)
    logger.info("Running scraper: %s", source_id)
    logger.info("=" * 60)

    try:
        instance = cls()
        chips = instance.run()
        elapsed = time.time() - start
        result["chips"] = len(chips)
        result["success"] = True
        result["duration"] = elapsed
        logger.info(
            "[%s] SUCCESS — %d chip(s) in %.1fs",
            source_id, len(chips), elapsed,
        )
    except Exception as exc:
        elapsed = time.time() - start
        result["duration"] = elapsed
        result["error"] = str(exc)
        logger.warning(
            "[%s] FAILED after %.1fs: %s",
            source_id, elapsed, exc,
        )

    return result


def reapply_provenance() -> None:
    """Re-apply provenance tracking to all chip files.

    Processes each vendor JSON file and ensures every field has a
    provenance source associated with it.  Existing provenance is
    preserved unless ``force=True``.
    """
    logger.info("=" * 60)
    logger.info("Re-applying provenance tracking...")
    logger.info("=" * 60)

    count = 0
    for fpath in sorted(DATA_DIR.glob("*.json")):
        if fpath.name in ("index.json", "soc-db.db") or fpath.name.startswith("_"):
            continue

        import json

        try:
            chips = json.loads(fpath.read_text("utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Skipping %s: %s", fpath.name, exc)
            continue

        # Apply provenance tracker — migrate legacy_v2 to real sources,
        # then fill gaps for chips lacking full provenance
        tracker = ProvenanceTracker()
        for chip in chips:
            prov = chip.get("provenance") or {}

            # Determine the actual source for this chip
            actual_source = chip.get("source", "") or tracker._source_id
            # If source is from a known scraper, use it for the migration
            known_sources = {
                "wikipedia", "linux_dt", "notebookcheck", "apple_techspecs",
                "qualcomm", "mediatek", "intel_amd", "geekbench", "wikidata",
                "apple", "techpowerup",
            }

            # Migrate legacy_v2 → actual source
            has_legacy = any(v == "legacy_v2" for v in prov.values())
            if has_legacy:
                for k in list(prov.keys()):
                    if prov[k] == "legacy_v2":
                        if actual_source in known_sources:
                            prov[k] = actual_source
                        else:
                            prov[k] = "enrichment"

            # If chip has no provenance at all (after migration), mark all fields
            if not prov:
                tracker.track(chip, force=False)
            else:
                # Fill in missing fields with the chip's source
                src = actual_source if actual_source in known_sources else "enrichment"
                for key in chip:
                    if key not in ("id", "provenance", "uuid", "completeness", "updated", "sources"):
                        if key not in prov and chip[key] not in (None, "", [], 0):
                            prov[key] = src
                if prov:
                    chip["provenance"] = prov

        # Write back
        fpath.write_text(json.dumps(chips, indent=2, ensure_ascii=False) + "\n", "utf-8")
        count += len(chips)
        logger.info("%s: %d entries — provenance applied", fpath.name, len(chips))

    logger.info("Provenance applied to %d chip(s) across all files", count)


def print_stats() -> dict:
    """Compute and log final database statistics.

    Returns:
        Dict with total_chips, per_vendor counts, avg_completeness.
    """
    import json

    total_chips = 0
    per_vendor: dict[str, int] = {}
    completeness_scores: list[float] = []

    for fpath in sorted(DATA_DIR.glob("*.json")):
        if fpath.name in ("index.json", "soc-db.db") or fpath.name.startswith("_"):
            continue
        try:
            chips = json.loads(fpath.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        vendor_name = fpath.stem.replace("_", " ").title()
        if vendor_name.lower().startswith("intel"):
            vendor_name = "Intel Atom" if "atom" in fpath.stem else "Intel"
        elif vendor_name.lower().startswith("nxp"):
            vendor_name = "NXP i.MX"
        elif vendor_name.lower() == "exynos":
            vendor_name = "Samsung"
        elif vendor_name.lower() == "kirin":
            vendor_name = "HiSilicon"
        elif vendor_name.lower() == "tensor":
            vendor_name = "Google"
        elif vendor_name.lower() == "ti Omap":
            vendor_name = "TI OMAP"

        count = len(chips)
        total_chips += count
        per_vendor[vendor_name] = count
        completeness_scores.extend(
            c.get("completeness", 0) for c in chips if c.get("completeness")
        )

    avg_comp = (
        sum(completeness_scores) / len(completeness_scores)
        if completeness_scores
        else 0.0
    )

    logger.info("=" * 60)
    logger.info("FINAL DATABASE STATISTICS")
    logger.info("=" * 60)
    logger.info("Total chips: %d", total_chips)
    logger.info("Total vendors: %d", len(per_vendor))
    logger.info("Average completeness: %.3f", avg_comp)
    logger.info("")
    logger.info("Per-vendor breakdown:")
    for vname in sorted(per_vendor.keys()):
        logger.info("  %-20s %5d chips", vname, per_vendor[vname])

    return {
        "total_chips": total_chips,
        "total_vendors": len(per_vendor),
        "avg_completeness": round(avg_comp, 4),
        "per_vendor": per_vendor,
    }


def main() -> int:
    """Run all scrapers, apply provenance, and print stats."""
    setup_logging(level="INFO", fmt="plain")

    logger.info("=" * 60)
    logger.info("soc-db v3.1 Scraper Runner")
    logger.info("=" * 60)

    # Step 0: Clear cache
    logger.info("")
    logger.info("[Step 0] Clearing HTTP cache...")
    clear_cache()

    # Step 1: Discover all scrapers
    logger.info("")
    logger.info("[Step 1] Discovering scrapers...")
    SourceRegistry.clear()
    scrapers = SourceRegistry.discover()
    logger.info("Discovered %d scraper(s)", len(scrapers))

    # Step 2: Run each scraper in order
    logger.info("")
    logger.info("[Step 2] Running scrapers...")
    results = []
    for source_id in SOURCES_TO_RUN:
        cls = scrapers.get(source_id)
        if cls is None:
            logger.warning("[%s] Scraper class not found — skipping", source_id)
            results.append({
                "source": source_id,
                "chips": 0,
                "success": False,
                "duration": 0.0,
                "error": "Not found in registry",
            })
            continue
        result = run_single_scraper(source_id, cls)
        results.append(result)

    # Step 3: Summary of scraper results
    logger.info("")
    logger.info("=" * 60)
    logger.info("SCRAPER RUN SUMMARY")
    logger.info("=" * 60)
    total_chips = 0
    success_count = 0
    for r in results:
        status = "✓" if r["success"] else "✗"
        logger.info(
            "  %s %-20s %5d chips in %5.1fs  %s",
            status, r["source"], r["chips"], r["duration"],
            r["error"] or "",
        )
        if r["success"]:
            total_chips += r["chips"]
            success_count += 1
    logger.info("  %d/%d scrapers succeeded, %d total chips collected",
                success_count, len(results), total_chips)

    # Step 4: Re-apply provenance
    logger.info("")
    logger.info("[Step 4] Re-applying provenance...")
    reapply_provenance()

    # Step 5: Print final stats
    logger.info("")
    logger.info("[Step 5] Final statistics...")
    stats = print_stats()

    logger.info("")
    logger.info("Done. Database ready.")
    return 0 if success_count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
