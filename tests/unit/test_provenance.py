"""Unit tests for soc-db provenance tracking module."""

import pytest

from soc_db.provenance import ConflictResolver, ProvenanceTracker, apply_provenance


class TestProvenanceTracker:
    def test_record_all_fields(self):
        tracker = ProvenanceTracker()
        chip = {"id": "test_1", "name": "Test", "vendor": "V", "cores": 8, "year": 2023}
        tracker.record(chip, "wikipedia")
        prov = chip.get("provenance", {})
        assert prov["name"] == "wikipedia"
        assert prov["cores"] == "wikipedia"
        assert prov["vendor"] == "wikipedia"
        assert "id" not in prov  # system field

    def test_record_skips_empty(self):
        tracker = ProvenanceTracker()
        chip = {"id": "test_1", "name": "Test", "vendor": "V", "cores": None, "gpu": ""}
        tracker.record(chip, "scraper")
        prov = chip.get("provenance", {})
        assert "name" in prov
        assert "cores" not in prov
        assert "gpu" not in prov

    def test_record_skips_zero(self):
        tracker = ProvenanceTracker()
        chip = {"id": "test_1", "name": "Test", "vendor": "V", "cores": 0, "ai_ops": 0.0}
        tracker.record(chip, "scraper")
        prov = chip.get("provenance", {})
        assert "cores" not in prov
        assert "ai_ops" not in prov

    def test_record_preserves_existing(self):
        tracker = ProvenanceTracker()
        chip = {"id": "test_1", "name": "Test", "vendor": "V", "provenance": {"name": "old_source"}}
        tracker.record(chip, "new_source")
        assert chip["provenance"]["name"] == "old_source"

    def test_record_force_overwrite(self):
        tracker = ProvenanceTracker()
        chip = {"id": "test_1", "name": "Test", "vendor": "V", "provenance": {"name": "old_source"}}
        tracker.record(chip, "new_source", force=True)
        assert chip["provenance"]["name"] == "new_source"

    def test_record_field(self):
        tracker = ProvenanceTracker()
        chip = {"id": "test_1", "name": "Test"}
        tracker.record_field(chip, "name", "manual")
        assert chip["provenance"]["name"] == "manual"

    def test_record_field_skips_system(self):
        tracker = ProvenanceTracker()
        chip = {"id": "test_1", "name": "Test"}
        tracker.record_field(chip, "id", "manual")
        assert "id" not in chip.get("provenance", {})

    def test_bulk_record(self):
        tracker = ProvenanceTracker()
        chip = {"id": "test_1", "name": "Test", "cores": 8}
        tracker.bulk_record(chip, {"name": "wiki", "cores": "wiki"})
        assert chip["provenance"]["name"] == "wiki"
        assert chip["provenance"]["cores"] == "wiki"

    def test_bulk_record_no_overwrite(self):
        tracker = ProvenanceTracker()
        chip = {"id": "test_1", "name": "Test", "provenance": {"name": "original"}}
        tracker.bulk_record(chip, {"name": "new_source"})
        assert chip["provenance"]["name"] == "original"

    def test_get_source(self):
        tracker = ProvenanceTracker()
        chip = {"provenance": {"name": "wikipedia"}}
        assert tracker.get_source(chip, "name") == "wikipedia"
        assert tracker.get_source(chip, "nonexistent") is None
        assert tracker.get_source({}, "name") is None

    def test_skips_system_fields(self):
        tracker = ProvenanceTracker()
        chip = {f: "x" for f in ["id", "sources", "completeness", "updated", "rating", "benchmarks"]}
        chip["name"] = "Test"
        tracker.record(chip, "source")
        prov = chip.get("provenance", {})
        assert prov.get("name") == "source"
        for sf in ["id", "sources", "completeness", "updated", "rating", "benchmarks"]:
            assert sf not in prov, f"System field {sf} should not be in provenance"


class TestConflictResolver:
    def test_agree_no_conflict(self):
        resolver = ConflictResolver()
        chip = {"id": "test"}
        result = resolver.resolve(chip, "cores", 8, 8, "wikipedia", "techpowerup")
        assert result == 8
        assert len(resolver.conflicts) == 0

    def test_disagree_keeps_current(self):
        resolver = ConflictResolver()
        chip = {"id": "test"}
        result = resolver.resolve(chip, "cores", 8, 4, "wikipedia", "techpowerup")
        assert result == 8
        assert len(resolver.conflicts) == 1
        conflict = resolver.conflicts[0]
        assert conflict["field"] == "cores"
        assert conflict["current_value"] == 8
        assert conflict["new_value"] == 4
        assert conflict["current_source"] == "wikipedia"
        assert conflict["new_source"] == "techpowerup"

    def test_empty_current_accepts_new(self):
        resolver = ConflictResolver()
        result = resolver.resolve({"id": "test"}, "gpu", None, "Adreno 650", None, "techpowerup")
        assert result == "Adreno 650"
        assert len(resolver.conflicts) == 0

    def test_empty_new_keeps_current(self):
        resolver = ConflictResolver()
        result = resolver.resolve({"id": "test"}, "gpu", "Adreno 650", None, "wikipedia", "techpowerup")
        assert result == "Adreno 650"
        assert len(resolver.conflicts) == 0

    def test_multiple_conflicts(self):
        resolver = ConflictResolver()
        resolver.resolve({"id": "test"}, "gpu", "Adreno 650", "Mali-G78", "wiki", "tpu")
        resolver.resolve({"id": "test"}, "cores", 8, 4, "wiki", "tpu")
        assert len(resolver.conflicts) == 2

    def test_clear(self):
        resolver = ConflictResolver()
        resolver.resolve({"id": "test"}, "gpu", "A", "B", "s1", "s2")
        assert len(resolver.conflicts) == 1
        resolver.clear()
        assert len(resolver.conflicts) == 0

    def test_zero_value_filled(self):
        resolver = ConflictResolver()
        result = resolver.resolve({"id": "test"}, "cores", 0, 8, "source_a", "source_b")
        assert result == 8  # zero is empty, accept new
        assert len(resolver.conflicts) == 0


class TestApplyProvenance:
    def test_basic(self):
        chip = {"id": "test_1", "name": "Test", "vendor": "V", "cores": 8}
        result = apply_provenance(chip, "legacy_v2")
        assert result is chip
        assert chip["provenance"]["name"] == "legacy_v2"
        assert chip["provenance"]["cores"] == "legacy_v2"
        assert "id" not in chip["provenance"]

    def test_default_source(self):
        chip = {"id": "test_1", "name": "Test"}
        result = apply_provenance(chip)
        assert result["provenance"]["name"] == "legacy_v2"

    def test_force_overwrite(self):
        chip = {"id": "test_1", "name": "Test", "provenance": {"name": "old"}}
        result = apply_provenance(chip, "new_source", force=True)
        assert result["provenance"]["name"] == "new_source"

    def test_no_overwrite_by_default(self):
        chip = {"id": "test_1", "name": "Test", "provenance": {"name": "old"}}
        result = apply_provenance(chip, "new_source")
        assert result["provenance"]["name"] == "old"

    def test_skips_system_fields(self):
        chip = {"id": "test", "name": "Test", "sources": {}, "completeness": 0.5}
        result = apply_provenance(chip)
        assert result["provenance"]["name"] == "legacy_v2"
        assert "sources" not in result["provenance"]
        assert "completeness" not in result["provenance"]

    def test_empty_chip(self):
        chip = {"id": "test"}
        result = apply_provenance(chip)
        assert result["provenance"] == {}
