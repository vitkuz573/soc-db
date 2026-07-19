#!/usr/bin/env python3
"""Command-line interface for the SoC database.

Provides subcommands to list vendors, query chips, show chip details,
compute database statistics, and re-apply enrichment.
"""

import json
import logging
import sys
from typing import Any

from soc_db.common import DATA_DIR, enrich_all
from soc_db.config import settings

logger = logging.getLogger(__name__)


def _load_all_json():
    """Load all chip records from JSON data files (internal, no dual-read).

    Reads every ``.json`` file in the data directory, skipping
    ``index.json``, and returns the combined list of chip dictionaries.

    This is the JSON-only fallback path, kept for ``cmd_enrich`` which
    writes back to JSON files.

    Returns:
        list[dict]: All chips across all vendor files.
    """
    chips = []
    for fpath in sorted(DATA_DIR.glob("*.json")):
        if fpath.name == "index.json" or fpath.name.startswith("_"):
            continue
        chips.extend(json.loads(fpath.read_text("utf-8")))
    return chips


def load_all():
    """Load all chip records with dual-read (SQLite / JSON) fallback.

    When ``settings.use_json`` is ``True`` reads from JSON vendor files;
    otherwise reads from the SQLite database (auto-migrating if needed).

    Returns:
        list[dict]: All chips across all sources.
    """
    if settings.use_json:
        return _load_all_json()

    from soc_db.db.migrate import ensure_migrated
    from soc_db.db.queries import get_all as _sql_get_all

    ensure_migrated()
    return _sql_get_all()


def fmt_table(rows, headers):
    """Format tabular data as an ASCII-art table.

    Args:
        rows: Iterable of tuples/lists, one per row.
        headers: Column header strings.

    Returns:
        str: The rendered table, including separator lines.
    """
    cols = len(headers)
    widths = [len(h) for h in headers]
    for row in rows:
        for i in range(cols):
            widths[i] = max(widths[i], len(str(row[i])))
    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    lines = [sep]
    hdr = "| " + " | ".join(h.center(widths[i]) for i, h in enumerate(headers)) + " |"
    lines.append(hdr)
    lines.append(sep)
    for row in rows:
        line = "| " + " | ".join(str(row[i]).ljust(widths[i]) for i in range(cols)) + " |"
        lines.append(line)
    lines.append(sep)
    return "\n".join(lines)


def cmd_list(args):
    """Handle the ``list`` subcommand — show vendor summary.

    Prints a table (or JSON) of vendors with chip count and average
    completeness, optionally filtered by ``--vendor``.

    Args:
        args: Parsed argparse namespace with ``.vendor`` and ``.json``.
    """
    chips = load_all()
    if args.vendor:
        chips = [c for c in chips if c.get("vendor", "").lower() == args.vendor.lower()]
    vendors: dict[str, dict[str, Any]] = {}
    for c in chips:
        v = c.get("vendor", "Unknown")
        vendors.setdefault(v, {"count": 0, "completeness": []})
        vendors[v]["count"] += 1
        vendors[v]["completeness"].append(c.get("completeness", 0))
    if args.json:
        out = {
            k: {"count": v["count"], "avg_completeness": round(sum(v["completeness"]) / max(len(v["completeness"]), 1), 3)} for k, v in sorted(vendors.items())
        }
        print(json.dumps(out, indent=2))
    else:
        rows = []
        for vname, vdata in sorted(vendors.items()):
            avg = sum(vdata["completeness"]) / max(len(vdata["completeness"]), 1)
            rows.append((vname, str(vdata["count"]), f"{avg:.3f}"))
        print(fmt_table(rows, ["Vendor", "Chips", "Completeness"]))


