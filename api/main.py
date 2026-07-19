"""FastAPI REST server for the SoC database."""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import signal
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from prometheus_client import generate_latest

from soc_db.config import settings
from soc_db.db.connection import get_async_connection
from soc_db.db.queries import get_all_async, search_async
from soc_db.log_config import setup_logging
from soc_db.telemetry import instrument_app, setup_telemetry, update_vendor_metrics
from soc_db.models import (
    Chip,
    ChipListResponse,
    ErrorResponse,
    HealthResponse,
    StatsResponse,
    VendorResponse,
)

logger = logging.getLogger("soc_db.api")

# ---------------------------------------------------------------------------
# Application lifecycle
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging()
    # Auto-migrate SQLite database on startup (unless using JSON fallback)
    if not settings.use_json:
        try:
            from soc_db.db.migrate import ensure_migrated

            ensure_migrated()
            logger.info("SQLite database ready at %s", settings.db_path)
        except Exception:
            logger.warning("Could not initialise SQLite — falling back to JSON on first request", exc_info=True)
    _app.state._cache_buster = make_cache_buster()
    _app.state._chips = None
    _app.state._search_index: dict[str, list[int]] | None = None
    _app.state._cache_loaded_at = 0.0
    _app.state._started_at = time.time()
    _app.state._request_count = 0
    # Initialize rate limiter (Redis-backed or in-memory fallback)
    from soc_db.rate_limit import create_rate_limiter

    _app.state.rate_limiter = await create_rate_limiter(
        redis_url=settings.redis_url,
        limit=settings.api_rate_limit,
        window=settings.api_rate_limit_window,
    )
    setup_telemetry()
    instrument_app(_app)
    logger.info("Server starting", extra={"version": _app.version, "cache_buster": _app.state._cache_buster})

    loop = asyncio.get_running_loop()
    stop = asyncio.Future()

    def _shutdown() -> None:
        if not stop.done():
            stop.set_result(None)

    loop.add_signal_handler(signal.SIGTERM, _shutdown)
    loop.add_signal_handler(signal.SIGINT, _shutdown)

    try:
        yield
    finally:
        logger.info("Server shutting down, closing rate limiter")
        limiter = getattr(_app.state, "rate_limiter", None)
        if limiter is not None and hasattr(limiter, "close"):
            try:
                await limiter.close()
            except Exception:
                pass
        from soc_db.db.connection import get_async_connection
        try:
            pool = get_async_connection()
            await pool.close()
        except Exception:
            pass


app = FastAPI(
    title="SoC Database API",
    version="2.1.0-dev",
    description="Enterprise SoC/CPU database — query, filter, export",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=settings.api_cors_origins, allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------
@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException):
    if isinstance(exc.detail, str):
        detail_val = None
        error_val = exc.detail
    else:
        error_val = exc.detail.get("error", "error")
        detail_val = exc.detail.get("detail")
    return JSONResponse(status_code=exc.status_code, content={"error": error_val, "detail": detail_val})


@app.exception_handler(RequestValidationError)
async def validation_handler(_request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "Validation error", "detail": exc.errors()},
    )


@app.exception_handler(Exception)
async def generic_handler(_request: Request, exc: Exception):
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Internal server error", "detail": str(exc) if settings.log_level == "DEBUG" else None},
    )


# ---------------------------------------------------------------------------
# API v1 router
# ---------------------------------------------------------------------------
api_v1 = APIRouter(prefix="/v1", tags=["v1"])


def load_index():
    """Load the chip index from ``data/index.json``.

    Returns:
        dict: The parsed index content.
    """
    return json.loads((settings.data_dir / "index.json").read_text("utf-8"))


def load_all() -> list[dict]:
    """Load all chip records from JSON data files.

    Reads every ``.json`` file in the data directory, skipping
    ``index.json``, and returns the combined list of chip dictionaries.
    """
    chips: list[dict] = []
    for fpath in sorted(settings.data_dir.glob("*.json")):
        if fpath.name == "index.json":
            continue
        chips.extend(json.loads(fpath.read_text("utf-8")))
    return chips


def _build_search_index(chips: list[dict]) -> dict[str, list[int]]:
    """Build an inverted index mapping lowercase tokens to chip indices."""
    index: dict[str, list[int]] = {}
    for i, c in enumerate(chips):
        seen: set[str] = set()
        for val in c.values():
            if isinstance(val, str):
                for word in val.lower().split():
                    if word not in seen:
                        seen.add(word)
                        index.setdefault(word, []).append(i)
            elif isinstance(val, (int, float)):
                word = str(val)
                if word not in seen:
                    seen.add(word)
                    index.setdefault(word, []).append(i)
    return index


