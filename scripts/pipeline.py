#!/usr/bin/env python3
"""
soc-db Enterprise Pipeline — fully automated scrape → enrich → validate → deploy.

Usage:
    python3 scripts/pipeline.py              # Full pipeline
    python3 scripts/pipeline.py --skip-scrape  # Enrich + validate only
    python3 scripts/pipeline.py --vendor Qualcomm  # Single vendor
"""

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA_DIR = ROOT / "data"

SCRAPERS = [
    ("scripts/scraper_wikipedia", "Wikipedia (13 vendors)", True),
    ("scripts/scraper_apple", "Apple Silicon", True),
]


def step(name: str, fn, *args, **kwargs):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")
    t0 = time.time()
    try:
        result = fn(*args, **kwargs)
        elapsed = time.time() - t0
        print(f"  ✓ Done in {elapsed:.1f}s")
        return result
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  ✗ FAILED after {elapsed:.1f}s: {e}", file=sys.stderr)
        traceback.print_exc()
        return None


def run_scraper(module_path: str, label: str, all_vendors: bool, vendor: str | None = None):
    import subprocess
    script = str(ROOT / module_path.replace(".", "/")) + ".py"
    cmd = [sys.executable, script]
    if vendor:
        cmd.append(vendor)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"{label} exited with code {result.returncode}")


def run_enrich():
    import subprocess
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "migrate.py")],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
    counts = {}
    for fpath in sorted(DATA_DIR.glob("*.json")):
        if fpath.name == "index.json":
            continue
        chips = json.loads(fpath.read_text("utf-8"))
        avg = sum(c.get("completeness", 0) for c in chips) / max(len(chips), 1)
        counts[fpath.stem] = {"count": len(chips), "completeness": round(avg, 3)}
    total = sum(c["count"] for c in counts.values())
    avg_comp = sum(c["completeness"] * c["count"] for c in counts.values()) / max(total, 1)
    print(f"  Enriched {total} entries across {len(counts)} vendors")
    print(f"  Average completeness: {avg_comp:.3f}")
    return counts


def run_validate():
    import subprocess
    result = subprocess.run(
        [sys.executable, str(ROOT / "tests" / "validate.py")],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
    return result.returncode == 0


def generate_report(counts: dict):
    print(f"\n{'='*60}")
    print(f"  Pipeline Report")
    print(f"{'='*60}")
    total = sum(c["count"] for c in counts.values())
    print(f"  Total chips: {total}")
    print(f"  Total vendors: {len(counts)}")
    print(f"  Average completeness: {sum(c['completeness']*c['count'] for c in counts.values())/max(total,1):.3f}")
    print()
    print(f"  {'Vendor':20s} {'Chips':>6s} {'Compl':>6s} {'Grade':>6s}")
    print(f"  {'-'*40}")
    for vname, vdata in sorted(counts.items()):
        comp = vdata["completeness"]
        grade = "A" if comp >= 0.5 else "B" if comp >= 0.35 else "C" if comp >= 0.25 else "D"
        print(f"  {vname:20s} {vdata['count']:6d} {comp:.3f} {grade:>6s}")
    print(f"  {'-'*40}")
    print(f"  {'TOTAL':20s} {total:6d}")
    return total


def main():
    parser = argparse.ArgumentParser(description="soc-db Enterprise Pipeline")
    parser.add_argument("--skip-scrape", action="store_true", help="Skip web scraping")
    parser.add_argument("--skip-enrich", action="store_true", help="Skip enrichment step")
    parser.add_argument("--skip-validate", action="store_true", help="Skip validation step")
    parser.add_argument("--vendor", help="Scrape single vendor only")
    args = parser.parse_args()

    t_start = time.time()
    errors = 0

    if not args.skip_scrape:
        for module_path, label, all_vendors in SCRAPERS:
            ok = step(label, run_scraper, module_path, label, all_vendors, args.vendor)
            if ok is None:
                errors += 1

    if not args.skip_enrich:
        ok = step("Enrichment", run_enrich)
        if ok is None:
            errors += 1

    if not args.skip_validate:
        ok = step("Validation & Index Build", run_validate)
        if not ok:
            errors += 1

    elapsed = time.time() - t_start
    print(f"\n{'='*60}")
    if errors:
        print(f"  Pipeline FINISHED WITH {errors} ERROR(S) in {elapsed:.1f}s ❌")
        sys.exit(1)
    else:
        print(f"  Pipeline COMPLETE in {elapsed:.1f}s ✅")


if __name__ == "__main__":
    main()
