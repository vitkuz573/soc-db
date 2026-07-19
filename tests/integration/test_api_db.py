"""Integration tests for the API with SQLite backend."""

import time

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app, make_cache_buster


@pytest.fixture(autouse=True)
def init_app_state():
    """Reset app state and SQLite connection cache for each test."""
    from soc_db.db.connection import clear_connection_cache

    clear_connection_cache()
    app.state._cache_buster = make_cache_buster()
    app.state._chips = None
    app.state._search_index = None
    app.state._cache_loaded_at = 0.0
    app.state._started_at = time.time()
    app.state._request_count = 0
    app.state._chips = None
    app.state._search_index = None
    app.state._cache_loaded_at = 0.0
    app.state._started_at = time.time()
    app.state._request_count = 0


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_chips_list_with_db(client):
    """GET /v1/chips returns 200 with data array (SQLite backend)."""
    resp = await client.get("/v1/chips")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "data" in data
    assert len(data["data"]) > 0


@pytest.mark.asyncio
async def test_chips_search_with_db(client):
    """GET /v1/chips?q=qualcomm returns Qualcomm chips (SQLite backend with FTS5)."""
    resp = await client.get("/v1/chips?q=qualcomm")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] > 0
    for c in data["data"]:
        assert "qualcomm" in c.get("vendor", "").lower()


@pytest.mark.asyncio
async def test_chips_filter_vendor_with_db(client):
    """GET /v1/chips?vendor=Qualcomm returns Qualcomm chips."""
    resp = await client.get("/v1/chips?vendor=Qualcomm")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] > 0
    for c in data["data"]:
        assert c.get("vendor", "").lower() == "qualcomm"


@pytest.mark.asyncio
async def test_chips_filter_arch_with_db(client):
    """GET /v1/chips?arch=ARMv9 returns ARMv9 chips."""
    resp = await client.get("/v1/chips?arch=ARMv9")
    assert resp.status_code == 200
    data = resp.json()
    for c in data["data"]:
        assert "armv9" in c.get("architecture", "").lower()


@pytest.mark.asyncio
async def test_chip_by_id_with_db(client):
    """GET /v1/chips/sm8550_ac returns correct chip."""
    resp = await client.get("/v1/chips/sm8550_ac")
    assert resp.status_code == 200
    chip = resp.json()
    assert chip["vendor"] == "Qualcomm"
    assert chip["id"] == "sm8550_ac"


@pytest.mark.asyncio
async def test_stats_with_db(client):
    """GET /v1/stats returns correct aggregates."""
    resp = await client.get("/v1/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_chips"] > 0
    assert data["total_vendors"] > 0
    assert data["avg_completeness"] > 0


@pytest.mark.asyncio
async def test_vendors_with_db(client):
    """GET /v1/vendors returns vendor listing."""
    resp = await client.get("/v1/vendors")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0
    for _vname, vinfo in data.items():
        assert "count" in vinfo
        assert "avg_completeness" in vinfo


@pytest.mark.asyncio
async def test_export_with_db(client):
    """GET /v1/export/json returns data."""
    resp = await client.get("/v1/export/json")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "id" in data[0]


@pytest.mark.asyncio
async def test_response_model_validation_with_db(client):
    """Verify each chip in response validates against Pydantic Chip model."""
    from soc_db.models import Chip

    resp = await client.get("/v1/chips?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    for item in data["data"]:
        chip = Chip.model_validate(item)
        assert chip.id is not None


@pytest.mark.asyncio
async def test_api_search_fts_with_db(client):
    """Verify FTS5 search via API returns results."""
    resp = await client.get("/v1/chips?q=qualcomm+adreno")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] > 0
    # Most results should be Qualcomm chips
    vendors = {c.get("vendor", "").lower() for c in data["data"]}
    assert "qualcomm" in vendors


@pytest.mark.asyncio
async def test_ttl_cache_invalidation_with_db(client):
    """Verify TTL cache works with SQLite backend."""
    import time as _time
    from api.main import app

    # First request warms cache
    resp1 = await client.get("/v1/chips?limit=10")
    assert resp1.status_code == 200
    data1 = resp1.json()

    # Force cache expiry
    app.state._cache_loaded_at = _time.monotonic() - 600  # 10 min ago

    # Second request should reload from DB
    resp2 = await client.get("/v1/chips?limit=100")
    assert resp2.status_code == 200
    data2 = resp2.json()

    assert data1["total"] == data2["total"]
    assert app.state._cache_loaded_at > _time.monotonic() - 10


@pytest.mark.asyncio
async def test_get_chip_async_with_db(client):
    """Verify single chip lookup works with async backend."""
    resp = await client.get("/v1/chips/sm8550_ac")
    assert resp.status_code == 200
    chip = resp.json()
    assert chip["vendor"] == "Qualcomm"
    assert chip["id"] == "sm8550_ac"


@pytest.mark.asyncio
async def test_five_concurrent_db_requests(client):
    """Five concurrent requests to DB-backed endpoints — all succeed."""
    import asyncio

    urls = [
        "/v1/chips?limit=20",
        "/v1/chips/sm8550_ac",
        "/v1/stats",
        "/v1/vendors",
        "/v1/chips?limit=10&offset=50",
    ]
    results = await asyncio.gather(*[client.get(url) for url in urls], return_exceptions=True)
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            pytest.fail(f"Request {i} failed: {r}")
        assert r.status_code == 200, f"Request {i} returned {r.status_code}"