def _load_all_dual() -> list[dict]:
    """Load chips with dual-read (SQLite / JSON) fallback.

    When ``settings.use_json`` is ``True``, reads from JSON vendor files.
    Otherwise reads from the SQLite database (auto-migrating if needed).
    """
    if settings.use_json:
        return load_all()
    from soc_db.db.migrate import ensure_migrated
    from soc_db.db.queries import get_all as _sql_get_all

    ensure_migrated()
    return _sql_get_all()


def make_cache_buster():
    """Generate a random 8-character cache-busting string.

    Uses MD5 of cryptographically random bytes.

    Returns:
        str: An 8-character hex string.
    """
    from hashlib import md5
    from os import urandom

    return md5(urandom(16)).hexdigest()[:8]


@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    """Optional API key authentication for v1 endpoints."""
    if settings.api_key and request.url.path.startswith("/v1/"):
        key = request.headers.get("X-API-Key")
        if key != settings.api_key:
            return JSONResponse({"error": "Unauthorized", "detail": "Invalid or missing X-API-Key"}, status_code=401)
    return await call_next(request)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Sliding-window rate limiter per client IP with standard headers."""
    limiter = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        # Lazy init for tests that don't use lifespan
        from soc_db.rate_limit import InMemoryRateLimiter

        limiter = InMemoryRateLimiter(limit=settings.api_rate_limit, window=settings.api_rate_limit_window)
        request.app.state.rate_limiter = limiter

    client = request.client.host if request.client else "unknown"
    try:
        allowed, limit, remaining, reset_time = await limiter.check(client)
    except Exception:
        logger.exception("Rate limiter check failed — allowing request")
        return await call_next(request)

    if not allowed:
        logger.warning("Rate limit exceeded", extra={"client": client, "limit": limit})
        return JSONResponse(
            status_code=429,
            content={"error": "Too many requests", "retry_after": max(1, int(reset_time - time.time()))},
            headers={
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(reset_time)),
            },
        )

    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(int(reset_time))
    return response


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Inject a unique ``X-Request-ID`` header into every response."""
    rid = request.headers.get("X-Request-ID", uuid4().hex[:16])
    request.state.request_id = rid
    start = time.monotonic()
    try:
        response = await call_next(request)
    except BaseException:
        logger.exception("Unhandled exception processing %s %s", request.method, request.url.path)
        raise
    elapsed = time.monotonic() - start
    response.headers["X-Request-ID"] = rid
    app.state._request_count += 1
    logger.info(
        "request",
        extra={
            "request_id": rid,
            "method": request.method,
            "path": request.url.path,
            "query": str(request.url.query),
            "status": response.status_code,
            "duration_ms": round(elapsed * 1000, 2),
            "client_host": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
        },
    )
    return response


def _search_chips(chips: list[dict], q: str, index: dict[str, list[int]] | None) -> list[dict]:
    """Fast full-text search using the inverted index, falling back to linear scan."""
    ql = q.lower()
    if index is not None:
        tokens = ql.split()
        if not tokens:
            return chips
        result_sets: list[set[int]] = []
        for token in tokens:
            result_sets.append(set(index.get(token, [])))
        if not result_sets:
            return []
        matched = result_sets[0].intersection(*result_sets[1:]) if len(result_sets) > 1 else result_sets[0]
        return [chips[i] for i in sorted(matched)]
    result: list[dict] = []
    for c in chips:
        for val in c.values():
            if isinstance(val, str) and ql in val.lower():
                result.append(c)
                break
    return result


async def get_chips():
    """Return the chip list with async DB access and TTL cache.

    When ``settings.use_json`` is ``True``, uses the original JSON cache
    with TTL-based invalidation and custom inverted search index.
    When ``False`` (default), queries SQLite asynchronously with TTL
    cache (``settings.cache_ttl`` seconds).  No ``asyncio.to_thread()``
    wrappers are used for database access.
    """
    now = time.monotonic()
    if settings.use_json:
        if app.state._chips is None or (now - app.state._cache_loaded_at) > settings.cache_ttl:
            app.state._chips = load_all()
            app.state._search_index = _build_search_index(app.state._chips)
            app.state._cache_loaded_at = now
        return app.state._chips

    # Async SQLite path with TTL cache
    if app.state._chips is not None and (now - app.state._cache_loaded_at) < settings.cache_ttl:
        return app.state._chips

    try:
        pool = get_async_connection()
        conn = await pool.acquire()
        try:
            app.state._chips = await get_all_async(conn=conn)
            app.state._search_index = None  # FTS5 handles search in DB mode
            app.state._cache_loaded_at = time.monotonic()
        finally:
            await pool.release(conn)
    except Exception:
        logger.warning("Async DB unavailable — falling back to JSON", exc_info=True)
        app.state._chips = load_all()
        app.state._search_index = _build_search_index(app.state._chips)
        app.state._cache_loaded_at = time.monotonic()

    return app.state._chips


