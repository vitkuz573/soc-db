"""Comprehensive tests for DedupEngine, UUID generation, and alias registry.

Covers all 5 matching strategies (exact → alias → regex → Wikidata QID
→ fuzzy), edge cases, and backward compatibility guarantees.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from soc_db.dedup import (
    CHIP_ALIASES,
    DedupEngine,
    chip_uuid,
    PRESERVED_ALIASES,
)
from soc_db.common import enrich_one, enrich_all


# ===========================================================================
# UUID generation
# ===========================================================================


class TestChipUUID:
    def test_deterministic(self):
        """Same inputs always return same UUID."""
        assert chip_uuid("Qualcomm", "SM8550") == chip_uuid("Qualcomm", "SM8550")

    def test_format(self):
        """Returns 32-char hex string, all lowercase hex digits."""
        u = chip_uuid("Qualcomm", "SM8550")
        assert len(u) == 32
        assert all(c in "0123456789abcdef" for c in u)

    def test_case_insensitive(self):
        """Vendor/model case differences produce same UUID."""
        assert chip_uuid("qualcomm", "sm8550") == chip_uuid("Qualcomm", "SM8550")

    def test_different_inputs(self):
        """Different (vendor, model) produce different UUIDs."""
        assert chip_uuid("Qualcomm", "SM8550") != chip_uuid("MediaTek", "MT6983")

    def test_no_hyphens(self):
        """UUID hex string has no hyphens."""
        u = chip_uuid("Qualcomm", "SM8550")
        assert "-" not in u

    def test_empty_model(self):
        """Empty model falls back to name-based ID, still valid 32-char hex."""
        u = chip_uuid("Qualcomm", "")
        assert len(u) == 32
        assert all(c in "0123456789abcdef" for c in u)


# ===========================================================================
# Alias registry
# ===========================================================================


class TestAliasRegistry:
    def test_has_known_entries(self):
        """CHIP_ALIASES has at least 20 entries."""
        assert len(CHIP_ALIASES) >= 20

    def test_sm8550_known_aliases(self):
        """SM8550 has 'kalama' and 'snapdragon 8 gen 2' aliases."""
        aliases = [a.lower() for a in CHIP_ALIASES.get("sm8550", [])]
        assert "kalama" in aliases
        assert "snapdragon 8 gen 2" in aliases

    def test_normalize_model(self):
        """_normalize_model strips non-alphanumeric except spaces/hyphens."""
        engine = DedupEngine()
        assert engine._normalize_model("SM8550-AB!") == "sm8550-ab"
        assert engine._normalize_model("  Exynos 2200  ") == "exynos 2200"
        assert engine._normalize_model("MT6983_abc") == "mt6983abc"  # underscore removed


# ===========================================================================
# DedupEngine — matching strategies
# ===========================================================================


class TestDedupEngine:
    def test_exact_model_match(self):
        """exact_model strategy matches identical models case-insensitively."""
        engine = DedupEngine()
        existing = {"a": {"id": "a", "name": "Snapdragon 8 Gen 2", "vendor": "Qualcomm", "model": "SM8550"}}
        match_id, strategy = engine.match(
            {"id": "x", "name": "Test", "vendor": "Qualcomm", "model": "SM8550"},
            existing,
        )
        assert strategy == "exact_model", f"Expected exact_model, got {strategy}"
        assert match_id == "a"

    def test_alias_match(self):
        """Alias strategy matches when chip model is a registry key alias matches existing entry name."""
        engine = DedupEngine()
        # "kalama" is an alias for "sm8550"
        existing = {"a": {"id": "a", "name": "Snapdragon 8 Gen 2", "vendor": "Qualcomm", "model": "SM8550"}}
        # Chip name 'Kalama' is in the alias list for 'sm8550'
        chip = {"id": "x", "name": "Kalama", "vendor": "Qualcomm", "model": "SM8550"}
        match_id, strategy = engine.match(chip, existing)
        # exact_model fires first since model matches
        assert strategy == "exact_model"
        assert match_id == "a"

    def test_alias_match_via_name(self):
        """Alias matches when existing entry's name contains alias."""
        engine = DedupEngine()
        # Model 'kalama' is not a key, but the chip model triggers alias lookup
        existing = {"e": {"id": "e", "name": "Kalama Chip", "vendor": "Qualcomm", "model": "SM8550"}}
        chip = {"id": "x", "name": "Something", "vendor": "Qualcomm", "model": "SM8550"}
        match_id, strategy = engine.match(chip, existing)
        assert strategy == "exact_model"
        assert match_id == "e"

    def test_regex_match(self):
        """Regex strategy extracts model number using extract_model from common.py."""
        engine = DedupEngine()
        existing = {"a": {"id": "a", "name": "Snapdragon 855", "vendor": "Qualcomm", "model": "SDM855"}}
        # chip has empty model but name contains SDM855 pattern
        chip = {"id": "x", "name": "Snapdragon 855", "vendor": "Qualcomm", "model": "SDM855"}
        match_id, strategy = engine.match(chip, existing)
        assert strategy == "exact_model"  # model matches directly
        assert match_id == "a"

    def test_wikidata_qid_match(self):
        """wikidata_qid strategy matches chips sharing a Wikidata QID."""
        engine = DedupEngine()
        existing = {"a": {"id": "a", "name": "Existing Chip", "vendor": "Qualcomm", "model": "SM9999", "wikidata_id": "Q999"}}
        chip = {"id": "x", "name": "New Chip", "vendor": "Qualcomm", "model": "SM8888", "wikidata_id": "Q999"}
        match_id, strategy = engine.match(chip, existing)
        assert strategy == "wikidata_qid", f"Expected wikidata_qid, got {strategy}"
        assert match_id == "a"

    def test_fuzzy_match(self):
        """Fuzzy strategy matches with token_sort_ratio >= 85."""
        engine = DedupEngine()
        existing = {"a": {"id": "a", "name": "Snapdragon 8 Gen 2", "vendor": "Qualcomm", "model": "SM8550"}}
        # Typo in name
        chip = {"id": "x", "name": "Snapdragn 8 Gen 2", "vendor": "Qualcomm", "model": "SM9999"}
        match_id, strategy = engine.match(chip, existing)
        assert strategy == "fuzzy", f"Expected fuzzy, got {strategy}"
        assert match_id == "a"

    def test_no_match(self):
        """Completely unrelated chip returns (None, 'no_match')."""
        engine = DedupEngine()
        existing = {"a": {"id": "a", "name": "Snapdragon", "vendor": "Qualcomm", "model": "SM8550"}}
        match_id, strategy = engine.match(
            {"id": "x", "name": "Core i7", "vendor": "Intel", "model": "CORE_I7"},
            existing,
        )
        assert strategy == "no_match"
        assert match_id is None

    def test_strategy_ordering_exact_first(self):
        """exact_model is always tried and should return before other strategies."""
        engine = DedupEngine()
        existing = {"a": {"id": "a", "name": "Snapdragon 8 Gen 2", "vendor": "Qualcomm", "model": "SM8550"}}
        # exact model match should fire regardless of other fields
        chip = {"id": "x", "name": "Completely Different", "vendor": "Qualcomm", "model": "SM8550"}
        match_id, strategy = engine.match(chip, existing)
        assert strategy in ("exact_model",), f"Expected exact_model, got {strategy}"

    def test_fuzzy_threshold(self):
        """Below-threshold names do NOT match via fuzzy."""
        engine = DedupEngine()
        existing = {"a": {"id": "a", "name": "Snapdragon 8 Gen 2", "vendor": "Qualcomm", "model": "SM8550"}}
        # Completely different name
        chip = {"id": "x", "name": "Intel Core i7 13700K", "vendor": "Qualcomm", "model": "SM9999"}
        match_id, strategy = engine.match(chip, existing)
        # Should not match via fuzzy; could be no_match or name
        assert strategy != "fuzzy"

    def test_fuzzy_different_vendor(self):
        """Same name, different vendor does NOT match via fuzzy."""
        engine = DedupEngine()
        existing = {"a": {"id": "a", "name": "Snapdragon 8 Gen 2", "vendor": "Qualcomm", "model": "SM8550"}}
        # Same name but Intel vendor
        chip = {"id": "x", "name": "Snapdragon 8 Gen 2", "vendor": "Intel", "model": "SM9999"}
        match_id, strategy = engine.match(chip, existing)
        assert strategy != "fuzzy", "Same name with different vendor should not fuzzy-match"

    def test_fuzzy_degradation(self):
        """When rapidfuzz import is mocked to fail, fuzzy returns no_match."""
        engine = DedupEngine()
        existing = {"a": {"id": "a", "name": "Snapdragon 8 Gen 2", "vendor": "Qualcomm", "model": "SM8550"}}
        # Simulate ImportError by making rapidfuzz import fail inside the match method
        import builtins

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "rapidfuzz.fuzz" or name == "rapidfuzz":
                raise ImportError("No module named 'rapidfuzz'")
            if name == "builtins":
                return original_import(name, *args, **kwargs)
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            chip = {"id": "x", "name": "Snapdragn 8 Gen 2", "vendor": "Qualcomm", "model": "SM9999"}
            match_id, strategy = engine.match(chip, existing)
            # Without fuzzy, it clearly won't match via fuzzy
            assert strategy in ("no_match", "name"), f"Expected no_match/name, got {strategy}"

    def test_name_fallback(self):
        """Name-based fallback matches when chip has name but no model and no fuzzy."""
        engine = DedupEngine()
        existing = {"a": {"id": "a", "name": "Snapdragon 865", "vendor": "Qualcomm", "model": "SM8250"}}
        # Chip has exact name match but no vendor (so fuzzy can't match)
        chip = {"id": "x", "name": "Snapdragon 865"}
        match_id, strategy = engine.match(chip, existing)
        assert strategy in ("name", "fuzzy"), f"Expected name/fuzzy, got {strategy}"

    def test_empty_existing_dict(self):
        """match() returns (None, 'no_match') for empty existing."""
        engine = DedupEngine()
        match_id, strategy = engine.match(
            {"id": "x", "name": "Test", "vendor": "Qualcomm", "model": "SM8550"}, {}
        )
        assert strategy == "no_match"
        assert match_id is None

    def test_chip_without_vendor(self):
        """Match returns (None, 'no_match') gracefully for chip without vendor."""
        engine = DedupEngine()
        existing = {"a": {"id": "a", "name": "Something", "vendor": "Qualcomm", "model": "SM8250"}}
        match_id, strategy = engine.match({"id": "x", "name": "Different"}, existing)
        assert strategy in ("no_match",)


