#!/usr/bin/env python3
"""Enrich SoC data: completeness scoring, vendor knowledge, field sources.

Delegates to common.py for all enrichment logic.
"""

import json
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from soc_db.common import enrich_all


def main():
    for fpath in sorted(DATA_DIR.glob("*.json")):
        if fpath.name == "index.json":
            continue
        chips = json.loads(fpath.read_text("utf-8"))
        chips = enrich_all(chips)
        fpath.write_text(json.dumps(chips, indent=2, ensure_ascii=False) + "\n", "utf-8")
        avg = sum(c.get("completeness", 0) for c in chips) / max(len(chips), 1)
        print(f"  {fpath.name}: {len(chips)} entries, completeness {avg:.3f}")


if __name__ == "__main__":
    main()
