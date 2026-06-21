import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app, make_cache_buster


@pytest.fixture(autouse=True)
def init_app_state():
    app.state._cache_buster = make_cache_buster()
    app.state._chips = None


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
    resp = await client.get("/chips")
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
    resp = await client.get("/chips/sm8550_ab")
    assert resp.status_code == 200
    chip = resp.json()
    assert chip["id"] == "sm8550_ab"
    assert chip["vendor"] == "Qualcomm"
    assert "name" in chip
    assert "architecture" in chip
    assert "cores" in chip


@pytest.mark.asyncio
async def test_chip_not_found(client):
    resp = await client.get("/chips/nonexistent_chip_xyz")
    assert resp.status_code == 404
    data = resp.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_stats(client):
    resp = await client.get("/stats")
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
    resp = await client.get("/schema")
    assert resp.status_code == 200
    data = resp.json()
    assert "type" in data
    assert "properties" in data or "$defs" in data or "definitions" in data


@pytest.mark.asyncio
async def test_export_json(client):
    resp = await client.get("/export/json")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "id" in data[0]