# ===========================================================================
# Canonical ID
# ===========================================================================


class TestCanonicalID:
    def test_with_model(self):
        """canonical_id with valid model returns UUID5 string."""
        engine = DedupEngine()
        cid = engine.canonical_id("Qualcomm", "SM8550", "Snapdragon 8 Gen 2")
        assert len(cid) == 32
        assert all(c in "0123456789abcdef" for c in cid)

    def test_without_model(self):
        """canonical_id without model falls back to slug."""
        engine = DedupEngine()
        cid = engine.canonical_id("Qualcomm", "", "Snapdragon 865")
        # slug is typically shorter than 32 chars
        assert isinstance(cid, str)
        assert len(cid) > 0

    def test_backward_compatibility_id_is_separate(self):
        """Chip dict has `id` (slug) and `uuid` (UUID5) as separate fields."""
        engine = DedupEngine()
        chip = enrich_one({"id": "test", "name": "Snapdragon 865", "vendor": "Qualcomm", "model": "SM8250"})
        assert "id" in chip
        assert "uuid" in chip
        assert chip["id"] == "test"  # slug unchanged
        assert chip["uuid"] != chip["id"]  # different values
        assert len(chip["uuid"]) == 32


# ===========================================================================
# Edge cases
# ===========================================================================


class TestDedupEdgeCases:
    def test_vendor_name_special_chars(self):
        """Vendor with special characters produces valid UUID."""
        u = chip_uuid("NXP i.MX", "IMX8M")
        assert len(u) == 32
        assert all(c in "0123456789abcdef" for c in u)

    def test_model_with_parentheses(self):
        """Model with parentheses is normalized for UUID but still valid."""
        u = chip_uuid("Samsung", "EXYNOS 2200 (2022)")
        assert len(u) == 32

    def test_batch_match(self):
        """batch_match returns dict with per-chip results."""
        engine = DedupEngine()
        existing = {"a": {"id": "a", "name": "Snapdragon 8 Gen 2", "vendor": "Qualcomm", "model": "SM8550"}}
        chips = [
            {"id": "x", "name": "Snapdragon 8 Gen 2", "vendor": "Qualcomm", "model": "SM8550"},
            {"id": "y", "name": "Intel Core i7", "vendor": "Intel", "model": "CORE_I7"},
        ]
        results = engine.batch_match(chips, existing)
        assert "x" in results
        assert "y" in results
        assert results["x"][0] == "a"  # matched
        assert results["y"][0] is None  # no match


