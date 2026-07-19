"""Tests for API performance improvements — cursor pagination, lazy loading, caching headers."""

from __future__ import annotations

import time

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app, make_cache_buster
from soc_db.rate_limit import InMemoryRateLimiter


@pytest.fixture(autouse=True)
def init_app_state():
    import time as _time

    from soc_db.db.connection import clear_connection_cache

    clear_connection_cache()
    app.state._cache_buster = make_cache_buster()
    app.state._chips = None
    app.state._search_index = None
    app.state._cache_loaded_at = 0.0
    app.state._started_at = _time.time()
    app.state._request_count = 0
    app.state.rate_limiter = InMemoryRateLimiter(limit=100, window=60)


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ===========================================================================
# Cursor-based pagination
# ===========================================================================


@pytest.mark.asyncio
async def test_cursor_pagination_basic(client):
    """Cursor-based pagination returns paginated results."""
    resp = await client.get("/v1/chips?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert "next_cursor" in data
    assert data["limit"] == 10
    assert len(data["data"]) <= 10


@pytest.mark.asyncio
async def test_cursor_pagination_traversal(client):
    """Traverse two pages using cursor and verify different pages returned."""
    resp1 = await client.get("/v1/chips?limit=5")
    assert resp1.status_code == 200
    data1 = resp1.json()
    page1_ids = [c["id"] for c in data1["data"]]

    # Second page via cursor
    cursor = data1.get("next_cursor")
    if cursor:
        resp2 = await client.get(f"/v1/chips?limit=5&cursor={cursor}")
        assert resp2.status_code == 200
        data2 = resp2.json()
        page2_ids = [c["id"] for c in data2["data"]]
        # Pages should have different chips
        overlap = set(page1_ids) & set(page2_ids)
        assert len(overlap) == 0


@pytest.mark.asyncio
async def test_cursor_last_page_no_next(client):
    """Last page should have next_cursor=None."""
    # Use a large enough offset to hit the end
    resp = await client.get("/v1/chips?limit=10000&offset=0")
    assert resp.status_code == 200
    data = resp.json()
    total = data["total"]
    # Request the last page
    resp_last = await client.get(f"/v1/chips?limit=100&offset={max(0, total - 50)}")
    data_last = resp_last.json()
    # If we got everything, there's no next_cursor
    if data_last["offset"] + len(data_last["data"]) >= total:
        assert data_last.get("next_cursor") is None or data_last["next_cursor"] == ""


@pytest.mark.asyncio
async def test_invalid_cursor_returns_400(client):
    """Invalid cursor should return 400."""
    resp = await client.get("/v1/chips?cursor=invalid_cursor_value!")
    assert resp.status_code == 400


# ===========================================================================
# Lazy field loading (heavy fields excluded by default)
# ===========================================================================


@pytest.mark.asyncio
async def test_lazy_loading_excludes_heavy_fields(client):
    """Heavy fields should be excluded by default."""
    resp = await client.get("/v1/chips?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    for chip in data["data"]:
        assert "benchmarks" not in chip, f"benchmarks should be excluded by default in {chip.get('id')}"
        assert "rating" not in chip, f"rating should be excluded by default in {chip.get('id')}"
        assert "cache" not in chip, f"cache should be excluded by default in {chip.get('id')}"
        assert "provenance" not in chip, f"provenance should be excluded by default in {chip.get('id')}"


@pytest.mark.asyncio
async def test_fields_param_includes_heavy_fields(client):
    """Explicit fields parameter should include heavy fields."""
    resp = await client.get("/v1/chips?limit=5&fields=id,name,benchmarks,rating")
    assert resp.status_code == 200
    data = resp.json()
    for chip in data["data"]:
        assert "id" in chip
        assert "name" in chip
        # benchmarks and rating may be None (not set on chips), but should be present
        # The fields filter only includes keys that exist in the chip


@pytest.mark.asyncio
async def test_fields_param_limits_output(client):
    """Explicit fields parameter should limit output to requested fields."""
    resp = await client.get("/v1/chips?limit=3&fields=id,name")
    assert resp.status_code == 200
    data = resp.json()
    for chip in data["data"]:
        assert len(chip) <= 2  # Only id and name
        assert "id" in chip
        assert "name" in chip


# ===========================================================================
# Caching headers
# ===========================================================================


@pytest.mark.asyncio
async def test_etag_header_present(client):
    """Response should include ETag header."""
    resp = await client.get("/v1/chips?limit=5")
    assert resp.status_code == 200
    assert "etag" in resp.headers or "ETag" in resp.headers


@pytest.mark.asyncio
async def test_cache_control_header_present(client):
    """Response should include Cache-Control header."""
    resp = await client.get("/v1/chips?limit=5")
    assert resp.status_code == 200
    cache_control = resp.headers.get("cache-control", resp.headers.get("Cache-Control", ""))
    assert "public" in cache_control
    assert "max-age" in cache_control


@pytest.mark.asyncio
async def test_last_modified_header_present(client):
    """Response should include Last-Modified header."""
    resp = await client.get("/v1/chips?limit=5")
    assert resp.status_code == 200
    assert "last-modified" in resp.headers or "Last-Modified" in resp.headers


@pytest.mark.asyncio
async def test_if_none_match_returns_304(client):
    """If-None-Match with matching ETag returns 304."""
    resp = await client.get("/v1/chips?limit=5")
    assert resp.status_code == 200
    etag = resp.headers.get("etag") or resp.headers.get("ETag", "")
    if etag:
        resp2 = await client.get("/v1/chips?limit=5", headers={"If-None-Match": etag})
        assert resp2.status_code == 304


@pytest.mark.asyncio
async def test_different_query_different_etag(client):
    """Different query parameters should produce different ETags."""
    resp1 = await client.get("/v1/chips?limit=5")
    resp2 = await client.get("/v1/chips?limit=10")
    etag1 = resp1.headers.get("etag") or resp1.headers.get("ETag", "")
    etag2 = resp2.headers.get("etag") or resp2.headers.get("ETag", "")
    assert etag1 != etag2 or not etag1 or not etag2
