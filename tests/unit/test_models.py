import pytest
from pydantic import ValidationError

from soc_db.models import Chip, ChipListResponse, MetricsResponse, StatsResponse, VendorInfo, VendorResponse


class TestChipModel:
    def test_minimal_chip(self):
        chip = Chip(id="test_1", name="Test Chip", vendor="TestCorp")
        assert chip.id == "test_1"
        assert chip.name == "Test Chip"
        assert chip.vendor == "TestCorp"
        assert chip.completeness is None
        assert chip.status == "unknown"

    def test_invalid_id(self):
        with pytest.raises(ValidationError):
            Chip(id="UPPERCASE", name="Test", vendor="Test")

    def test_full_chip(self):
        chip = Chip(
            id="test_1",
            name="Test Chip",
            vendor="TestCorp",
            model="TC-100",
            cores=8,
            year=2023,
            completeness=0.85,
        )
        assert chip.cores == 8
        assert chip.year == 2023
        assert chip.completeness == 0.85

    def test_extra_fields_ignored(self):
        chip = Chip(id="test_1", name="Test", vendor="Test", unknown_field="should be ignored")
        assert not hasattr(chip, "unknown_field")

    def test_completeness_bounds(self):
        with pytest.raises(ValidationError):
            Chip(id="test_1", name="Test", vendor="Test", completeness=1.5)


class TestVendorResponse:
    def test_vendor_info(self):
        resp = VendorResponse(root={"Qualcomm": VendorInfo(count=100, avg_completeness=0.75)})
        assert resp.root["Qualcomm"].count == 100
        assert resp.root["Qualcomm"].avg_completeness == 0.75


class TestChipListResponse:
    def test_chip_list(self):
        chip = Chip(id="test_1", name="Test", vendor="Test")
        resp = ChipListResponse(total=1, offset=0, limit=10, data=[chip])
        assert resp.total == 1
        assert len(resp.data) == 1


class TestStatsResponse:
    def test_stats(self):
        stats = StatsResponse(
            total_chips=100,
            total_vendors=5,
            year_min=2010,
            year_max=2024,
            avg_completeness=0.6,
            fields_present={"gpu": 80, "architecture": 100},
        )
        assert stats.total_chips == 100


class TestMetricsResponse:
    def test_metrics(self):
        m = MetricsResponse(uptime_seconds=3600, total_requests=1000, requests_per_second=0.28, chips_cached=500, active_rate_limit_clients=3)
        assert m.total_requests == 1000