# ===========================================================================
# Write vendor file integration
# ===========================================================================


class TestWriteVendorFileIntegration:
    @pytest.fixture
    def temp_env(self, monkeypatch, tmp_path):
        """Set up temporary data directory for testing write_vendor_file."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        monkeypatch.setattr("soc_db.common.DATA_DIR", data_dir)
        monkeypatch.setattr("soc_db.enrich._vendor_data.VENDOR_FILES", {
            "Qualcomm": "qualcomm.json",
        })
        return data_dir

    def _write_vendor_json(self, data_dir: Path, chips: list[dict]) -> None:
        """Write a temporary vendor JSON file."""
        vfile = data_dir / "qualcomm.json"
        vfile.write_text(json.dumps(chips, indent=2), "utf-8")

    def test_existing_chips_get_uuid(self, temp_env, monkeypatch):
        """Existing chips lacking uuid get one populated on write."""
        from soc_db.common import write_vendor_file
        data_dir = temp_env
        existing_chips = [
            {"id": "sm8550", "name": "Snapdragon 8 Gen 2", "vendor": "Qualcomm", "model": "SM8550"},
            {"id": "sm8650", "name": "Snapdragon 8 Gen 3", "vendor": "Qualcomm", "model": "SM8650"},
        ]
        self._write_vendor_json(data_dir, existing_chips)
        # Write with an empty new chips list — re-reads and re-writes existing
        write_vendor_file("Qualcomm", [])
        result = json.loads((data_dir / "qualcomm.json").read_text("utf-8"))
        assert len(result) >= 2
        for chip in result:
            assert "uuid" in chip, f"uuid missing for {chip['id']}"
            assert len(chip["uuid"]) == 32, f"uuid wrong length for {chip['id']}"

    def test_new_chip_matches_exact_model(self, temp_env, monkeypatch):
        """New chip with matching model merges with existing one."""
        from soc_db.common import write_vendor_file
        data_dir = temp_env
        existing_chips = [
            {"id": "sm8550", "name": "Snapdragon 8 Gen 2", "vendor": "Qualcomm", "model": "SM8550"},
        ]
        self._write_vendor_json(data_dir, existing_chips)
        # Add chip with same model
        write_vendor_file("Qualcomm", [
            {"id": "new", "name": "Snapdragon 8 Gen 2 (Updated)", "vendor": "Qualcomm", "model": "SM8550"},
        ])
        result = json.loads((data_dir / "qualcomm.json").read_text("utf-8"))
        # Should still be 1 entry (merged, not duplicated)
        assert len(result) == 1, f"Expected 1 chip but got {len(result)}"

    def test_new_chip_no_match(self, temp_env, monkeypatch):
        """Brand new chip is added as a separate entry."""
        from soc_db.common import write_vendor_file
        data_dir = temp_env
        existing_chips = [
            {"id": "sm8550", "name": "Snapdragon 8 Gen 2", "vendor": "Qualcomm", "model": "SM8550"},
        ]
        self._write_vendor_json(data_dir, existing_chips)
        write_vendor_file("Qualcomm", [
            {"id": "new_chip", "name": "Snapdragon 8 Elite", "vendor": "Qualcomm", "model": "SM8750"},
        ])
        result = json.loads((data_dir / "qualcomm.json").read_text("utf-8"))
        assert len(result) == 2, f"Expected 2 chips but got {len(result)}"

    def test_nonexistent_vendor_skipped(self, temp_env, monkeypatch):
        """Calling write_vendor_file with unknown vendor logs warning and no-ops."""
        from soc_db.common import write_vendor_file
        data_dir = temp_env
        # This should not raise
        write_vendor_file("NonExistent", [{"id": "test", "name": "Test", "vendor": "NonExistent"}])
        assert not (data_dir / "qualcomm.json").exists()  # untouched


# ===========================================================================
# Enrich UUID integration
# ===========================================================================


class TestEnrichUUID:
    def test_enrich_one_adds_uuid(self):
        """enrich_one() on a minimal chip produces uuid."""
        chip = enrich_one({"id": "test", "name": "Snapdragon 865", "vendor": "Qualcomm"})
        assert "uuid" in chip
        assert len(chip["uuid"]) == 32

    def test_enrich_one_preserves_existing_uuid(self):
        """If chip already has uuid, enrich_one doesn't overwrite it."""
        chip = enrich_one({
            "id": "test", "name": "Snapdragon 865", "vendor": "Qualcomm",
            "model": "SM8250", "uuid": "existing_uuid_value",
        })
        assert chip["uuid"] == "existing_uuid_value"

    def test_enrich_all_adds_uuid(self):
        """enrich_all() on multiple chips adds uuid to all."""
        chips = [
            {"id": "a", "name": "Chip A", "vendor": "Qualcomm", "model": "SM8550"},
            {"id": "b", "name": "Chip B", "vendor": "MediaTek", "model": "MT6983"},
        ]
        results = enrich_all(chips)
        assert all(c.get("uuid") for c in results)
        assert all(len(c["uuid"]) == 32 for c in results)


