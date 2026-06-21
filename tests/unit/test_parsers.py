"""Unit tests for soc-db cell parsers."""

from soc_db.parsers import (
    detect_columns,
    parse_camera,
    parse_cell,
    parse_connectivity,
    parse_cpu,
    parse_display,
    parse_gpu,
    parse_memory,
    parse_modem,
    parse_process,
    parse_video,
    parse_year,
)


class MockCell:
    def __init__(self, text):
        self._text = text

    def get_text(self, sep=" ", strip=True):
        return self._text


class TestParseCPU:
    def test_cores_only(self):
        assert parse_cpu("8-core") == {"cores": 8}

    def test_cluster_config(self):
        result = parse_cpu("1x 3.0 GHz Cortex-X2 + 3x 2.5 GHz Cortex-A710 + 4x 1.8 GHz Cortex-A510")
        assert result.get("cores") == 8
        assert "cluster_config" in result
        assert result.get("architecture") == "ARMv8.2-A"

    def test_empty(self):
        assert parse_cpu("") == {}
        assert parse_cpu(None) == {}


class TestParseGPU:
    def test_gpu_name(self):
        assert parse_gpu("Adreno 650").get("gpu") == "Adreno 650"

    def test_gpu_with_clock(self):
        result = parse_gpu("Adreno 650 @ 587 MHz")
        assert result.get("gpu_clock") == 587

    def test_empty(self):
        assert parse_gpu("") == {}


class TestParseProcess:
    def test_nm_value(self):
        result = parse_process("7 nm")
        assert result.get("process_nm") == 7
        assert result.get("process_name") == "7nm"

    def test_empty(self):
        assert parse_process("") == {}


class TestParseMemory:
    def test_type_and_clock(self):
        result = parse_memory("LPDDR5 3200 MHz")
        assert result.get("memory_type") == "LPDDR5"
        assert result.get("memory_clock") == 3200

    def test_bus_width(self):
        result = parse_memory("64-bit")
        assert result.get("memory_bus") == 64


class TestParseModem:
    def test_modem_name(self):
        result = parse_modem("Snapdragon X55 5G")
        assert "Snapdragon" in result.get("modem", "")


class TestParseConnectivity:
    def test_wifi_only(self):
        result = parse_connectivity("Wi-Fi 6")
        assert result.get("wifi") == "Wi-Fi 6"

    def test_bluetooth(self):
        result = parse_connectivity("Bluetooth 5.0")
        assert result.get("bluetooth") == "5.0"


class TestParseVideo:
    def test_4k(self):
        result = parse_video("4K @ 60fps")
        assert result.get("video_decode")


class TestParseDisplay:
    def test_resolution(self):
        result = parse_display("3840×2160")
        assert "3840" in result.get("display_max", "")


class TestParseCamera:
    def test_megapixels(self):
        result = parse_camera("108 MP")
        assert "108" in result.get("camera_max", "")


class TestParseYear:
    def test_valid_year(self):
        assert parse_year("2020") == {"year": 2020}

    def test_out_of_range(self):
        assert parse_year("1999") == {}

    def test_empty(self):
        assert parse_year("") == {}


class TestDetectColumns:
    def test_cpu_column(self):
        cells = [MockCell("Model"), MockCell("CPU"), MockCell("GPU")]
        cols = detect_columns(cells)
        assert len(cols) == 3
        assert cols[0][0] == "model"
        assert cols[1][0] == "cpu"
        assert cols[2][0] == "gpu"

    def test_empty_header(self):
        cells = [MockCell("")]
        cols = detect_columns(cells)
        assert cols[0][0] is None


class TestParseCell:
    def test_empty_cell(self):
        assert parse_cell("", "cpu", None) == {}

    def test_na_value(self):
        assert parse_cell("N/A", "cpu", None) == {}

    def test_dash_value(self):
        assert parse_cell("—", "cpu", None) == {}
