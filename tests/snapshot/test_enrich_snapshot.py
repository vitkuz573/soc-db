"""Snapshot test for enrichment — ensures zero regression across ALL chips.

Compares the current enrichment output against a deterministic reference
file captured before any refactoring. Run with ``--update-snapshot`` to
regenerate the reference when intentional changes are made.
"""

import json
from pathlib import Path

from soc_db.common import enrich_one

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent
DATA_DIR = PROJECT / "data"
PHASE_DIR = PROJECT / ".planning" / "phases" / "01-refac-enrichment-module-extraction"
REFERENCE_FILE = PHASE_DIR / "expected_enrichment.json"


def load_all_chips():
    """Load ALL chips from all vendor JSON files (excluding index.json)."""
    chips = []
    for path in sorted(DATA_DIR.glob("*.json")):
        if path.name == "index.json":
            continue
        chips.extend(json.loads(path.read_text("utf-8")))
    return chips


def test_enrich_snapshot_matches():
    """Enrich every chip and compare against the reference snapshot."""
    chips = load_all_chips()
    if not REFERENCE_FILE.exists():
        # First run — write reference file and pass
        enriched = [enrich_one(c) for c in chips]
        enriched.sort(key=lambda c: (c.get("vendor", ""), c.get("id", "")))
        PHASE_DIR.mkdir(parents=True, exist_ok=True)
        REFERENCE_FILE.write_text(
            json.dumps(enriched, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return

    with open(REFERENCE_FILE) as f:
        expected = json.load(f)

    enriched = [enrich_one(c) for c in chips]
    enriched.sort(key=lambda c: (c.get("vendor", ""), c.get("id", "")))

    assert len(enriched) == len(expected), (
        f"Chip count mismatch: {len(enriched)} vs {len(expected)}. "
        "Run with --update-snapshot if intentional."
    )

    for i, (got, exp) in enumerate(zip(enriched, expected)):
        assert got == exp, (
            f"Chip {i} ({got.get('vendor', '?')}/{got.get('id', '?')}) "
            f"differs from reference. Run with --update-snapshot if intentional."
        )


if __name__ == "__main__":
    import sys

    if "--update-snapshot" in sys.argv:
        chips = load_all_chips()
        enriched = [enrich_one(c) for c in chips]
        enriched.sort(key=lambda c: (c.get("vendor", ""), c.get("id", "")))
        PHASE_DIR.mkdir(parents=True, exist_ok=True)
        REFERENCE_FILE.write_text(
            json.dumps(enriched, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Snapshot updated: {len(enriched)} chips → {REFERENCE_FILE}")
    else:
        test_enrich_snapshot_matches()
        print("Snapshot test PASSED")
