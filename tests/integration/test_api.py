import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app, make_cache_buster


@pytest.fixture(autouse=True)
def init_app_state():
    import time

    app.state._cache_buster = make_cache_buster()
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
async def test_root(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert "api" in data
    assert "version" in data
    assert "endpoints" in data


@pytest.mark.asyncio
async def test_chips_list(client):
    resp = await client.get("/v1/chips")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "offset" in data
    assert "limit" in data
    assert "data" in data
    assert isinstance(data["data"], list)
    assert len(data["data"]) > 0


@pytest.mark.asyncio
async def test_chip_by_id(client):
    resp = await client.get("/v1/chips/sm8550_ab")
    assert resp.status_code == 200
    chip = resp.json()
    assert chip["id"] == "sm8550_ab"
    assert chip["vendor"] == "Qualcomm"
    assert "name" in chip
    assert "architecture" in chip
    assert "cores" in chip


@pytest.mark.asyncio
async def test_chip_not_found(client):
    resp = await client.get("/v1/chips/nonexistent_chip_xyz")
    assert resp.status_code == 404
    data = resp.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_stats(client):
    resp = await client.get("/v1/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_chips" in data
    assert "total_vendors" in data
    assert "year_min" in data
    assert "year_max" in data
    assert "avg_completeness" in data
    assert "fields_present" in data
    assert data["total_chips"] > 0
    assert data["total_vendors"] > 0


@pytest.mark.asyncio
async def test_schema(client):
    resp = await client.get("/v1/schema")
    assert resp.status_code == 200
    data = resp.json()
    assert "type" in data
    assert "properties" in data or "$defs" in data or "definitions" in data


@pytest.mark.asyncio
async def test_export_json(client):
    resp = await client.get("/v1/export/json")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "id" in data[0]


@pytest.mark.asyncio
async def test_health(client):
    await client.get("/v1/chips")  # trigger chip cache load
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "uptime" in data
    assert "chips_cached" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_health_not_ready(client):
    resp = await client.get("/health")
    assert resp.status_code == 503
    assert resp.json()["status"] == "not ready"


@pytest.mark.asyncio
async def test_metrics(client):
    await client.get("/v1/chips")  # trigger chip cache load
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "uptime_seconds" in data
    assert "total_requests" in data
    assert "requests_per_second" in data
    assert "active_rate_limit_clients" in data


@pytest.mark.asyncio
async def test_x_request_id(client):
    resp = await client.get("/", headers={"X-Request-ID": "my-test-id"})
    assert resp.status_code == 200
    assert resp.headers.get("x-request-id") == "my-test-id"


@pytest.mark.asyncio
async def test_rate_limit_jail(client):
    from api.main import _rate_limit_buckets
    from api.main import settings as api_settings

    _rate_limit_buckets.clear()
    saved = api_settings.api_rate_limit
    api_settings.api_rate_limit = 10
    api_settings.api_rate_limit_window = 60
    try:
        for _ in range(15):
            resp = await client.get("/")
            if resp.status_code == 429:
                data = resp.json()
                assert "error" in data
                assert "retry_after" in data
                return
        pytest.fail("Rate limiter did not trigger (expected HTTP 429)")
    finally:
        api_settings.api_rate_limit = saved
        _rate_limit_buckets.clear()


@pytest.mark.asyncio
async def test_search_qualcomm(client):
    await client.get("/v1/chips")  # trigger cache load
    resp = await client.get("/v1/chips?q=qualcomm")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] > 0
    for c in data["data"]:
        assert "qualcomm" in c.get("vendor", "").lower()


@pytest.mark.asyncio
async def test_api_key_auth(client):
    from api.main import settings as api_settings

    saved = api_settings.api_key
    api_settings.api_key = "test-secret-123"
    try:
        resp = await client.get("/v1/chips?limit=1")
        assert resp.status_code == 401
        resp = await client.get("/v1/chips?limit=1", headers={"X-API-Key": "test-secret-123"})
        assert resp.status_code == 200
    finally:
        api_settings.api_key = saved


@pytest.mark.asyncio
async def test_validation_error(client):
    resp = await client.get("/v1/chips?limit=-1")
    assert resp.status_code == 422
    data = resp.json()
    assert "error" in data


@pytest.mark.asyncio
async def test_404_format(client):
    resp = await client.get("/v1/chips/nonexistent")
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"] == "Chip not found"
