"""Unit tests for the Wikidata SPARQL module and merge layer."""

from __future__ import annotations

import json
import logging
import time
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_sparql_bindings():
    """Return a minimal SPARQLWrapper JSON result with all binding shapes."""
    return {
        "results": {
            "bindings": [
                {
                    "item": {"type": "uri", "value": "http://www.wikidata.org/entity/Q123456"},
                    "itemLabel": {"type": "literal", "value": "Snapdragon 8 Gen 2 (SM8550)"},
                    "processNode": {"type": "literal", "value": "4"},
                },
                {
                    "item": {"type": "uri", "value": "http://www.wikidata.org/entity/Q123457"},
                    "itemLabel": {"type": "literal", "value": "Snapdragon 8 Gen 1 (SM8450)"},
                    "processNode": {"type": "literal", "value": "4"},
                },
            ]
        }
    }


@pytest.fixture
def mock_gpu_bindings():
    return {
        "results": {
            "bindings": [
                {
                    "item": {"type": "uri", "value": "http://www.wikidata.org/entity/Q123456"},
                    "itemLabel": {"type": "literal", "value": "Snapdragon 8 Gen 2 (SM8550)"},
                    "gpu": {"type": "uri", "value": "http://www.wikidata.org/entity/Q98765"},
                    "gpuLabel": {"type": "literal", "value": "Adreno 740"},
                },
            ]
        }
    }


@pytest.fixture
def mock_arch_bindings():
    return {
        "results": {
            "bindings": [
                {
                    "item": {"type": "uri", "value": "http://www.wikidata.org/entity/Q544847"},
                    "itemLabel": {"type": "literal", "value": "Qualcomm"},
                    "architecture": {"type": "uri", "value": "http://www.wikidata.org/entity/Q54321"},
                    "architectureLabel": {"type": "literal", "value": "ARMv8"},
                },
            ]
        }
    }


@pytest.fixture
def mock_vendor_knowledge():
    """A minimal VENDOR_KNOWLEDGE-like dict for merge tests."""
    return {
        "Qualcomm": {
            "architecture": "ARMv8",
            "process_map": {"sm8550": 4, "sm8450": 4},
            "gpu_map": {"sm8550": "Adreno 740", "sm8450": "Adreno 730"},
        },
        "MediaTek": {
            "architecture": "ARMv8",
            "process_map": {"mt6989": 3},
            "gpu_map": {"mt6989": "Immortalis-G720"},
        },
    }


# ---------------------------------------------------------------------------
# SPARQL query string tests
# ---------------------------------------------------------------------------

class TestSparqlQueryStrings:
    def test_process_query_has_p2175(self):
        from soc_db.wikidata import _build_process_query

        query = _build_process_query("Q544847")
        assert "P2175" in query

    def test_gpu_query_has_p488(self):
        from soc_db.wikidata import _build_gpu_query

        query = _build_gpu_query("Q544847")
        assert "P488" in query

    def test_arch_query_has_p10620(self):
        from soc_db.wikidata import _build_architecture_query

        query = _build_architecture_query("Q544847")
        assert "P10620" in query

    def test_process_query_includes_vendor_qid(self):
        from soc_db.wikidata import _build_process_query

        query = _build_process_query("Q544847")
        assert "Q544847" in query

    def test_queries_have_limit(self):
        from soc_db.wikidata import _build_architecture_query, _build_gpu_query, _build_process_query

        for builder in (_build_process_query, _build_gpu_query, _build_architecture_query):
            assert "LIMIT" in builder("Q544847")


# ---------------------------------------------------------------------------
# Response parsing tests
# ---------------------------------------------------------------------------