@app.get("/health", response_model=HealthResponse, tags=["infra"])
def health():
    """Liveness & readiness probe.

    Returns HTTP 200 when the application is healthy, HTTP 503 when the
    chip cache has not been loaded yet (JSON mode only — SQLite mode
    doesn't use a cache and is always ready when the database exists).
    """
    if settings.use_json:
        if app.state._chips is None:
            return JSONResponse({"status": "not ready", "uptime": time.time() - app.state._started_at}, status_code=503)
        chips_cached = len(app.state._chips)
    else:
        chips_cached = 0
    limiter = getattr(app.state, "rate_limiter", None)
    redis_connected = limiter.is_redis_connected if limiter else False
    return {
        "status": "healthy",
        "uptime": round(time.time() - app.state._started_at, 2),
        "chips_cached": chips_cached,
        "version": app.version,
        "redis_connected": redis_connected,
    }


@app.get("/metrics", tags=["infra"])
async def metrics():
    """Prometheus metrics endpoint."""
    chips = await get_chips()
    update_vendor_metrics(chips)
    return Response(content=generate_latest(), media_type="text/plain; version=0.0.4; charset=utf-8")


@app.get("/")
def root():
    """Root endpoint — return API metadata and available routes."""
    return {
        "api": "SoC Database API",
        "version": "2.0.0",
        "endpoints": {
            "vendors": "/v1/vendors",
            "chips": "/v1/chips",
            "search": "/v1/chips?q=...",
            "chip": "/v1/chips/{id}",
            "stats": "/v1/stats",
            "schema": "/v1/schema",
            "export": "/v1/export/{fmt}",
        },
        "infra": {"/health": "liveness probe", "/metrics": "application metrics"},
        "docs": "/docs",
    }


@api_v1.get("/vendors", response_model=VendorResponse)
async def list_vendors():
    """List all vendors with chip counts and average completeness.

    Returns a mapping of vendor name to chip count and average completeness score.
    """
    chips = await get_chips()
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


@api_v1.get("/chips", response_model=ChipListResponse)
async def list_chips(
    q: str | None = Query(None, description="Full-text search across all fields"),
    vendor: str | None = Query(None, description="Exact vendor name"),
    arch: str | None = Query(None, description="Architecture substring match"),
    gpu: str | None = Query(None, description="GPU substring match"),
    year: int | None = Query(None, description="Release year"),
    min_cores: int | None = Query(None, alias="min-cores", description="Minimum core count"),
    min_completeness: float | None = Query(None, alias="min-completeness", ge=0, le=1, description="Minimum completeness score"),
    limit: int = Query(100, ge=1, le=10000, description="Results per page"),
    offset: int = Query(0, ge=0, description="Page offset"),
    fields: str | None = Query(None, description="Comma-separated field whitelist"),
    sort: str | None = Query(None, description="Sort field"),
    order: str = Query("asc", pattern="^(asc|desc)$", description="Sort direction"),
):
    """Search and filter chips with pagination.

    Supports full-text search, field-specific filtering, sorting,
    field projection, and pagination.
    """
    chips = await get_chips()
    if vendor:
        chips = [c for c in chips if c.get("vendor", "").lower() == vendor.lower()]
    if q:
        if settings.use_json:
            chips = _search_chips(chips, q, app.state._search_index)
        else:
            chips = await search_async(q)
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


@api_v1.get("/chips/{chip_id}", response_model=Chip, responses={404: {"model": ErrorResponse}})
async def get_chip(chip_id: str):
    """Retrieve a single chip by its ID.

    Returns the full chip record for the given identifier,
    or HTTP 404 if the chip does not exist.
    """
    chips = await get_chips()
    for c in chips:
        if c.get("id") == chip_id:
            return Chip.model_validate(c)
    raise HTTPException(404, {"error": "Chip not found", "detail": f"Chip '{chip_id}' not found"})


@api_v1.get("/stats", response_model=StatsResponse)
async def stats():
    """Database-wide aggregate statistics.

    Returns total chips, vendors, year range, average completeness,
    and field-presence counters.
    """
    chips = await get_chips()
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


@api_v1.get("/schema")
def get_schema():
    """Return the JSON Schema for a chip record.

    Returns:
        JSONResponse with media type ``application/schema+json``.
        HTTP 200 on success.
    """
    schema = json.loads(settings.schema_file.read_text("utf-8"))
    return JSONResponse(schema, media_type="application/schema+json")


@api_v1.get("/export/{fmt}")
async def export(fmt: str):
    """Export all chip data in the requested format.

    Args:
        fmt: Output format — ``"json"``, ``"json.gz"``, or ``"csv"``.

    Returns:
        JSONResponse, gzip-compressed JSON, or CSV Response depending
        on ``fmt``.  HTTP 400 if the format is unsupported.
    """
    chips = await get_chips()
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


app.include_router(api_v1)
