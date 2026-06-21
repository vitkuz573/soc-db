#!/usr/bin/env python3
"""Validate all SoC database JSON files against the schema."""

import json
import sys
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCHEMA_FILE = ROOT / "schema" / "chip-schema.json"
DATA_DIR = ROOT / "data"
INDEX_FILE = DATA_DIR / "index.json"


def load_json(path):
    with open(path, "r") as f:
        return json.load(f)


def validate_schema():
    """Validate schema itself is valid JSON."""
    try:
        load_json(SCHEMA_FILE)
        print(f"  OK schema: {SCHEMA_FILE.name}")
        return True
    except json.JSONDecodeError as e:
        print(f"  FAIL schema: {e}")
        return False


def validate_data_files():
    """Validate each data file is valid JSON and has required fields."""
    required = ["id", "name", "vendor", "cores", "architecture"]
    valid_vendors = {"Qualcomm", "MediaTek", "Samsung", "HiSilicon", "Google", "Apple", "Intel", "AMD"}
    all_ok = True
    ids_seen = set()
    total = 0

    for fpath in sorted(DATA_DIR.glob("*.json")):
        if fpath.name == "index.json":
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

            if "vendor" in entry and entry["vendor"] not in valid_vendors:
                print(f"  FAIL {fpath.name}[{idx}]: unknown vendor '{entry['vendor']}'")
                file_ok = False

            if "year" in entry and not isinstance(entry["year"], int):
                print(f"  FAIL {fpath.name}[{idx}]: 'year' must be int, got {type(entry['year']).__name__}")
                file_ok = False

            if "cores" in entry and not isinstance(entry["cores"], int):
                print(f"  FAIL {fpath.name}[{idx}]: 'cores' must be int")
                file_ok = False

        if file_ok:
            print(f"  OK {fpath.name}: {len(entries)} entries")
            total += len(entries)
        else:
            all_ok = False

    return all_ok, total


def validate_index(total):
    """Validate and update index.json counts."""
    try:
        idx = load_json(INDEX_FILE)
    except json.JSONDecodeError as e:
        print(f"  FAIL index.json: {e}")
        return False

    old_total = idx.get("total", 0)
    idx["total"] = total
    idx["updated"] = "2026-06-21T09:00:00Z"

    # Count per vendor file
    for vendor_key, vendor_info in idx["vendors"].items():
        vfile = vendor_info["file"]
        fpath = DATA_DIR / vfile
        if fpath.exists():
            try:
                entries = load_json(fpath)
                vendor_info["count"] = len(entries)
            except json.JSONDecodeError:
                pass

    with open(INDEX_FILE, "w") as f:
        json.dump(idx, f, indent=2)
        f.write("\n")

    print(f"  OK index.json updated: {total} entries (was {old_total})")
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
    if not validate_index(total):
        errors += 1

    print(f"\n{'=' * 40}")
    if errors:
        print(f"FAILED: {errors} error(s)")
        sys.exit(1)
    else:
        print(f"ALL OK: {total} chips validated")


if __name__ == "__main__":
    main()
