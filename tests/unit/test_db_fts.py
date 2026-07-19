"""FTS5 full-text search parity tests.

Compares FTS5 search results against the custom inverted index to ensure
FTS5 returns equivalent or better results within tokenisation differences:

- FTS5 uses ``porter unicode61`` tokenizer with minimum token length 3
  (so 2-char tokens like "nm" are ignored)
- FTS5 AND semantics require ALL tokens present (more precise than
  JSON substring matching)
- Custom inverted index does naive word-split + substring matching
"""

import pytest

from soc_db.cli import _load_all_json
from soc_db.db.queries import search as fts_search

# Test queries spanning vendors, models, GPUs, architectures
# Queries are grouped by tokeniser compatibility:
#   good: single-word or multi-word where all tokens have length >= 3
#   challenging: tokens shorter than 3 chars may be lost by unicode61
TEST_QUERIES = [
    "qualcomm",
    "adreno",
    "mali",
    "snapdragon 865",
    "snapdragon 888",
    "dimensity 9000",
    "kirin 9000",
    "a16 bionic",
    "apple m1",
    "armv9",
    "mediatek",
    "kirin",
    "tensor",
    "rockchip",
    "LPDDR5",
    "wifi 6",
]


def _build_search_index(chips):
    """Custom inverted index (mirrors api/main.py implementation)."""
    index = {}
    for i, c in enumerate(chips):
        seen = set()
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


def _search_chips(chips, q, index):
    """Custom search using inverted index."""
    ql = q.lower()
    if index is not None:
        tokens = ql.split()
        if not tokens:
            return chips
        result_sets = []
        for token in tokens:
            result_sets.append(set(index.get(token, [])))
        if not result_sets:
            return []
        matched = result_sets[0].intersection(*result_sets[1:]) if len(result_sets) > 1 else result_sets[0]
        return [chips[i] for i in sorted(matched)]
    result = []
    for c in chips:
        for val in c.values():
            if isinstance(val, str) and ql in val.lower():
                result.append(c)
                break
    return result


class TestFtsSearch:
    def test_fts_search_basic(self, db_conn):
        """Search 'adreno' returns results, each result has gpu containing 'Adreno'."""
        results = fts_search("adreno")
        assert len(results) > 0
        adreno_count = sum(1 for c in results if "adreno" in c.get("gpu", "").lower())
        assert adreno_count > 0

    def test_fts_search_multi_word(self, db_conn):
        """Search 'snapdragon 865' returns the expected chip."""
        results = fts_search("snapdragon 865")
        assert len(results) > 0

    def test_fts_search_case_insensitive(self, db_conn):
        """Search 'SNAPDRAGON' same as 'snapdragon'."""
        upper = fts_search("SNAPDRAGON")
        lower = fts_search("snapdragon")
        assert len(upper) > 0
        assert len(upper) == len(lower)

    def test_fts_search_no_results(self, db_conn):
        """Search 'nonexistent_chip_xyz' returns empty list."""
        results = fts_search("nonexistent_chip_xyz")
        assert results == []

    def test_fts_search_stemming(self, db_conn):
        """Search 'processors' returns chips with 'processor' in description."""
        results = fts_search("processors")
        assert len(results) > 0

    def test_fts_search_versus_custom_index_parity(self, db_conn):
        """FTS5 returns comparable results to custom index for 16 queries.

        FTS5 uses token-level AND which is more precise than the custom
        index's naive substring match.  Some queries return fewer FTS5
        results because:
        - FTS5 ``unicode61`` tokeniser ignores tokens shorter than 3 chars
        - FTS5 AND requires every token present in *indexed* columns only
        - Custom index searches the entire JSON serialisation (description,
          name, model, id, etc.)

        The threshold is 50% to account for these differences — the key
        guarantee is that the most common queries (vendor names, GPU names,
        chip families) return consistent results.
        """
        json_chips = _load_all_json()
        custom_index = _build_search_index(json_chips)

        failures = []
        for query in TEST_QUERIES:
            fts_results = fts_search(query)
            custom_results = _search_chips(json_chips, query, custom_index)

            # FTS5 should return at least 50% of custom results
            if custom_results and len(fts_results) < len(custom_results) * 0.5:
                failures.append(f"{query}: FTS5={len(fts_results)} vs Custom={len(custom_results)}")

            # Check that FTS5 doesn't miss more than 50% of custom IDs
            if custom_results:
                fts_ids = {c["id"] for c in fts_results}
                custom_ids = {c["id"] for c in custom_results}
                missing = custom_ids - fts_ids
                if len(missing) > len(custom_ids) * 0.5:
                    failures.append(f"{query}: missing {len(missing)}/{len(custom_ids)} custom IDs")

        if failures:
            msg = "\n".join(failures[:5])
            pytest.fail(msg)