def cmd_query(args):
    """Handle the ``query`` subcommand — search and filter chips.

    Applies all provided filters (vendor, arch, GPU, year, min-cores,
    min-ghz, completeness, full-text search) and outputs results as a
    table, JSON, or CSV.

    When ``settings.use_json`` is false and a search term is provided,
    delegates to the FTS5-backed ``search()`` from the queries module.

    Args:
        args: Parsed argparse namespace with filter and output options.
    """
    chips = load_all()
    if args.vendor:
        chips = [c for c in chips if c.get("vendor", "").lower() == args.vendor.lower()]
    if args.arch:
        chips = [c for c in chips if args.arch.lower() in c.get("architecture", "").lower()]
    if args.gpu:
        chips = [c for c in chips if args.gpu.lower() in c.get("gpu", "").lower()]
    if args.year:
        chips = [c for c in chips if c.get("year") == args.year]
    if args.min_ghz:
        min_mhz = int(args.min_ghz * 1000)
        chips = [c for c in chips if (c.get("clock_max") or 0) >= min_mhz]
    if args.min_cores:
        chips = [c for c in chips if (c.get("cores") or 0) >= args.min_cores]
    if args.completeness:
        chips = [c for c in chips if (c.get("completeness") or 0) >= args.completeness]
    if args.search:
        if settings.use_json:
            term = args.search.lower()
            chips = [c for c in chips if term in json.dumps(c).lower()]
        else:
            from soc_db.db.queries import search as _fts_search
            chips = _fts_search(args.search)
    if args.limit:
        chips = chips[: args.limit]
    if args.csv:
        import csv
        import io

        out = io.StringIO()
        w = csv.writer(out)
        fields = ["id", "name", "vendor", "model", "architecture", "cores", "process_nm", "gpu", "year", "completeness"]
        w.writerow(fields)
        for c in chips:
            w.writerow([c.get(f, "") for f in fields])
        print(out.getvalue().strip())
    elif args.json:
        print(json.dumps(chips, indent=2, ensure_ascii=False))
    else:
        rows = []
        for c in chips:
            gpu = c.get("gpu", "") or ""
            proc = f"{c.get('process_nm', '?')}nm" if c.get("process_nm") else ""
            rows.append((c.get("id", ""), c.get("name", ""), c.get("vendor", ""), str(c.get("cores", "?")), proc, gpu, str(c.get("year", ""))))
        if rows:
            print(fmt_table(rows, ["ID", "Name", "Vendor", "Cores", "Process", "GPU", "Year"]))
            print(f"\n{len(chips)} chips matched")
        else:
            print("No chips matched")


def cmd_show(args):
    """Handle the ``show`` subcommand — display a single chip.

    Looks up a chip by its ``id`` field and prints its full JSON
    representation.  Exits with code 1 if not found.

    Args:
        args: Parsed argparse namespace with ``.id``.
    """
    chips = load_all()
    match = None
    for c in chips:
        if c.get("id") == args.id:
            match = c
            break
    if not match:
        print(f"Chip '{args.id}' not found", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(match, indent=2, ensure_ascii=False))


def cmd_stats(args):
    """Handle the ``stats`` subcommand — database-level statistics.

    Computes total chips, vendors, year range, average completeness,
    and field-presence counters.  Outputs as plain text or JSON.

    When ``settings.use_json`` is false, delegates to the SQLite-backed
    ``get_stats()`` for server-side aggregation.

    Args:
        args: Parsed argparse namespace with ``.json``.
    """
    if not settings.use_json:
        from soc_db.db.queries import get_stats as _db_stats
        stats = _db_stats()
    else:
        chips = _load_all_json()
        vcount = len({c.get("vendor", "") for c in chips})
        years = [c.get("year") for c in chips if c.get("year")]
        comps = [c.get("completeness", 0) for c in chips]
        stats = {
            "total_chips": len(chips),
            "total_vendors": vcount,
            "year_min": min(years) if years else None,
            "year_max": max(years) if years else None,
            "avg_completeness": round(sum(comps) / max(len(comps), 1), 3),
            "fields_present": {
                "gpu": f"{sum(1 for c in chips if c.get('gpu'))}/{len(chips)}",
                "process_nm": f"{sum(1 for c in chips if c.get('process_nm'))}/{len(chips)}",
                "clock_max": f"{sum(1 for c in chips if c.get('clock_max'))}/{len(chips)}",
                "architecture": f"{sum(1 for c in chips if c.get('architecture'))}/{len(chips)}",
            },
        }
    if args.json:
        print(json.dumps(stats, indent=2))
    else:
        for k, v in stats.items():
            print(f"  {k}: {v}")


def cmd_enrich(args):
    """Handle the ``enrich`` subcommand — re-apply enrichment to all data.

    Reads every vendor JSON file, runs :func:`soc_db.common.enrich_all`
    on its chips, and writes the updated data back to disk.

    **Always reads/writes JSON files directly** — enrichment is a
    mutation on the JSON source of truth and bypasses SQLite.

    Args:
        args: Parsed argparse namespace (unused).
    """
    for fpath in sorted(DATA_DIR.glob("*.json")):
        if fpath.name == "index.json" or fpath.name.startswith("_"):
            continue
        chips = json.loads(fpath.read_text("utf-8"))
        enrich_all(chips)
        fpath.write_text(json.dumps(chips, indent=2, ensure_ascii=False) + "\n", "utf-8")
        logger.info("%s: %d entries enriched", fpath.name, len(chips))