class TestResponseParsing:
    def test_parse_process_response(self, mock_sparql_bindings):
        from soc_db.wikidata import refresh_vendor_knowledge

        with (
            patch("soc_db.wikidata._cached_sparql") as mock_cached,
            patch("soc_db.wikidata.VENDOR_QIDS", {"Qualcomm": "Q544847"}),
        ):
            # Return process bindings for the process query, empty for others
            def side_effect(query, **_kwargs):
                if "P2175" in query:
                    return mock_sparql_bindings["results"]["bindings"]
                return []

            mock_cached.side_effect = side_effect

            result = refresh_vendor_knowledge(dry_run=False)
            qc_result = result.get("Qualcomm", {})
            pmap = qc_result.get("process_map", {})
            assert "sm8550" in pmap
            assert pmap["sm8550"] == 4
            assert "sm8450" in pmap
            assert pmap["sm8450"] == 4

    def test_parse_gpu_response(self, mock_gpu_bindings):
        from soc_db.wikidata import refresh_vendor_knowledge

        with (
            patch("soc_db.wikidata._cached_sparql") as mock_cached,
            patch("soc_db.wikidata.VENDOR_QIDS", {"Qualcomm": "Q544847"}),
        ):
            def side_effect(query, **_kwargs):
                if "P488" in query:
                    return mock_gpu_bindings["results"]["bindings"]
                return []

            mock_cached.side_effect = side_effect

            result = refresh_vendor_knowledge(dry_run=False)
            qc_result = result.get("Qualcomm", {})
            gmap = qc_result.get("gpu_map", {})
            assert "sm8550" in gmap
            assert gmap["sm8550"] == "Adreno 740"

    def test_parse_architecture_response(self, mock_arch_bindings):
        from soc_db.wikidata import refresh_vendor_knowledge

        with (
            patch("soc_db.wikidata._cached_sparql") as mock_cached,
            patch("soc_db.wikidata.VENDOR_QIDS", {"Qualcomm": "Q544847"}),
        ):
            def side_effect(query, **_kwargs):
                if "P10620" in query:
                    return mock_arch_bindings["results"]["bindings"]
                return []

            mock_cached.side_effect = side_effect

            result = refresh_vendor_knowledge(dry_run=False)
            qc_result = result.get("Qualcomm", {})
            assert qc_result.get("architecture") == "ARMv8"


# ---------------------------------------------------------------------------
# Caching tests
# ---------------------------------------------------------------------------

class TestCaching:
    def test_cached_sparql_returns_cached(self, tmp_path, mock_sparql_bindings):
        from soc_db.wikidata import _cached_sparql

        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        query = "SELECT * WHERE { ?s ?p ?o } LIMIT 1"
        key = __import__("hashlib").md5(query.encode(), usedforsecurity=False).hexdigest()
        cache_file = cache_dir / key
        cache_file.write_text(json.dumps(mock_sparql_bindings["results"]["bindings"]))

        with (
            patch("soc_db.wikidata.CACHE_DIR", cache_dir),
            patch("soc_db.wikidata.run_sparql") as mock_run,
        ):
            result = _cached_sparql(query, ttl=86400)
            mock_run.assert_not_called()
            assert len(result) == 2

    def test_cached_sparql_expires(self, tmp_path, mock_sparql_bindings):
        from soc_db.wikidata import _cached_sparql

        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        query = "SELECT * WHERE { ?s ?p ?o } LIMIT 1"
        key = __import__("hashlib").md5(query.encode(), usedforsecurity=False).hexdigest()
        cache_file = cache_dir / key
        cache_file.write_text(json.dumps(mock_sparql_bindings["results"]["bindings"]))

        # Set mtime far in the past
        old_time = time.time() - 200000  # ~2.3 days ago
        os = __import__("os")
        os.utime(str(cache_file), (old_time, old_time))

        with (
            patch("soc_db.wikidata.CACHE_DIR", cache_dir),
            patch("soc_db.wikidata.run_sparql", return_value=mock_sparql_bindings["results"]["bindings"]),
        ):
            result = _cached_sparql(query, ttl=86400)
            assert len(result) == 2

    def test_cached_sparql_writes_new_results(self, tmp_path):
        from soc_db.wikidata import _cached_sparql

        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        query = "SELECT * WHERE { ?s ?p ?o } LIMIT 1"
        bindings = [{"s": {"value": "test"}}]

        with (
            patch("soc_db.wikidata.CACHE_DIR", cache_dir),
            patch("soc_db.wikidata.run_sparql", return_value=bindings),
        ):
            result = _cached_sparql(query, ttl=86400)
            assert result == bindings
            key = __import__("hashlib").md5(query.encode(), usedforsecurity=False).hexdigest()
            assert (cache_dir / key).exists()


# ---------------------------------------------------------------------------
# Exponential backoff tests
# ---------------------------------------------------------------------------

