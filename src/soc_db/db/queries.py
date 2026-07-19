"""Query functions with dual-read (SQLite / JSON) fallback.

Every public function checks ``settings.use_json`` and either runs a
SQLite query or falls back to loading from the JSON vendor files via
``cli._load_all_json()``.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

import aiosqlite

from soc_db.config import settings

# ---------------------------------------------------------------------------
# Columns that are stored as JSON text in SQLite
# ---------------------------------------------------------------------------
_JSON_COLUMNS = frozenset({
    "aliases",
    "gpu_api",
    "devices",
    "alternative_names",
    "tags",
    "cache",
    "rating",
    "benchmarks",
    "sources",
    "provenance",
})


def _ensure_conn(conn: sqlite3.Connection | None) -> sqlite3.Connection:
    """Return *conn* or the cached connection."""
    if conn is not None:
        return conn
    from soc_db.db.connection import get_connection_cached

    return get_connection_cached()


def _load_json_fallback() -> list[dict[str, Any]]:
    """Load all chips from JSON vendor files (dual-read fallback)."""
    from soc_db.cli import _load_all_json

    return _load_all_json()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a SQLite row to a dict, deserialising JSON columns.

    NULL columns are omitted from the returned dict (matching JSON file
    semantics where absent keys produce None in Pydantic).
    """
    result: dict[str, Any] = {}
    for key in row.keys():  # noqa: SIM118 — sqlite3.Row doesn't iterate keys
        val = row[key]
        if val is None:
            continue
        if key in _JSON_COLUMNS:
            val = json.loads(val)
        result[key] = val
    return result


def _ensure_migrated() -> None:
    """Auto-migrate if the database does not exist yet."""
    from soc_db.db.migrate import ensure_migrated as _em

    _em()


# ---------------------------------------------------------------------------
# Public query API
# ---------------------------------------------------------------------------