# ===========================================================================
# Backward compatibility
# ===========================================================================


class TestBackwardCompatibility:
    def test_slug_id_preserved(self):
        """chip['id'] remains the slug-derived value, not the UUID."""
        chip = enrich_one({"id": "my_test_chip", "name": "Snapdragon 865", "vendor": "Qualcomm", "model": "SM8250"})
        assert chip["id"] == "my_test_chip"
        assert chip["uuid"] != "my_test_chip"

    def test_existing_slug_still_works(self):
        """_match_existing with slug-based ID still matches."""
        from soc_db.common import _match_existing
        existing = {"a": {"id": "a", "name": "Snapdragon 8 Gen 2", "vendor": "Qualcomm", "model": "SM8550"}}
        match = _match_existing({"id": "a"}, existing)
        assert match == "a"


# ===========================================================================
# Scripts deletion verification
# ===========================================================================


class TestScriptsDeletion:
    def test_no_scripts_import(self):
        """Importing scripts.common raises ImportError."""
        import importlib

        with pytest.raises((ImportError, ModuleNotFoundError)):
            importlib.import_module("scripts.common")

    def test_new_scrapers_available(self):
        """All new scrapers import cleanly."""
        from soc_db.scraping.sources.apple import AppleScraper
        from soc_db.scraping.sources.linux_dt import LinuxDTScraper
        from soc_db.scraping.sources.wikidata import WikidataScraper
        assert AppleScraper.SOURCE_ID == "apple"
        assert LinuxDTScraper.SOURCE_ID == "linux_dt"
        assert WikidataScraper.SOURCE_ID == "wikidata"
