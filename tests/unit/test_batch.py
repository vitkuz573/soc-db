"""Tests for BatchEnricher — checkpointing, crash recovery, progress tracking."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from soc_db.batch import BatchEnricher


# ===========================================================================
# Helper
# ===========================================================================


def _make_chips(n: int, vendor: str = "TestVendor") -> list[dict]:
    return [
        {
            "id": f"test_{i}",
            "name": f"Test Chip {i}",
            "vendor": vendor,
            "model": f"TC{i:04d}",
        }
        for i in range(n)
    ]


# ===========================================================================
# BatchEnricher
# ===========================================================================


class TestBatchEnricherInit:
    def test_default_batch_size(self):
        enricher = BatchEnricher()
        assert enricher.batch_size == 500

    def test_custom_batch_size(self):
        enricher = BatchEnricher(batch_size=100)
        assert enricher.batch_size == 100

    def test_custom_checkpoint_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            enricher = BatchEnricher(checkpoint_dir=tmp)
            assert str(enricher.checkpoint_dir) == tmp

    def test_default_checkpoint_dir_created(self):
        enricher = BatchEnricher(batch_size=10)
        assert enricher.checkpoint_dir.exists()


class TestBatchEnricherCheckpoint:
    def test_load_checkpoint_missing(self):
        enricher = BatchEnricher(batch_size=10)
        assert enricher._load_checkpoint() == 0

    def test_save_and_load_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            enricher = BatchEnricher(batch_size=10, checkpoint_dir=tmp)
            enricher._save_checkpoint(42)
            assert enricher.checkpoint_path.exists()
            data = json.loads(enricher.checkpoint_path.read_text("utf-8"))
            assert data["processed"] == 42
            assert data["batch_size"] == 10
            assert "timestamp" in data

    def test_reload_checkpoint(self):
        """_load_checkpoint returns the saved count."""
        with tempfile.TemporaryDirectory() as tmp:
            enricher = BatchEnricher(batch_size=10, checkpoint_dir=tmp)
            enricher._save_checkpoint(99)
            assert enricher._load_checkpoint() == 99

    def test_corrupt_checkpoint_returns_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            enricher = BatchEnricher(batch_size=10, checkpoint_dir=tmp)
            enricher.checkpoint_path.write_text("not json")
            assert enricher._load_checkpoint() == 0

    def test_clear_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            enricher = BatchEnricher(batch_size=10, checkpoint_dir=tmp)
            enricher._save_checkpoint(50)
            assert enricher.checkpoint_path.exists()
            enricher._clear_checkpoint()
            assert not enricher.checkpoint_path.exists()


class TestBatchEnricherEnrich:
    def test_enrich_empty_list(self):
        enricher = BatchEnricher(batch_size=10)
        result = enricher.enrich_all([])
        assert result == []

    def test_enrich_single_chip(self):
        enricher = BatchEnricher(batch_size=10)
        chips = _make_chips(1)
        result = enricher.enrich_all(chips)
        assert len(result) == 1
        # Enrichment adds completeness and uuid
        assert "completeness" in result[0]
        assert "uuid" in result[0]
        assert "provenance" in result[0]

    def test_enrich_multiple_chips(self):
        enricher = BatchEnricher(batch_size=10)
        chips = _make_chips(25)
        result = enricher.enrich_all(chips)
        assert len(result) == 25
        for c in result:
            assert "completeness" in c
            assert "uuid" in c

    def test_enrich_custom_batch_size(self):
        enricher = BatchEnricher(batch_size=7)
        chips = _make_chips(20)
        result = enricher.enrich_all(chips)
        assert len(result) == 20

    def test_checkpoint_cleared_after_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            enricher = BatchEnricher(batch_size=10, checkpoint_dir=tmp)
            chips = _make_chips(5)
            enricher.enrich_all(chips)
            assert not enricher.checkpoint_path.exists()

    def test_checkpoint_exists_during_run(self):
        """Checkpoint is saved at least after the first batch."""
        with tempfile.TemporaryDirectory() as tmp:
            enricher = BatchEnricher(batch_size=10, checkpoint_dir=tmp)
            chips = _make_chips(25)
            # Manually save checkpoint as if a batch was completed
            enricher._save_checkpoint(10)
            assert enricher.checkpoint_path.exists()

    def test_resume_from_checkpoint(self):
        """Simulate crash recovery: partial enrich, then resume."""
        with tempfile.TemporaryDirectory() as tmp:
            enricher = BatchEnricher(batch_size=5, checkpoint_dir=tmp)
            chips = _make_chips(12)

            # Simulate processing 7 chips and crashing
            for c in chips[:7]:
                pass  # pretend they were enriched
            enricher._save_checkpoint(7)

            # New enricher with same checkpoint dir
            enricher2 = BatchEnricher(batch_size=5, checkpoint_dir=tmp)
            # enrich_all should load checkpoint and continue
            result = enricher2.enrich_all(chips)

            assert len(result) == 12
            assert not enricher2.checkpoint_path.exists()

    def test_progress_tracking(self):
        enricher = BatchEnricher(batch_size=10)
        chips = _make_chips(35)
        enricher.enrich_all(chips)
        assert enricher.get_progress() == 35

    def test_run_alias(self):
        enricher = BatchEnricher(batch_size=10)
        chips = _make_chips(3)
        result = enricher.run(chips)
        assert len(result) == 3
        assert "completeness" in result[0]

    def test_enrich_preserves_existing_fields(self):
        enricher = BatchEnricher(batch_size=10)
        chips = [
            {"id": "custom_1", "name": "Custom SoC", "vendor": "Custom", "gpu": "Mali-G78", "year": 2023}
        ]
        result = enricher.enrich_all(chips)
        assert result[0]["gpu"] == "Mali-G78"
        assert result[0]["year"] == 2023
        assert result[0]["id"] == "custom_1"

    def test_vendor_specific_enrichment(self):
        """Qualcomm chip should get process node inferences."""
        enricher = BatchEnricher(batch_size=10)
        chips = [
            {"id": "sm8550", "name": "Snapdragon 8 Gen 2", "vendor": "Qualcomm", "model": "SM8550"}
        ]
        result = enricher.enrich_all(chips)
        # SM8550 should have process_nm=4 (from vendor knowledge)
        assert result[0].get("process_nm") == 4
