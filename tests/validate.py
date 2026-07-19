#!/usr/bin/env python3
"""Validate all SoC database JSON files against the schema."""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCHEMA_FILE = ROOT / "schema" / "chip-schema.json"
DATA_DIR = ROOT / "data"
INDEX_FILE = DATA_DIR / "index.json"


def load_json(path):
    with open(path) as f:
        return json.load(f)


def validate_schema():
    try:
        load_json(SCHEMA_FILE)
        print(f"  OK schema: {SCHEMA_FILE.name}")
        return True
    except json.JSONDecodeError as e:
        print(f"  FAIL schema: {e}")
        return False


def validate_data_files():
    required = ["id", "name", "vendor"]
    all_ok = True
    ids_seen = set()
    total = 0

    for fpath in sorted(DATA_DIR.glob("*.json")):
        if fpath.name == "index.json" or fpath.name.startswith("_") or fpath.name == "vendor_overrides.json":
            continue
        try:
            entries = load_json(fpath)
        except json.JSONDecodeError as e:
            print(f"  FAIL {fpath.name}: invalid JSON — {e}")
            all_ok = False
            continue
        if not isinstance(entries, list):
            print(f"  FAIL {fpath.name}: root must be an array")
            all_ok = False
            continue
        file_ok = True
        for idx, entry in enumerate(entries):
            for field in required:
                if field not in entry:
                    print(f"  FAIL {fpath.name}[{idx}]: missing field '{field}'")
                    file_ok = False
            if "id" in entry:
                if entry["id"] in ids_seen:
                    print(f"  FAIL {fpath.name}[{idx}]: duplicate id '{entry['id']}'")
                    file_ok = False
                ids_seen.add(entry["id"])
            if "year" in entry and not isinstance(entry["year"], int):
                print(f"  FAIL {fpath.name}[{idx}]: 'year' must be int")
                file_ok = False
            if "cores" in entry and entry["cores"] is not None and not isinstance(entry["cores"], int):
                print(f"  FAIL {fpath.name}[{idx}]: 'cores' must be int")
                file_ok = False
        if file_ok:
            print(f"  OK {fpath.name}: {len(entries)} entries")
            total += len(entries)
        else:
            all_ok = False
    return all_ok, total


def build_index(total):
    vendor_files = {}
    for fpath in sorted(DATA_DIR.glob("*.json")):
        if fpath.name == "index.json" or fpath.name.startswith("_") or fpath.name == "vendor_overrides.json":
            continue
        try:
            entries = load_json(fpath)
        except json.JSONDecodeError as e:
            print(f"  FAIL {fpath.name}: invalid JSON — {e}")
            continue
        if not entries:
            continue
        vendor_name = entries[0].get("vendor", fpath.stem.title())
        key = vendor_name.lower().replace(" ", "_")
        avg_comp = round(sum(c.get("completeness", 0) for c in entries) / max(len(entries), 1), 3) if entries else 0
        vendor_files[key] = {
            "name": vendor_name,
            "file": fpath.name,
            "count": len(entries),
            "completeness": avg_comp,
        }
    idx = {
        "version": "2.0.0",
        "updated": "2026-06-21",
        "vendors": dict(sorted(vendor_files.items())),
        "total": total,
        "spec": "https://vitkuz573.github.io/soc-db/schema/chip-schema.json",
    }
    INDEX_FILE.write_text(json.dumps(idx, indent=2) + "\n")
    print(f"  OK index.json updated: {total} entries, {len(vendor_files)} vendors")
    return True


def main():
    errors = 0
    print("Validating schema...")
    if not validate_schema():
        errors += 1
    print("\nValidating data files...")
    data_ok, total = validate_data_files()
    if not data_ok:
        errors += 1
    print("\nUpdating index...")
    if not build_index(total):
        errors += 1
    print(f"\n{'=' * 40}")
    if errors:
        print(f"FAILED: {errors} error(s)")
        sys.exit(1)
    else:
        print(f"ALL OK: {total} chips validated")


if __name__ == "__main__":
    main()
