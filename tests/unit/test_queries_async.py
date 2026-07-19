"""Async query function tests.

Verifies that async query functions return identical results to
their synchronous equivalents, and that the dual-read JSON fallback
works correctly.
"""

import asyncio

import pytest

from soc_db.db import queries as q


@pytest.fixture(autouse=True)
async def _reset_async_pool():
    """Close the global async pool after each test."""
    yield
    import soc_db.db.connection as conn_mod

    pool = getattr(conn_mod, "_async_pool", None)
    if pool is not None:
        await pool.close()
        conn_mod._async_pool = None


@pytest.mark.asyncio
class TestAsyncQueriesDefault:
    """Async queries produce identical results to sync SQLite path."""

    async def test_get_all_async_returns_all_chips(self, db_conn):
        sync_chips = q.get_all(conn=db_conn)
        async_chips = await q.get_all_async()
        assert len(async_chips) == len(sync_chips)
        assert async_chips[0]["id"] == sync_chips[0]["id"]

    async def test_get_by_id_async_found(self):
        chip = await q.get_by_id_async("sm8550_ac")
        assert chip is not None
        assert chip["vendor"] == "Qualcomm"

    async def test_get_by_id_async_not_found(self):
        chip = await q.get_by_id_async("nonexistent_chip_xyz")
        assert chip is None

    async def test_get_by_id_async_matches_sync(self, db_conn):
        # Use IDs present in both the temp test DB (db_conn) and main DB (async pool)
        test_ids = ["sm8550_ac", "exynos2200"]
        for chip_id in test_ids:
            sync = q.get_by_id(chip_id, conn=db_conn)
            async_ = await q.get_by_id_async(chip_id)
            assert sync is not None
            assert async_ is not None
            assert sync["id"] == async_["id"]
            assert sync["name"] == async_["name"]
            assert sync["vendor"] == async_["vendor"]

    async def test_get_all_async_pool_acquire_release(self):
        """Verify pool acquires and releases correctly over multiple calls."""
        chips1 = await q.get_all_async()
        chips2 = await q.get_all_async()
        assert len(chips1) == len(chips2)
        assert chips1[0]["id"] == chips2[0]["id"]

    async def test_search_async_basic(self, db_conn):
        async_results = await q.search_async("qualcomm")
        sync_results = q.search("qualcomm", conn=db_conn)
        assert len(async_results) > 0
        assert len(async_results) == len(sync_results)
        for c in async_results:
            assert "qualcomm" in c.get("vendor", "").lower()

    async def test_search_async_no_results(self):
        results = await q.search_async("nonexistent_chip_xyz")
        assert results == []

    async def test_get_vendors_async_matches_sync(self, db_conn):
        sync_v = q.get_vendors(conn=db_conn)
        async_v = await q.get_vendors_async()
        assert set(sync_v.keys()) == set(async_v.keys())
        for vn in sync_v:
            assert sync_v[vn]["count"] == async_v[vn]["count"]

    async def test_get_stats_async_matches_sync(self, db_conn):
        sync_s = q.get_stats(conn=db_conn)
        async_s = await q.get_stats_async()
        assert sync_s["total_chips"] == async_s["total_chips"]
        assert sync_s["total_vendors"] == async_s["total_vendors"]

    async def test_concurrent_async_queries(self):
        """Run multiple async queries concurrently to verify non-blocking."""
        results = await asyncio.gather(
            q.get_all_async(),
            q.get_by_id_async("sm8550_ac"),
            q.search_async("mediatek"),
            q.get_vendors_async(),
            q.get_stats_async(),
        )
        chips, chip, search_res, vendors, stats = results
        assert len(chips) > 0
        assert chip is not None
        assert len(search_res) > 0
        assert len(vendors) > 0
        assert stats["total_chips"] > 0


@pytest.mark.asyncio
class TestAsyncQueriesJsonFallback:
    """Async queries fall back to JSON when SOC_DB_USE_JSON is true."""

    async def test_get_all_async_json_fallback(self, use_json_true):
        chips = await q.get_all_async()
        assert len(chips) > 0

    async def test_get_by_id_async_json_fallback(self, use_json_true):
        chip = await q.get_by_id_async("sm8550_ac")
        assert chip is not None
        assert chip["vendor"] == "Qualcomm"

    async def test_get_vendors_async_json_fallback(self, use_json_true):
        vendors = await q.get_vendors_async()
        assert len(vendors) > 0

    async def test_get_stats_async_json_fallback(self, use_json_true):
        stats = await q.get_stats_async()
        assert stats["total_chips"] > 0
        assert stats["total_vendors"] > 0
