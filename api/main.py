"""FastAPI REST server for the SoC database.

Provides endpoints for listing chips, vendors, stats, schema, and
exporting data in multiple formats.  Chips are cached in-memory after
the first load.
"""

import gzip
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA_DIR = ROOT / "data"
SCHEMA_FILE = ROOT / "schema" / "chip-schema.json"

app = FastAPI(
    title="SoC Database API",
    version="2.1.0-dev",
    description="Enterprise SoC/CPU database — query, filter, export",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def load_index():
    """Load the chip index from ``data/index.json``.

    Returns:
        dict: The parsed index content.
    """
    return json.loads((DATA_DIR / "index.json").read_text("utf-8"))


def load_all():
    """Load all chip records from JSON data files.

    Reads every ``.json`` file in the data directory, skipping
    ``index.json``, and returns the combined list of chip dictionaries.

    Returns:
        list[dict]: All chips across all vendor files.
    """
    chips = []
    for fpath in sorted(DATA_DIR.glob("*.json")):
        if fpath.name == "index.json":
            continue
        chips.extend(json.loads(fpath.read_text("utf-8")))
    return chips


def make_cache_buster():
    """Generate a random 8-character cache-busting string.

    Uses MD5 of cryptographically random bytes.

    Returns:
        str: An 8-character hex string.
    """
    from hashlib import md5
    from os import urandom

    return md5(urandom(16)).hexdigest()[:8]


@app.on_event("startup")
async def startup():
    """FastAPI startup event — initialise cache state.

    Sets a random cache buster and marks the chip cache as empty.
    """
    app.state._cache_buster = make_cache_buster()
    app.state._chips = None


def get_chips():
    """Return the cached chip list, loading it on first access.

    Returns:
        list[dict]: All chips, cached in ``app.state._chips``.
    """
    if app.state._chips is None:
        app.state._chips = load_all()
    return app.state._chips


@app.get("/")
def root():
    """Root endpoint — return API metadata and available routes.

    Returns:
        dict: API name, version, endpoint listing, and docs URL.
    """
    return {
        "api": "SoC Database API",
        "version": "2.0.0",
        "endpoints": {
            "vendors": "/vendors",
            "chips": "/chips",
            "search": "/chips?q=...",
            "chip": "/chips/{id}",
            "stats": "/stats",
            "schema": "/schema",
        },
        "docs": "/docs",
    }


@app.get("/vendors")
def list_vendors():
    """List all vendors with chip counts and average completeness.

    Returns:
        dict: Mapping of vendor name to ``{"count": int, "avg_completeness": float}``.
              HTTP 200 on success.
    """
    chips = get_chips()
    vendors = {}
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


@app.get("/chips")
def list_chips(
    q: str | None = Query(None, description="Full-text search"),
    vendor: str | None = Query(None, description="Vendor name (exact)"),
    arch: str | None = Query(None, description="Architecture (substring)"),
    gpu: str | None = Query(None, description="GPU (substring)"),
    year: int | None = Query(None, description="Release year"),
    min_cores: int | None = Query(None, alias="min-cores"),
    min_completeness: float | None = Query(None, alias="min-completeness", ge=0, le=1),
    limit: int = Query(100, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    fields: str | None = Query(None, description="Comma-separated field whitelist"),
    sort: str | None = Query(None, description="Sort field"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
):
    """Search and filter chips with pagination.

    Accepts optional query parameters for filtering, full-text search,
    sorting, field projection, and pagination (offset/limit).

    Returns:
        dict: ``{"total": int, "offset": int, "limit": int, "data": list[dict]}``.
              HTTP 200 on success.
    """
    chips = get_chips()
    if vendor:
        chips = [c for c in chips if c.get("vendor", "").lower() == vendor.lower()]
    if q:
        ql = q.lower()
        chips = [c for c in chips if ql in json.dumps(c).lower()]
    if arch:
        chips = [c for c in chips if arch.lower() in c.get("architecture", "").lower()]
    if gpu:
        chips = [c for c in chips if gpu.lower() in c.get("gpu", "").lower()]
    if year:
        chips = [c for c in chips if c.get("year") == year]
    if min_cores:
        chips = [c for c in chips if (c.get("cores") or 0) >= min_cores]
    if min_completeness:
        chips = [c for c in chips if (c.get("completeness") or 0) >= min_completeness]
    if sort:
        reverse = order == "desc"
        chips = sorted(chips, key=lambda c: c.get(sort, "") or "", reverse=reverse)
    total = len(chips)
    chips = chips[offset : offset + limit]
    if fields:
        keep = set(f.strip() for f in fields.split(","))
        chips = [{k: c[k] for k in keep if k in c} for c in chips]
    return {"total": total, "offset": offset, "limit": limit, "data": chips}


@app.get("/chips/{chip_id}")
def get_chip(chip_id: str):
    """Retrieve a single chip by its ID.

    Args:
        chip_id: Unique chip identifier.

    Returns:
        dict: The full chip record.
              HTTP 200 on success, HTTP 404 if not found.
    """
    chips = get_chips()
    for c in chips:
        if c.get("id") == chip_id:
            return c
    raise HTTPException(404, f"Chip '{chip_id}' not found")


@app.get("/stats")
def stats():
    """Database-wide aggregate statistics.

    Returns:
        dict: Total chips, vendors, year range, average completeness,
              and field-presence counters.
              HTTP 200 on success.
    """
    chips = get_chips()
    vcount = len(set(c.get("vendor", "") for c in chips))
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


@app.get("/schema")
def get_schema():
    """Return the JSON Schema for a chip record.

    Returns:
        JSONResponse with media type ``application/schema+json``.
        HTTP 200 on success.
    """
    schema = json.loads(SCHEMA_FILE.read_text("utf-8"))
    return JSONResponse(schema, media_type="application/schema+json")


@app.get("/export/{fmt}")
def export(fmt: str):
    """Export all chip data in the requested format.

    Args:
        fmt: Output format — ``"json"``, ``"json.gz"``, or ``"csv"``.

    Returns:
        JSONResponse, gzip-compressed JSON, or CSV Response depending
        on ``fmt``.  HTTP 400 if the format is unsupported.
    """
    chips = get_chips()
    if fmt == "json":
        return JSONResponse(chips)
    if fmt == "json.gz":
        data = json.dumps(chips, ensure_ascii=False).encode()
        return Response(gzip.compress(data), media_type="application/gzip", headers={"Content-Encoding": "gzip"})
    if fmt == "csv":
        import csv
        import io

        out = io.StringIO()
        w = csv.writer(out)
        fields = ["id", "name", "vendor", "model", "architecture", "cores", "process_nm", "gpu", "year", "completeness"]
        w.writerow(fields)
        for c in chips:
            w.writerow([c.get(f, "") for f in fields])
        return Response(out.getvalue(), media_type="text/csv")
    raise HTTPException(400, f"Unsupported format: {fmt}")
