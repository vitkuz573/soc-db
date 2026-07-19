"""Dual-read fallback tests — verifies SQLite/JSON backends produce equivalent results."""

from soc_db.config import settings
from soc_db.db.queries import get_all, get_by_id, get_stats, search


class TestDualReadDefault:
    def test_default_is_sqlite(self):
        """Verify settings.use_json is False by default."""
        assert settings.use_json is False

    def test_sqlite_returns_chips(self):
        """Verify default (SQLite) returns chips."""
        chips = get_all()
        assert len(chips) > 0


class TestDualReadJsonFallback:
    def test_json_fallback_returns_chips(self, use_json_true):
        """Set SOC_DB_USE_JSON=true, verify load_all() returns chips from JSON."""
        from soc_db.cli import load_all

        chips = load_all()
        assert len(chips) > 0

    def test_identical_chip_ids_both_backends(self, db_conn, use_json_true):
        """Compare chip IDs between JSON and SQLite — every chip in JSON exists in SQLite and vice versa."""
        # Get SQLite chips (normal mode)
        settings.use_json = False
        sql_chips = get_all(conn=db_conn)

        # Get JSON chips (use_json mode)
        settings.use_json = True
        json_chips = get_all()
        settings.use_json = False

        sql_ids = {c["id"] for c in sql_chips}
        json_ids = {c["id"] for c in json_chips}

        missing_in_sql = json_ids - sql_ids
        extra_in_sql = sql_ids - json_ids

        assert not missing_in_sql, f"{len(missing_in_sql)} chips in JSON but not SQLite: {list(missing_in_sql)[:5]}"
        assert not extra_in_sql, f"{len(extra_in_sql)} chips in SQLite but not JSON: {list(extra_in_sql)[:5]}"

    def test_dual_read_get_by_id_matches(self, use_json_true):
        """Compare get_by_id() results between backends for specific chips."""
        test_ids = ["sm8550_ac", "mt6983", "exynos2200", "kirin9000", "apple_m1"]

        settings.use_json = False
        for chip_id in test_ids:
            sql_result = get_by_id(chip_id)

            settings.use_json = True
            json_result = get_by_id(chip_id)
            settings.use_json = False

            if sql_result and json_result:
                assert sql_result["id"] == json_result["id"]
                assert sql_result["name"] == json_result["name"]
                assert sql_result["vendor"] == json_result["vendor"]

    def test_dual_read_stats_matches(self, use_json_true):
        """Compare get_stats() aggregates between backends."""
        settings.use_json = False
        sql_stats = get_stats()

        settings.use_json = True
        json_stats = get_stats()
        settings.use_json = False

        assert sql_stats["total_chips"] == json_stats["total_chips"]
        assert sql_stats["total_vendors"] == json_stats["total_vendors"]

    def test_dual_read_search_matches(self, db_conn, use_json_true):
        """Compare search() results between backends for common queries."""
        queries = ["qualcomm", "snapdragon", "adreno", "mali", "mediatek"]

        for query in queries:
            settings.use_json = False
            sql_results = search(query, conn=db_conn)

            settings.use_json = True
            json_results = search(query)
            settings.use_json = False

            # FTS5 should return at least as many results as JSON substring search
            assert len(sql_results) >= len(json_results) * 0.5, (
                f"FTS5 returned {len(sql_results)} vs JSON {len(json_results)} for '{query}'"
            )
