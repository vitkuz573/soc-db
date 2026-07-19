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

    def test_new_v3_fields_default_none(self):
        chip = Chip(id="test_1", name="Test", vendor="Test")
        assert chip.market_segment is None
        assert chip.charging_max_w is None
        assert chip.wifi_version is None
        assert chip.modem_5g_mmwave is None
        assert chip.video_decode_av1 is None
        assert chip.video_encode_av1 is None
        assert chip.ai_int8_tops is None
        assert chip.ai_fp16_tflops is None
        assert chip.pcie_version is None
        assert chip.usb_version is None
        assert chip.bluetooth_version is None
        assert chip.satellite_connectivity is None
        assert chip.gnss is None
        assert chip.fingerprint is None
        assert chip.display_max_refresh is None
        assert chip.display_resolution is None
        assert chip.camera_max_mp is None
        assert chip.video_capture_max is None
        assert chip.isp_config is None
        assert chip.dsp_type is None
        assert chip.security is None
        assert chip.av1_decode is None
        assert chip.arm_cores_total is None
        assert chip.performance_cores is None
        assert chip.efficiency_cores is None
        assert chip.l2_cache is None
        assert chip.l3_cache is None
        assert chip.soc_id is None
        assert chip.package is None
        assert chip.die_size is None
        assert chip.provenance is None

    def test_new_v3_fields_set_values(self):
        chip = Chip(
            id="test_1",
            name="Test",
            vendor="Test",
            market_segment="mobile",
            charging_max_w=120,
            wifi_version="Wi-Fi 7",
            modem_5g_mmwave=True,
            video_decode_av1=True,
            video_encode_av1=False,
            ai_int8_tops=45.0,
            ai_fp16_tflops=22.5,
            pcie_version="PCIe 4.0",
            usb_version="USB4",
            bluetooth_version="5.4",
            satellite_connectivity=True,
            gnss="GPS+GLONASS+BeiDou",
            fingerprint="under-display",
            display_max_refresh=144,
            display_resolution="3840x2160",
            camera_max_mp=200,
            video_capture_max="8K30",
            isp_config="triple ISP",
            dsp_type="Hexagon",
            security="Titan M",
            av1_decode=True,
            arm_cores_total=8,
            performance_cores=4,
            efficiency_cores=4,
            l2_cache="512KB",
            l3_cache="8MB",
            soc_id="SM8550-AB",
            package="FCCSP",
            die_size="120.5 mm²",
            provenance={"name": "legacy_v2", "cores": "legacy_v2"},
        )
        assert chip.market_segment == "mobile"
        assert chip.charging_max_w == 120
        assert chip.wifi_version == "Wi-Fi 7"
        assert chip.modem_5g_mmwave is True
        assert chip.video_decode_av1 is True
        assert chip.video_encode_av1 is False
        assert chip.ai_int8_tops == 45.0
        assert chip.ai_fp16_tflops == 22.5
        assert chip.pcie_version == "PCIe 4.0"
        assert chip.usb_version == "USB4"
        assert chip.bluetooth_version == "5.4"
        assert chip.satellite_connectivity is True
        assert chip.gnss == "GPS+GLONASS+BeiDou"
        assert chip.fingerprint == "under-display"
        assert chip.display_max_refresh == 144
        assert chip.display_resolution == "3840x2160"
        assert chip.camera_max_mp == 200
        assert chip.video_capture_max == "8K30"
        assert chip.isp_config == "triple ISP"
        assert chip.dsp_type == "Hexagon"
        assert chip.security == "Titan M"
        assert chip.av1_decode is True
        assert chip.arm_cores_total == 8
        assert chip.performance_cores == 4
        assert chip.efficiency_cores == 4
        assert chip.l2_cache == "512KB"
        assert chip.l3_cache == "8MB"
        assert chip.soc_id == "SM8550-AB"
        assert chip.package == "FCCSP"
        assert chip.die_size == "120.5 mm²"
        assert chip.provenance == {"name": "legacy_v2", "cores": "legacy_v2"}

    def test_v3_fields_backward_compat(self):
        """Existing chip data should still work — new fields are optional."""
        chip = Chip(id="sm8250", name="Snapdragon 865", vendor="Qualcomm", cores=8, year=2020)
        assert chip.cores == 8
        assert chip.year == 2020
        assert chip.market_segment is None
        assert chip.ai_int8_tops is None


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


class TestSearchIndex:
    def test_build_search_index(self):
        from api.main import _build_search_index, _search_chips

        chips = [{"id": "chip_a", "name": "Snapdragon 888", "vendor": "Qualcomm"}, {"id": "chip_b", "name": "Exynos 2200", "vendor": "Samsung"}]
        index = _build_search_index(chips)
        assert "snapdragon" in index
        assert "qualcomm" in index
        assert "888" in index
        result = _search_chips(chips, "snapdragon", index)
        assert len(result) == 1
        assert result[0]["id"] == "chip_a"

    def test_search_fallback(self):
        from api.main import _search_chips

        chips = [{"id": "test_1", "name": "Test Processor", "vendor": "TestCorp"}]
        result = _search_chips(chips, "processor", None)
        assert len(result) == 1
        assert result[0]["id"] == "test_1"


class TestMetricsResponse:
    def test_metrics(self):
        m = MetricsResponse(uptime_seconds=3600, total_requests=1000, requests_per_second=0.28, chips_cached=500, active_rate_limit_clients=3)
        assert m.total_requests == 1000
