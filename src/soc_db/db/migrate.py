"""JSON-to-SQLite migration tool.

Provides ``migrate()`` to populate the SQLite database from the JSON
vendor files, ``validate_migration()`` to verify data integrity, and
``ensure_migrated()`` for auto-migration on first use.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from soc_db.common import DATA_DIR
from soc_db.config import settings
from soc_db.db.connection import get_connection
from soc_db.db.schema import create_tables, drop_tables, rebuild_fts

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Columns that are stored as JSON text in SQLite
# ---------------------------------------------------------------------------
_JSON_COLUMNS = frozenset({
    "aliases", "gpu_api", "devices", "alternative_names", "tags",
    "cache", "rating", "benchmarks", "sources",
})

# Chip model fields that are dates stored as ISO text
_DATE_FIELDS = frozenset({"announced", "updated"})

# All SQL column names (from schema.CHIPS_TABLE_DDL)
_CHIP_COLUMNS = [
    "id", "name", "vendor", "model", "aliases", "codename", "description",
    "architecture", "isa", "cores", "threads", "cluster_config",
    "clock_max", "clock_mid", "clock_min", "max_freq", "process_nm",
    "process_name", "process", "cache", "tdp", "gpu", "gpu_clock",
    "gpu_api", "gpu_tflops", "memory_type", "memory_max", "memory_clock",
    "memory_bus", "memory_bandwidth", "storage_type", "npu", "ai_ops",
    "modem", "modem_dl", "modem_ul", "cellular", "video_decode",
    "video_encode", "display_max", "camera_max", "isps", "video_capture",
    "wifi", "bluetooth", "connectivity", "dsp", "usb", "navigation", "charging", "year",
    "announced", "revision", "status", "completeness", "source",
    "sources", "updated", "datasheet_url", "wikipedia_url", "wikidata_id",
    "linux_dt_compatible", "devices", "alternative_names", "parent",
    "tags", "rating", "benchmarks",
]

_BATCH_SIZE = 500


def _chip_to_row(chip: dict[str, Any]) -> dict[str, Any]:
    """Map a chip dict to a row dict suitable for SQL INSERT.

    Serialises list/dict fields to JSON, converts dates to ISO strings,
    and passes through scalar values as-is.  All columns are included —
    missing values are set to ``None`` (SQL NULL).
    """
    row: dict[str, Any] = {}
    for col in _CHIP_COLUMNS:
        val = chip.get(col)
        if val is None:
            row[col] = None
        elif col in _JSON_COLUMNS:
            row[col] = json.dumps(val, ensure_ascii=False)
        elif col in _DATE_FIELDS:
            row[col] = str(val)
        else:
            row[col] = val
    return row


def _load_all_json_chips() -> list[dict[str, Any]]:
    """Load all chips from JSON vendor files (migration source)."""
    chips: list[dict[str, Any]] = []
    for fpath in sorted(DATA_DIR.glob("*.json")):
        if fpath.name == "index.json" or fpath.name.startswith("_"):
            continue
        chips.extend(json.loads(fpath.read_text("utf-8")))
    return chips


def migrate(db_path: Path | None = None, force: bool = False) -> dict[str, Any]:
    """Migrate all JSON vendor files to SQLite.

    Args:
        db_path: Path to the SQLite database.  ``None`` uses
            ``settings.db_path``.
        force: If ``True``, drop existing tables and re-create them.

    Returns:
        Dict with migration stats::

            {
                "total_chips": int,
                "per_vendor": {str: int},
                "db_path": str,
            }

    Raises:
        RuntimeError: If no JSON vendor files are found.
    """
    if db_path is None:
        db_path = settings.db_path
    db_path = Path(db_path).resolve()

    # Load all JSON data
    all_chips = _load_all_json_chips()
    if not all_chips:
        raise RuntimeError("No JSON vendor files found — cannot migrate")

    conn = get_connection(db_path)

    if force:
        drop_tables(conn)
    create_tables(conn)

    # Check if data already exists (idempotent skip)
    existing = conn.execute("SELECT COUNT(*) FROM chips").fetchone()[0]
    if existing > 0 and not force:
        logger.info("Database already has %d chips — skipping migration", existing)
        conn.close()
        return {
            "total_chips": existing,
            "per_vendor": {},
            "db_path": str(db_path),
        }

    # Group chips by vendor for per-vendor tracking
    vendor_chips: dict[str, list[dict[str, Any]]] = {}
    for chip in all_chips:
        v = chip.get("vendor", "Unknown")
        vendor_chips.setdefault(v, []).append(chip)

    # Begin transaction
    conn.execute("BEGIN")

    try:
        total = 0
        per_vendor: dict[str, int] = {}
        columns = _CHIP_COLUMNS
        placeholders = ", ".join([f":{c}" for c in columns])
        col_names = ", ".join(columns)

        for vendor_name, chips in vendor_chips.items():
            rows = [_chip_to_row(c) for c in chips]
            for i in range(0, len(rows), _BATCH_SIZE):
                batch = rows[i: i + _BATCH_SIZE]
                conn.executemany(
                    f"INSERT OR REPLACE INTO chips ({col_names}) VALUES ({placeholders})",
                    batch,
                )
            per_vendor[vendor_name] = len(chips)
            total += len(chips)

        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        conn.close()
        raise

    # Rebuild FTS5 index
    rebuild_fts(conn)
    conn.close()

    logger.info("Migration complete: %d chips migrated to %s", total, db_path)

    return {
        "total_chips": total,
        "per_vendor": per_vendor,
        "db_path": str(db_path),
    }


def validate_migration(db_path: Path | None = None) -> dict[str, Any]:
    """Validate SQLite data against JSON source.

    Compares every field of every chip between JSON and SQLite backends.

    Args:
        db_path: Path to the SQLite database.  ``None`` uses
            ``settings.db_path``.

    Returns:
        Dict with validation results::

            {
                "pass": bool,
                "total": int,
                "mismatches": [{id, field, expected, got}],
                "missing_ids": [str],
                "extra_ids": [str],
            }
    """
    if db_path is None:
        db_path = settings.db_path
    db_path = Path(db_path).resolve()

    from soc_db.db.connection import get_connection as _get_conn
    from soc_db.db.queries import get_all as _sql_get_all

    # Load from both sources
    json_chips = _load_all_json_chips()
    sql_conn = _get_conn(db_path)
    sql_chips = _sql_get_all(conn=sql_conn)
    sql_conn.close()

    json_by_id: dict[str, dict[str, Any]] = {c["id"]: c for c in json_chips}
    sql_by_id: dict[str, dict[str, Any]] = {c["id"]: c for c in sql_chips}

    json_ids = set(json_by_id.keys())
    sql_ids = set(sql_by_id.keys())

    missing_ids = sorted(json_ids - sql_ids)
    extra_ids = sorted(sql_ids - json_ids)

    mismatches: list[dict[str, Any]] = []
    common_ids = json_ids & sql_ids

    for chip_id in sorted(common_ids):
        jc = json_by_id[chip_id]
        sc = sql_by_id[chip_id]
        all_fields = set(jc.keys()) | set(sc.keys())
        for field in sorted(all_fields):
            expected = jc.get(field)
            got = sc.get(field)
            # Normalise types for comparison
            if isinstance(expected, (list, dict)):
                expected_norm = json.dumps(expected, sort_keys=True, ensure_ascii=False)
                got_norm = json.dumps(got, sort_keys=True, ensure_ascii=False) if got is not None else None
            else:
                expected_norm = expected
                got_norm = got

            if expected_norm != got_norm:
                mismatches.append({
                    "id": chip_id,
                    "field": field,
                    "expected": expected_norm,
                    "got": got_norm,
                })

    passed = len(mismatches) == 0 and len(missing_ids) == 0 and len(extra_ids) == 0

    return {
        "pass": passed,
        "total": len(common_ids),
        "mismatches": mismatches,
        "missing_ids": missing_ids,
        "extra_ids": extra_ids,
    }


def ensure_migrated(db_path: Path | None = None) -> bool:
    """Ensure the database exists and is migrated.

    If the database file doesn't exist or the chips table is empty, runs
    the migration automatically.  Safe to call on every query.

    Args:
        db_path: Path to the SQLite database.

    Returns:
        ``True`` if the database is ready for queries.
    """
    if db_path is None:
        db_path = settings.db_path
    db_path = Path(db_path).resolve()

    if not db_path.exists():
        logger.info("Database %s not found — auto-migrating", db_path)
        migrate(db_path)
        return True

    # Check if chips table has data
    try:
        conn = get_connection(db_path)
        count = conn.execute("SELECT COUNT(*) FROM chips").fetchone()[0]
        conn.close()
        if count == 0:
            logger.info("Database %s is empty — auto-migrating", db_path)
            migrate(db_path, force=True)
        return True
    except Exception:
        logger.exception("Error checking database %s — re-migrating", db_path)
        migrate(db_path, force=True)
        return True
