"""Unit tests for soc-db shared utilities."""

from soc_db.common import (
    clean,
    enrich_one,
    extract_freq,
    extract_int,
    extract_model,
    extract_process,
    slug,
)


class TestClean:
    def test_strip_html(self):
        assert clean("<b>Snapdragon</b> 865") == "Snapdragon 865"

    def test_strip_brackets(self):
        assert clean("Snapdragon [1] 865") == "Snapdragon 865"

    def test_strip_editorial(self):
        result = clean("Snapdragon 855 (now managed and sold to X)")
        assert "now" not in (result or "")

    def test_none_input(self):
        assert clean(None) is None

    def test_empty_input(self):
        assert clean("") is None


class TestSlug:
    def test_basic(self):
        assert slug("Snapdragon 865", "SM8250") == "snapdragon_865_sm8250"

    def test_no_model(self):
        slug_result = slug("Apple A14 Bionic")
        assert "apple" in slug_result
        assert "a14" in slug_result

    def test_skip_words(self):
        slug_result = slug("Snapdragon 8 Gen 2 with Kryo Cores")
        assert "with" not in slug_result
        assert "kryo" not in slug_result


class TestExtractInt:
    def test_basic(self):
        assert extract_int("123") == 123

    def test_with_text(self):
        assert extract_int("7nm") == 7

    def test_none(self):
        assert extract_int("") is None
        assert extract_int(None) is None


class TestExtractFreq:
    def test_mhz(self):
        result = extract_freq("3200 MHz")
        assert result and "3200" in result

    def test_ghz(self):
        result = extract_freq("3.0 GHz")
        assert result and "3.0" in result

    def test_none(self):
        assert extract_freq("") is None


class TestExtractProcess:
    def test_nm_value(self):
        assert extract_process("7nm") == "7nm"

    def test_none(self):
        assert extract_process("") is None


class TestExtractModel:
    def test_qualcomm_sm(self):
        assert extract_model("SM8250") == "SM8250"

    def test_mediatek_mt(self):
        assert extract_model("MT6983") == "MT6983"

    def test_exynos(self):
        assert extract_model("Exynos 2200") == "EXYNOS 2200"

    def test_none(self):
        assert extract_model("") is None


class TestEnrichOne:
    def test_basic_fill(self):
        chip = {"id": "sm8250", "name": "Snapdragon 865", "vendor": "Qualcomm"}
        result = enrich_one(chip)
        assert result.get("completeness", 0) > 0
        assert result.get("updated") is not None

    def test_minimal(self):
        chip = {"id": "x", "name": "X", "vendor": "Unknown"}
        result = enrich_one(chip)
        assert isinstance(result.get("completeness"), (int, float))