def get_all(conn: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    """Return all chips sorted by vendor, name.

    Args:
        conn: Optional SQLite connection.  ``None`` uses the cached one.

    Returns:
        List of chip dicts.
    """
    if settings.use_json:
        return _load_json_fallback()

    _ensure_migrated()
    c = _ensure_conn(conn)
    rows = c.execute("SELECT * FROM chips ORDER BY vendor, name").fetchall()
    return [_row_to_dict(r) for r in rows]


def get_by_id(chip_id: str, conn: sqlite3.Connection | None = None) -> dict[str, Any] | None:
    """Return a single chip by its ``id`` field.

    Args:
        chip_id: The chip identifier.
        conn: Optional SQLite connection.

    Returns:
        Chip dict or ``None`` if not found.
    """
    if settings.use_json:
        chips = _load_json_fallback()
        for c in chips:
            if c.get("id") == chip_id:
                return c
        return None

    _ensure_migrated()
    c = _ensure_conn(conn)
    row = c.execute("SELECT * FROM chips WHERE id = ?", (chip_id,)).fetchone()
    return _row_to_dict(row) if row else None


def search(query: str, conn: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    """Full-text search across all text-searchable fields.

    Uses FTS5 MATCH against ``chips_fts`` when ``use_json`` is false.
    Multi-word queries are joined with `` AND `` so that all terms must
    match.  Falls back to LIKE-based search on FTS5 syntax errors.

    When ``use_json`` is true, falls back to a linear substring match
    over the JSON serialisation of each chip.

    Args:
        query: The search string.
        conn: Optional SQLite connection.

    Returns:
        List of matching chip dicts.
    """
    if settings.use_json:
        ql = query.lower()
        chips = _load_json_fallback()
        return [c for c in chips if ql in json.dumps(c).lower()]

    _ensure_migrated()
    c = _ensure_conn(conn)

    # Build FTS5 MATCH expression — join tokens with AND
    tokens = query.strip().split()
    if not tokens:
        return []
    fts_query = " AND ".join(tokens)

    try:
        rows = c.execute(
            "SELECT chips.* FROM chips JOIN chips_fts ON chips.rowid = chips_fts.rowid WHERE chips_fts MATCH ? ORDER BY rank",
            (fts_query,),
        ).fetchall()
    except sqlite3.OperationalError:
        like_clauses: list[str] = []
        like_params: list[str] = []
        for token in tokens:
            like_clauses.append("(name LIKE ? OR vendor LIKE ? OR model LIKE ? OR description LIKE ?)")
            like_params.extend([f"%{token}%"] * 4)
        like_exprs = " AND ".join(like_clauses)
        rows = c.execute(f"SELECT * FROM chips WHERE {like_exprs}", like_params).fetchall()  # nosec B608 — parameters are ?-placeholders, not injected

    return [_row_to_dict(r) for r in rows]


def get_vendors(conn: sqlite3.Connection | None = None) -> dict[str, dict[str, Any]]:
    """Return vendor summary with chip counts and average completeness.

    Args:
        conn: Optional SQLite connection.

    Returns:
        Dict mapping vendor name to ``{count, avg_completeness}``.
    """
    if settings.use_json:
        chips = _load_json_fallback()
        vendors: dict[str, dict[str, Any]] = {}
        for c in chips:
            v = c.get("vendor", "Unknown")
            vendors.setdefault(v, {"count": 0, "completeness": []})
            vendors[v]["count"] += 1
            vendors[v]["completeness"].append(c.get("completeness", 0))
        result = {}
        for vname, vdata in sorted(vendors.items()):
            avg = sum(vdata["completeness"]) / max(len(vdata["completeness"]), 1)
            result[vname] = {"count": vdata["count"], "avg_completeness": round(avg, 3)}
        return result

    _ensure_migrated()
    c = _ensure_conn(conn)
    rows = c.execute("SELECT vendor, COUNT(*) AS count, AVG(COALESCE(completeness, 0)) AS avg_comp FROM chips GROUP BY vendor ORDER BY vendor").fetchall()
    return {r["vendor"]: {"count": r["count"], "avg_completeness": round(r["avg_comp"], 3)} for r in rows}


def get_stats(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Return database-wide aggregate statistics.

    Returns:
        Dict with keys: ``total_chips``, ``total_vendors``, ``year_min``,
        ``year_max``, ``avg_completeness``, ``fields_present``.
    """
    if settings.use_json:
        chips = _load_json_fallback()
        vcount = len({c.get("vendor", "") for c in chips})
        years = [c.get("year") for c in chips if c.get("year")]
        comps = [c.get("completeness", 0) for c in chips]
        return {
            "total_chips": len(chips),
            "total_vendors": vcount,
            "year_min": min(years) if years else None,
            "year_max": max(years) if years else None,
            "avg_completeness": round(sum(comps) / max(len(comps), 1), 3),
            "fields_present": {
                "gpu": sum(1 for c in chips if c.get("gpu")),
                "process_nm": sum(1 for c in chips if c.get("process_nm")),
                "clock_max": sum(1 for c in chips if c.get("clock_max")),
                "architecture": sum(1 for c in chips if c.get("architecture")),
            },
        }

    _ensure_migrated()
    c = _ensure_conn(conn)
    row = c.execute(
        "SELECT COUNT(*) AS total_chips, "
        "COUNT(DISTINCT vendor) AS total_vendors, "
        "MIN(year) AS year_min, "
        "MAX(year) AS year_max, "
        "AVG(COALESCE(completeness, 0)) AS avg_completeness, "
        "SUM(CASE WHEN gpu IS NOT NULL THEN 1 ELSE 0 END) AS gpu_present, "
        "SUM(CASE WHEN process_nm IS NOT NULL THEN 1 ELSE 0 END) AS process_nm_present, "
        "SUM(CASE WHEN clock_max IS NOT NULL THEN 1 ELSE 0 END) AS clock_max_present, "
        "SUM(CASE WHEN architecture IS NOT NULL THEN 1 ELSE 0 END) AS architecture_present "
        "FROM chips"
    ).fetchone()
    total = row["total_chips"]
    return {
        "total_chips": total,
        "total_vendors": row["total_vendors"],
        "year_min": row["year_min"],
        "year_max": row["year_max"],
        "avg_completeness": round(row["avg_completeness"], 3),
        "fields_present": {
            "gpu": f"{row['gpu_present']}/{total}",
            "process_nm": f"{row['process_nm_present']}/{total}",
            "clock_max": f"{row['clock_max_present']}/{total}",
            "architecture": f"{row['architecture_present']}/{total}",
        },
    }


def _search_chips_json(chips: list[dict[str, Any]], q: str) -> list[dict[str, Any]]:
    """Linear substring search over JSON serialisation (JSON fallback)."""
    ql = q.lower()
    return [c for c in chips if ql in json.dumps(c).lower()]


def filter_chips(
    *,
    vendor: str | None = None,
    arch: str | None = None,
    gpu: str | None = None,
    year: int | None = None,
    min_cores: int | None = None,
    min_ghz: float | None = None,
    completeness: float | None = None,
    search_query: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    sort: str | None = None,
    order: str = "asc",
    conn: sqlite3.Connection | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Combined filter + search with pagination.

    Builds a dynamic SQL WHERE clause from provided filters, uses FTS5
    for *search_query* when available.  SQL injection safe — all values
    passed through ``?`` parameters.

    Args:
        vendor: Exact vendor name filter.
        arch: Architecture substring match.
        gpu: GPU substring match.
        year: Exact release year.
        min_cores: Minimum core count.
        min_ghz: Minimum clock speed in GHz.
        completeness: Minimum completeness score (0-1).
        search_query: Full-text search string.
        limit: Maximum results to return.
        offset: Pagination offset.
        sort: Field to sort by.
        order: Sort direction (``asc`` / ``desc``).
        conn: Optional SQLite connection.

    Returns:
        ``(chips_list, total_count)`` tuple.
    """
    if settings.use_json:
        chips = _load_json_fallback()
        if vendor:
            chips = [c for c in chips if c.get("vendor", "").lower() == vendor.lower()]
        if arch:
            chips = [c for c in chips if arch.lower() in c.get("architecture", "").lower()]
        if gpu:
            chips = [c for c in chips if gpu.lower() in c.get("gpu", "").lower()]
        if year:
            chips = [c for c in chips if c.get("year") == year]
        if min_cores:
            chips = [c for c in chips if (c.get("cores") or 0) >= min_cores]
        if min_ghz:
            min_mhz = int(min_ghz * 1000)
            chips = [c for c in chips if (c.get("clock_max") or 0) >= min_mhz]
        if completeness:
            chips = [c for c in chips if (c.get("completeness") or 0) >= completeness]
        if search_query:
            chips = _search_chips_json(chips, search_query)
        if sort:
            reverse = order == "desc"
            chips = sorted(chips, key=lambda c: c.get(sort, "") or "", reverse=reverse)
        total = len(chips)
        chips = chips[offset : offset + limit] if limit else chips[offset:]
        return chips, total

    # --- SQLite path ---
    _ensure_migrated()
    c = _ensure_conn(conn)

    where_clauses: list[str] = []
    params: list[Any] = []

    if vendor:
        where_clauses.append("LOWER(vendor) = LOWER(?)")
        params.append(vendor)
    if arch:
        where_clauses.append("LOWER(architecture) LIKE '%' || LOWER(?) || '%'")
        params.append(arch)
    if gpu:
        where_clauses.append("LOWER(gpu) LIKE '%' || LOWER(?) || '%'")
        params.append(gpu)
    if year:
        where_clauses.append("year = ?")
        params.append(year)
    if min_cores:
        where_clauses.append("COALESCE(cores, 0) >= ?")
        params.append(min_cores)
    if min_ghz:
        min_mhz = int(min_ghz * 1000)
        where_clauses.append("COALESCE(clock_max, 0) >= ?")
        params.append(min_mhz)
    if completeness:
        where_clauses.append("COALESCE(completeness, 0) >= ?")
        params.append(completeness)

    # Search via FTS5
    fts_join = ""
    fts_clause: str | None = None
    if search_query:
        tokens = search_query.strip().split()
        if tokens:
            fts_query = " AND ".join(tokens)
            fts_join = " JOIN chips_fts ON chips.rowid = chips_fts.rowid"
            fts_clause = "chips_fts MATCH ?"
            params.append(fts_query)

    all_clauses = list(where_clauses)
    if fts_clause:
        all_clauses.append(fts_clause)
    where_sql = " WHERE " + " AND ".join(all_clauses) if all_clauses else ""

    # Count
    count_row = c.execute(f"SELECT COUNT(*) FROM chips{fts_join}{where_sql}", params).fetchone()  # nosec B608 — params are ?-placeholders
    total = count_row[0]

    # Sort
    order_sql = ""
    if sort:
        direction = "DESC" if order == "desc" else "ASC"
        order_sql = f' ORDER BY "{sort}" {direction}'

    # Paginate
    limit_sql = ""
    limit_params: list[Any] = []
    if limit is not None:
        limit_sql = " LIMIT ? OFFSET ?"
        limit_params = [limit, offset]

    rows = c.execute(
        f"SELECT chips.* FROM chips{fts_join}{where_sql}{order_sql}{limit_sql}",  # nosec B608 — params are ?-placeholders
        params + limit_params,
    ).fetchall()

    return [_row_to_dict(r) for r in rows], total


# ---------------------------------------------------------------------------
# Async query API (aiosqlite)
# ---------------------------------------------------------------------------


async def _ensure_async_conn(conn: aiosqlite.Connection | None) -> aiosqlite.Connection:
    """Return *conn* or acquire one from the async connection pool."""
    if conn is not None:
        return conn
    from soc_db.db.connection import get_async_connection

    pool = get_async_connection()
    return await pool.acquire()


async def get_all_async(conn: aiosqlite.Connection | None = None) -> list[dict[str, Any]]:
    """Async: return all chips sorted by vendor, name.

    Args:
        conn: Optional aiosqlite connection.  ``None`` acquires from the pool.

    Returns:
        List of chip dicts.
    """
    if settings.use_json:
        return _load_json_fallback()

    _ensure_migrated()
    c = await _ensure_async_conn(conn)
    cursor = await c.execute("SELECT * FROM chips ORDER BY vendor, name")
    rows = await cursor.fetchall()
    return [_row_to_dict(r) for r in rows]


async def get_by_id_async(chip_id: str, conn: aiosqlite.Connection | None = None) -> dict[str, Any] | None:
    """Async: return a single chip by its ``id`` field.

    Args:
        chip_id: The chip identifier.
        conn: Optional aiosqlite connection.

    Returns:
        Chip dict or ``None`` if not found.
    """
    if settings.use_json:
        chips = _load_json_fallback()
        for c in chips:
            if c.get("id") == chip_id:
                return c
        return None

    _ensure_migrated()
    c = await _ensure_async_conn(conn)
    cursor = await c.execute("SELECT * FROM chips WHERE id = ?", (chip_id,))
    row = await cursor.fetchone()
    return _row_to_dict(row) if row else None


async def search_async(query: str, conn: aiosqlite.Connection | None = None) -> list[dict[str, Any]]:
    """Async: full-text search across all text-searchable fields.

    Multi-word queries joined with `` AND `` so all terms must match.
    Falls back to LIKE-based search on FTS5 syntax errors.

    Args:
        query: The search string.
        conn: Optional aiosqlite connection.

    Returns:
        List of matching chip dicts.
    """
    if settings.use_json:
        ql = query.lower()
        chips = _load_json_fallback()
        return [c for c in chips if ql in json.dumps(c).lower()]

    _ensure_migrated()
    c = await _ensure_async_conn(conn)

    tokens = query.strip().split()
    if not tokens:
        return []
    fts_query = " AND ".join(tokens)

    try:
        cursor = await c.execute(
            "SELECT chips.* FROM chips JOIN chips_fts ON chips.rowid = chips_fts.rowid WHERE chips_fts MATCH ? ORDER BY rank",
            (fts_query,),
        )
        rows = await cursor.fetchall()
    except aiosqlite.OperationalError:
        like_clauses: list[str] = []
        like_params: list[str] = []
        for token in tokens:
            like_clauses.append("(name LIKE ? OR vendor LIKE ? OR model LIKE ? OR description LIKE ?)")
            like_params.extend([f"%{token}%"] * 4)
        like_exprs = " AND ".join(like_clauses)
        cursor = await c.execute(f"SELECT * FROM chips WHERE {like_exprs}", like_params)  # nosec B608 — parameters are ?-placeholders, not injected
        rows = await cursor.fetchall()

    return [_row_to_dict(r) for r in rows]


async def get_vendors_async(conn: aiosqlite.Connection | None = None) -> dict[str, dict[str, Any]]:
    """Async: return vendor summary with chip counts and average completeness.

    Args:
        conn: Optional aiosqlite connection.

    Returns:
        Dict mapping vendor name to ``{count, avg_completeness}``.
    """
    if settings.use_json:
        chips = _load_json_fallback()
        vendors: dict[str, dict[str, Any]] = {}
        for c in chips:
            v = c.get("vendor", "Unknown")
            vendors.setdefault(v, {"count": 0, "completeness": []})
            vendors[v]["count"] += 1
            vendors[v]["completeness"].append(c.get("completeness", 0))
        result = {}
        for vname, vdata in sorted(vendors.items()):
            avg = sum(vdata["completeness"]) / max(len(vdata["completeness"]), 1)
            result[vname] = {"count": vdata["count"], "avg_completeness": round(avg, 3)}
        return result

    _ensure_migrated()
    c = await _ensure_async_conn(conn)
    cursor = await c.execute("SELECT vendor, COUNT(*) AS count, AVG(COALESCE(completeness, 0)) AS avg_comp FROM chips GROUP BY vendor ORDER BY vendor")
    rows = await cursor.fetchall()
    return {r["vendor"]: {"count": r["count"], "avg_completeness": round(r["avg_comp"], 3)} for r in rows}


async def get_stats_async(conn: aiosqlite.Connection | None = None) -> dict[str, Any]:
    """Async: return database-wide aggregate statistics.

    Returns:
        Dict with keys: ``total_chips``, ``total_vendors``, ``year_min``,
        ``year_max``, ``avg_completeness``, ``fields_present``.
    """
    if settings.use_json:
        chips = _load_json_fallback()
        vcount = len({c.get("vendor", "") for c in chips})
        years = [c.get("year") for c in chips if c.get("year")]
        comps = [c.get("completeness", 0) for c in chips]
        return {
            "total_chips": len(chips),
            "total_vendors": vcount,
            "year_min": min(years) if years else None,
            "year_max": max(years) if years else None,
            "avg_completeness": round(sum(comps) / max(len(comps), 1), 3),
            "fields_present": {
                "gpu": sum(1 for c in chips if c.get("gpu")),
                "process_nm": sum(1 for c in chips if c.get("process_nm")),
                "clock_max": sum(1 for c in chips if c.get("clock_max")),
                "architecture": sum(1 for c in chips if c.get("architecture")),
            },
        }

    _ensure_migrated()
    c = await _ensure_async_conn(conn)
    cursor = await c.execute(
        "SELECT COUNT(*) AS total_chips, "
        "COUNT(DISTINCT vendor) AS total_vendors, "
        "MIN(year) AS year_min, "
        "MAX(year) AS year_max, "
        "AVG(COALESCE(completeness, 0)) AS avg_completeness, "
        "SUM(CASE WHEN gpu IS NOT NULL THEN 1 ELSE 0 END) AS gpu_present, "
        "SUM(CASE WHEN process_nm IS NOT NULL THEN 1 ELSE 0 END) AS process_nm_present, "
        "SUM(CASE WHEN clock_max IS NOT NULL THEN 1 ELSE 0 END) AS clock_max_present, "
        "SUM(CASE WHEN architecture IS NOT NULL THEN 1 ELSE 0 END) AS architecture_present "
        "FROM chips"
    )
    row = await cursor.fetchone()
    total = row["total_chips"]
    return {
        "total_chips": total,
        "total_vendors": row["total_vendors"],
        "year_min": row["year_min"],
        "year_max": row["year_max"],
        "avg_completeness": round(row["avg_completeness"], 3),
        "fields_present": {
            "gpu": f"{row['gpu_present']}/{total}",
            "process_nm": f"{row['process_nm_present']}/{total}",
            "clock_max": f"{row['clock_max_present']}/{total}",
            "architecture": f"{row['architecture_present']}/{total}",
        },
    }