class TestExponentialBackoff:
    def test_exponential_backoff_succeeds_on_retry(self):
        from soc_db.wikidata import run_sparql

        call_count = [0]

        def mock_convert():
            call_count[0] += 1
            if call_count[0] < 4:
                msg = "SPARQL endpoint returned error"
                raise Exception(msg)
            return {"results": {"bindings": [{"test": {"value": "ok"}}]}}

        convert_mock = MagicMock(side_effect=mock_convert)
        mock_query_result = MagicMock()
        mock_query_result.convert = convert_mock

        mock_sparql_cls = MagicMock()
        mock_sparql_cls.query = MagicMock(return_value=mock_query_result)

        with patch("soc_db.wikidata.SPARQLWrapper", return_value=mock_sparql_cls):
            result = run_sparql("TEST", retries=5, base_delay=0.01, max_delay=0.1)
            assert len(result) == 1
            assert result[0]["test"]["value"] == "ok"

    def test_exponential_backoff_fails_after_retries(self):
        from soc_db.wikidata import run_sparql

        convert_mock = MagicMock(side_effect=Exception("Persistent SPARQL error"))
        mock_query_result = MagicMock()
        mock_query_result.convert = convert_mock

        mock_sparql_cls = MagicMock()
        mock_sparql_cls.query = MagicMock(return_value=mock_query_result)

        with patch("soc_db.wikidata.SPARQLWrapper", return_value=mock_sparql_cls):
            result = run_sparql("TEST", retries=3, base_delay=0.01, max_delay=0.1)
            assert result == []
            assert convert_mock.call_count >= 3


# ---------------------------------------------------------------------------
# Dry-run mode tests
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_dry_run_logs_only(self, caplog, mock_sparql_bindings, mock_gpu_bindings, mock_arch_bindings):
        from soc_db.wikidata import refresh_vendor_knowledge

        caplog.set_level(logging.INFO)

        with (
            patch("soc_db.wikidata._cached_sparql") as mock_cached,
            patch("soc_db.wikidata.VENDOR_QIDS", {"Qualcomm": "Q544847"}),
        ):
            bindings_by_property = {
                "P2175": mock_sparql_bindings["results"]["bindings"],
                "P488": mock_gpu_bindings["results"]["bindings"],
                "P10620": mock_arch_bindings["results"]["bindings"],
            }

            def side_effect(query, **_kwargs):
                for prop, bindings in bindings_by_property.items():
                    if prop in query:
                        return bindings
                return []

            mock_cached.side_effect = side_effect

            result = refresh_vendor_knowledge(dry_run=True)
            assert result == {}  # dry_run returns empty dict
            assert "Wikidata refresh for Qualcomm" in caplog.text
            assert "process mappings" in caplog.text
            assert "GPU mappings" in caplog.text

    def test_empty_results_omits_vendor(self):
        from soc_db.wikidata import refresh_vendor_knowledge

        with (
            patch("soc_db.wikidata._cached_sparql", return_value=[]),
            patch("soc_db.wikidata.VENDOR_QIDS", {"Qualcomm": "Q544847"}),
        ):
            result = refresh_vendor_knowledge(dry_run=False)
            assert "Qualcomm" not in result


# ---------------------------------------------------------------------------
# Query builder unit tests
# ---------------------------------------------------------------------------

class TestQueryBuilders:
    def test_query_builders_return_strings(self):
        from soc_db.wikidata import _build_architecture_query, _build_gpu_query, _build_process_query

        qid = "Q544847"
        assert isinstance(_build_process_query(qid), str)
        assert isinstance(_build_gpu_query(qid), str)
        assert isinstance(_build_architecture_query(qid), str)

    def test_query_builders_contain_service_label(self):
        from soc_db.wikidata import _build_architecture_query, _build_gpu_query, _build_process_query

        qid = "Q544847"
        for query in (_build_process_query(qid), _build_gpu_query(qid), _build_architecture_query(qid)):
            assert "wikibase:label" in query
            assert "SERVICE" in query


# ---------------------------------------------------------------------------
# Merge layer tests (Task 2)
# ---------------------------------------------------------------------------