def cmd_migrate(args):
    """Handle the ``migrate`` subcommand — migrate JSON data to SQLite.

    Args:
        args: Parsed argparse namespace with ``.force``.
    """
    from soc_db.db.migrate import migrate as _run_migration
    from soc_db.db.migrate import validate_migration

    result = _run_migration(force=args.force)
    print(f"Migration complete: {result['total_chips']} chips")
    if result.get("per_vendor"):
        for v, c in sorted(result["per_vendor"].items()):
            print(f"  {v}: {c}")
    validation = validate_migration()
    if validation["pass"]:
        print(f"Validation PASSED: {validation['total']} chips match JSON source")
    else:
        print(f"Validation FAILED: {len(validation['mismatches'])} mismatches")
        for m in validation["mismatches"][:5]:
            print(f"  {m['id']}.{m['field']}: expected={m['expected']}, got={m['got']}")


def cmd_wikidata_refresh(args):
    """Handle the ``wikidata-refresh`` subcommand.

    Queries Wikidata for process node, GPU, and architecture data per vendor,
    merges results into ``VENDOR_KNOWLEDGE``, and applies manual overrides.

    Args:
        args: Parsed argparse namespace with ``.dry_run``.
    """
    from soc_db.enrich._vendor_data_wikidata import merge_vendor_knowledge
    from soc_db.wikidata import refresh_vendor_knowledge

    dry_run = args.dry_run
    logger.info("Refreshing vendor knowledge from Wikidata (dry_run=%s)", dry_run)

    result = refresh_vendor_knowledge(dry_run=dry_run)
    if dry_run:
        for vendor, data in result.items():
            pmap = data.get("process_map", {})
            gmap = data.get("gpu_map", {})
            arch = data.get("architecture", "?")
            logger.info(
                "  %s: %d process mappings, %d GPU mappings, arch=%s",
                vendor,
                len(pmap),
                len(gmap),
                arch,
            )
        print(f"Dry-run complete: {len(result)} vendors with Wikidata data")
        print("Use without --dry-run to merge results into VENDOR_KNOWLEDGE")
        return

    merged = merge_vendor_knowledge(result)
    # Update the module-level VENDOR_KNOWLEDGE
    from soc_db.enrich._vendor_data import VENDOR_KNOWLEDGE

    VENDOR_KNOWLEDGE.clear()
    VENDOR_KNOWLEDGE.update(merged)
    print(f"VENDOR_KNOWLEDGE updated: {len(merged)} vendors")


def main():
    """CLI entry point — parse arguments and dispatch to the appropriate command handler."""
    from soc_db.log_config import setup_logging as _setup_logging

    _setup_logging()
    import argparse

    p = argparse.ArgumentParser(description="soc-db CLI")
    sp = p.add_subparsers(dest="cmd")

    p_list = sp.add_parser("list", help="List vendors")
    p_list.add_argument("--vendor", "-v", help="Filter by vendor")
    p_list.add_argument("--json", action="store_true", help="JSON output")

    p_query = sp.add_parser("query", help="Search chips")
    p_query.add_argument("--vendor", "-v", help="Vendor filter")
    p_query.add_argument("--arch", "-a", help="Architecture filter (substring)")
    p_query.add_argument("--gpu", "-g", help="GPU filter (substring)")
    p_query.add_argument("--year", type=int, help="Release year")
    p_query.add_argument("--min-cores", type=int, help="Minimum cores")
    p_query.add_argument("--min-ghz", type=float, help="Minimum clock GHz")
    p_query.add_argument("--completeness", type=float, help="Minimum completeness (0-1)")
    p_query.add_argument("--search", "-s", help="Full-text search")
    p_query.add_argument("--json", action="store_true", help="JSON output")
    p_query.add_argument("--csv", action="store_true", help="CSV output")
    p_query.add_argument("--limit", type=int, help="Max results")

    p_show = sp.add_parser("show", help="Show chip details")
    p_show.add_argument("id", help="Chip ID")

    p_stats = sp.add_parser("stats", help="Database statistics")
    p_stats.add_argument("--json", action="store_true", help="JSON output")

    sp.add_parser("enrich", help="Re-apply enrichment to all data")

    p_migrate = sp.add_parser("migrate", help="Migrate JSON data to SQLite database")
    p_migrate.add_argument("--force", action="store_true", help="Re-create database from scratch")

    p_wd = sp.add_parser("wikidata-refresh", help="Refresh vendor knowledge from Wikidata")
    p_wd.add_argument("--dry-run", action="store_true", help="Log results without writing")

    args = p.parse_args()
    if args.cmd == "list":
        cmd_list(args)
    elif args.cmd == "query":
        cmd_query(args)
    elif args.cmd == "show":
        cmd_show(args)
    elif args.cmd == "stats":
        cmd_stats(args)
    elif args.cmd == "enrich":
        cmd_enrich(args)
    elif args.cmd == "migrate":
        cmd_migrate(args)
    elif args.cmd == "wikidata-refresh":
        cmd_wikidata_refresh(args)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