class TestMergeLayer:
    def test_merge_wikidata_into_existing(self, mock_vendor_knowledge):
        from soc_db.enrich._vendor_data_wikidata import merge_vendor_knowledge

        wikidata_result = {
            "Qualcomm": {
                "process_map": {"sm8750": 3, "sm8550": 4},
                "gpu_map": {"sm8750": "Adreno 830"},
                "architecture": "ARMv9",
            },
        }

        with patch("soc_db.enrich._vendor_data_wikidata._VENDOR_KNOWLEDGE_CACHE", mock_vendor_knowledge):
            merged = merge_vendor_knowledge(wikidata_result)

        # Existing entries preserved
        assert merged["Qualcomm"]["process_map"]["sm8450"] == 4
        # New entry added
        assert merged["Qualcomm"]["process_map"]["sm8750"] == 3
        # Architecture replaced (Wikidata takes precedence)
        assert merged["Qualcomm"]["architecture"] == "ARMv9"
        # MediaTek unchanged (no Wikidata results)
        assert merged["MediaTek"]["architecture"] == "ARMv8"

    def test_overrides_take_precedence(self, tmp_path, mock_vendor_knowledge):
        from soc_db.enrich._vendor_data_wikidata import merge_vendor_knowledge

        # Create temp overrides file
        overrides_file = tmp_path / "vendor_overrides.json"
        overrides_file.write_text(json.dumps({
            "Qualcomm": {
                "process_map": {"sm8550": 5},  # Override Wikidata's 4nm → 5nm
            }
        }))

        with (
            patch("soc_db.enrich._vendor_data_wikidata._VENDOR_KNOWLEDGE_CACHE", mock_vendor_knowledge),
            patch("soc_db.enrich._vendor_data_wikidata._OVERRIDES_PATH", overrides_file),
            patch("soc_db.enrich._vendor_data_wikidata._overrides_cache", None),  # Clear cache
        ):
            merged = merge_vendor_knowledge({
                "Qualcomm": {
                    "process_map": {"sm8550": 4, "sm8750": 3},
                },
            })

        # Override should win: 5 instead of 4
        assert merged["Qualcomm"]["process_map"]["sm8550"] == 5
        # New entry from Wikidata still added
        assert merged["Qualcomm"]["process_map"]["sm8750"] == 3

    def test_fallback_on_wikidata_failure(self, mock_vendor_knowledge):
        from soc_db.enrich._vendor_data_wikidata import get_vendor_knowledge

        with (
            patch("soc_db.wikidata.refresh_vendor_knowledge", side_effect=RuntimeError("Network error")),
            patch("soc_db.enrich._vendor_data_wikidata._VENDOR_KNOWLEDGE_CACHE", mock_vendor_knowledge),
            patch("soc_db.config.settings") as mock_settings,
        ):
            mock_settings.use_wikidata = True
            result = get_vendor_knowledge()

        # Fallback to hardcoded knowledge
        assert result is not None
        assert result["Qualcomm"]["architecture"] == "ARMv8"
        assert result["MediaTek"]["architecture"] == "ARMv8"

    def test_wikidata_disabled_returns_hardcoded(self, mock_vendor_knowledge):
        from soc_db.enrich._vendor_data_wikidata import get_vendor_knowledge

        with (
            patch("soc_db.enrich._vendor_data_wikidata._VENDOR_KNOWLEDGE_CACHE", mock_vendor_knowledge),
            patch("soc_db.config.settings") as mock_settings,
        ):
            mock_settings.use_wikidata = False
            result = get_vendor_knowledge()

        assert result is not None
        assert result is mock_vendor_knowledge  # Same reference

    def test_overrides_file_missing_returns_empty(self, tmp_path):
        from soc_db.enrich._vendor_data_wikidata import load_overrides

        missing = tmp_path / "nonexistent.json"
        with patch("soc_db.enrich._vendor_data_wikidata._overrides_cache", None):
            result = load_overrides(missing)
        assert result == {}

    def test_merge_does_not_remove_existing_models(self, mock_vendor_knowledge):
        from soc_db.enrich._vendor_data_wikidata import merge_vendor_knowledge

        # Wikidata returns only 1 GPU entry for Qualcomm
        wikidata_result = {
            "Qualcomm": {
                "gpu_map": {"sm8750": "Adreno 830"},
            },
        }

        with patch("soc_db.enrich._vendor_data_wikidata._VENDOR_KNOWLEDGE_CACHE", mock_vendor_knowledge):
            merged = merge_vendor_knowledge(wikidata_result)

        # All existing GPU entries preserved
        assert "sm8550" in merged["Qualcomm"]["gpu_map"]
        assert merged["Qualcomm"]["gpu_map"]["sm8550"] == "Adreno 740"
        # New entry added
        assert merged["Qualcomm"]["gpu_map"]["sm8750"] == "Adreno 830"

    def test_new_vendor_from_wikidata_added(self):
        """A vendor that exists in Wikidata but not in VENDOR_KNOWLEDGE should be added."""
        from soc_db.enrich._vendor_data_wikidata import merge_vendor_knowledge

        base_knowledge = {"Qualcomm": {"architecture": "ARMv8"}}
        wikidata_result = {
            "NewVendor": {
                "architecture": "RISC-V",
                "process_map": {"nv100": 7},
            },
        }

        with patch("soc_db.enrich._vendor_data_wikidata._VENDOR_KNOWLEDGE_CACHE", base_knowledge):
            merged = merge_vendor_knowledge(wikidata_result)

        assert "NewVendor" in merged
        assert merged["NewVendor"]["architecture"] == "RISC-V"
        assert merged["NewVendor"]["process_map"]["nv100"] == 7
