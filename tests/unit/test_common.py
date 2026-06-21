"""Unit tests for soc-db shared utilities."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from soc_db.common import (
    _has,
    _match_existing,
    clean,
    enrich_all,
    enrich_one,
    extract_freq,
    extract_int,
    extract_model,
    extract_process,
    fetch,
    merge_chips,
    slug,
    write_vendor_file,
)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


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

    def test_already_clean(self):
        assert clean("Snapdragon 865") == "Snapdragon 865"

    def test_multiple_brackets(self):
        assert clean("[1][2] Snapdragon [3]") == "Snapdragon"


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

    def test_only_name(self):
        result = slug("Exynos 2200")
        assert result == "exynos_2200"

    def test_special_chars(self):
        result = slug("SD 8 Gen 1", "SM8450")
        assert result == "sd_8_gen_1_sm8450"

    def test_empty_name(self):
        assert slug("") == "chip"


class TestExtractInt:
    def test_basic(self):
        assert extract_int("123") == 123

    def test_with_text(self):
        assert extract_int("7nm") == 7

    def test_none(self):
        assert extract_int("") is None
        assert extract_int(None) is None

    def test_trailing_text(self):
        assert extract_int("123 MHz") == 123

    def test_negative(self):
        assert extract_int("-5") == 5

    def test_float(self):
        assert extract_int("1.5") == 1


class TestExtractFreq:
    def test_mhz(self):
        result = extract_freq("3200 MHz")
        assert result and "3200" in result

    def test_ghz(self):
        result = extract_freq("3.0 GHz")
        assert result and "3.0" in result

    def test_none(self):
        assert extract_freq("") is None

    def test_multiple_freqs(self):
        result = extract_freq("1.8 GHz / 2.0 GHz")
        assert result

    def test_mhz_no_space(self):
        result = extract_freq("2400MHz")
        assert result and "2400" in result

    def test_up_to_format(self):
        result = extract_freq("up to 2.84 GHz")
        assert result and "2.84" in result

    def test_no_match(self):
        result = extract_freq("no numbers here")
        assert result is None


class TestExtractProcess:
    def test_nm_value(self):
        assert extract_process("7nm") == "7nm"

    def test_none(self):
        assert extract_process("") is None

    def test_with_nm_uppercase(self):
        assert extract_process("28NM") == "28NM"


class TestExtractModel:
    def test_qualcomm_sm(self):
        assert extract_model("SM8250") == "SM8250"

    def test_mediatek_mt(self):
        assert extract_model("MT6983") == "MT6983"

    def test_exynos(self):
        assert extract_model("Exynos 2200") == "EXYNOS 2200"

    def test_none(self):
        assert extract_model("") is None

    def test_kirin(self):
        assert extract_model("Kirin 9000") == "KIRIN 9000"

    def test_apple_not_matched(self):
        assert extract_model("Apple A16") is None


class TestHas:
    def test_has_field(self):
        assert _has({"name": "test"}, "name")

    def test_missing_field(self):
        assert not _has({}, "name")

    def test_none_value(self):
        assert not _has({"name": None}, "name")

    def test_empty_string(self):
        assert not _has({"name": ""}, "name")

    def test_zero_value(self):
        assert not _has({"count": 0}, "count")


class TestMergeChips:
    def test_merge_basic(self):
        a = {"id": "x", "name": "A", "year": 2020}
        b = {"cores": 8}
        result = merge_chips(a, b)
        assert result == {"id": "x", "name": "A", "year": 2020, "cores": 8}

    def test_merge_override(self):
        a = {"id": "x", "name": "A", "year": 2020}
        b = {"name": "B"}
        result = merge_chips(a, b)
        assert result["name"] == "B"

    def test_merge_skip_empty(self):
        a = {"id": "x", "name": "A"}
        b = {"name": "", "year": 0}
        result = merge_chips(a, b)
        assert result["name"] == "A"

    def test_empty_merge(self):
        assert merge_chips({}, {}) == {}

    def test_merge_does_not_mutate(self):
        a = {"id": "x"}
        b = {"year": 2020}
        merge_chips(a, b)
        assert "year" not in a


class TestMatchExisting:
    def test_by_id(self):
        existing = {"a": {"id": "a", "name": "A"}, "b": {"id": "b", "name": "B"}}
        assert _match_existing({"id": "a"}, existing) == "a"

    def test_by_model(self):
        existing = {"a": {"id": "a", "model": "SM8250"}}
        assert _match_existing({"id": "x", "model": "SM8250"}, existing) == "a"

    def test_by_name(self):
        existing = {"a": {"id": "a", "name": "Snapdragon 865"}}
        assert _match_existing({"id": "x", "name": "Snapdragon 865"}, existing) == "a"

    def test_no_match(self):
        existing = {"a": {"id": "a", "name": "A"}}
        assert _match_existing({"id": "x", "name": "B"}, existing) is None

    def test_empty_existing(self):
        assert _match_existing({"id": "x"}, {}) is None


class TestFetch:
    def test_cached(self):
        url = "https://example.com/test"
        with (
            patch("soc_db.common.CACHE_DIR") as mock_cache,
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.read_text", return_value="cached data"),
            patch("pathlib.Path.stat") as mock_stat,
        ):
            mock_cache.__truediv__.return_value = Path("/tmp/test-cache")
            mock_stat.return_value.st_mtime = 9999999999
            result = fetch(url, ttl=86400)
            assert result == "cached data"

    def test_fetch_from_network(self):
        url = "http://localhost:0/test"
        with patch("soc_db.common.CACHE_DIR") as mock_cache:
            mock_cache.__truediv__.return_value = Path("/tmp/test-cache")
            with patch("pathlib.Path.exists", return_value=False), patch("soc_db.common.urlopen") as mock_urlopen:
                mock_resp = mock_urlopen.return_value.__enter__.return_value
                mock_resp.read.return_value = b"network data"
                mock_resp.status = 200
                result = fetch(url, ttl=86400)
                assert result == "network data"


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

    def test_qualcomm_sm8550(self):
        chip = {"id": "sm8550", "name": "Snapdragon 8 Gen 2", "vendor": "Qualcomm", "model": "SM8550", "cores": 8, "year": 2023}
        result = enrich_one(chip)
        assert result.get("gpu") == "Adreno 740"
        assert result.get("process_nm") == 4
        assert result.get("memory_type") == "LPDDR5X"

    def test_qualcomm_sm8650(self):
        chip = {"id": "sm8650", "name": "Snapdragon 8 Gen 3", "vendor": "Qualcomm", "model": "SM8650", "year": 2024}
        result = enrich_one(chip)
        assert result.get("gpu") == "Adreno 750"

    def test_qualcomm_sm8250(self):
        chip = {"id": "sm8250", "name": "Snapdragon 865", "vendor": "Qualcomm", "model": "SM8250", "year": 2020}
        result = enrich_one(chip)
        assert result.get("gpu") == "Adreno 650"

    def test_mediatek_dimensity(self):
        chip = {"id": "mt6983", "name": "Dimensity 9000", "vendor": "MediaTek", "model": "MT6983", "year": 2022}
        result = enrich_one(chip)
        assert result.get("npu") == "MediaTek APU"

    def test_mediatek_helio(self):
        chip = {"id": "mt6785", "name": "Helio G90", "vendor": "MediaTek", "model": "MT6785"}
        result = enrich_one(chip)
        assert result.get("year") is not None

    def test_exynos_2200(self):
        chip = {"id": "exynos2200", "name": "Exynos 2200", "vendor": "Samsung", "model": "EXYNOS 2200", "year": 2022}
        result = enrich_one(chip)
        assert result.get("npu") is not None

    def test_exynos_auto_year(self):
        chip = {"id": "exynos990", "name": "Exynos 990", "vendor": "Samsung", "model": "EXYNOS 990"}
        result = enrich_one(chip)
        assert result.get("year") is not None

    def test_apple_m1(self):
        chip = {"id": "apple_m1", "name": "Apple M1", "vendor": "Apple", "year": 2020}
        result = enrich_one(chip)
        assert result.get("architecture") is not None
        assert result.get("memory_type") is not None

    def test_kirin_9000(self):
        chip = {"id": "kirin9000", "name": "Kirin 9000", "vendor": "HiSilicon", "model": "KIRIN 9000", "year": 2020}
        result = enrich_one(chip)
        assert result.get("npu") is not None

    def test_kirin_auto_year(self):
        chip = {"id": "kirin990", "name": "Kirin 990", "vendor": "HiSilicon", "model": "KIRIN 990"}
        result = enrich_one(chip)
        assert result.get("year") == 2019

    def test_intel_atom(self):
        chip = {"id": "atom_z3740", "name": "Atom Z3740", "vendor": "Intel Atom", "model": "Z3740", "year": 2014}
        result = enrich_one(chip)
        assert result is not None

    def test_nvidia_tegra(self):
        chip = {"id": "tegra_x1", "name": "Tegra X1", "vendor": "Nvidia", "year": 2015}
        result = enrich_one(chip)
        assert result.get("gpu") == "Nvidia GPU"

    def test_allwinner(self):
        chip = {"id": "aw_h3", "name": "H3", "vendor": "Allwinner", "year": 2014}
        result = enrich_one(chip)
        assert result is not None

    def test_rockchip(self):
        chip = {"id": "rk3588", "name": "RK3588", "vendor": "Rockchip", "year": 2022}
        result = enrich_one(chip)
        assert result is not None

    def test_npu_qualcomm_sm(self):
        chip = {"id": "sm8550", "name": "Snapdragon 8 Gen 2", "vendor": "Qualcomm", "model": "SM8550", "year": 2023}
        result = enrich_one(chip)
        assert result.get("npu") is not None

    def test_memory_bus_lpddr5(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "model": "SM8550", "memory_type": "LPDDR5", "year": 2023}
        result = enrich_one(chip)
        assert result.get("memory_bus") == 64

    def test_memory_bus_lpddr3(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "model": "SM8250", "memory_type": "LPDDR3", "year": 2020}
        result = enrich_one(chip)
        assert result.get("memory_bus") == 32

    def test_wifi_by_year_2023(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "year": 2023}
        result = enrich_one(chip)
        assert result.get("wifi") == "Wi-Fi 7"

    def test_wifi_by_year_2019(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "year": 2019}
        result = enrich_one(chip)
        assert result.get("wifi") == "Wi-Fi 6"

    def test_storage_by_year(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "year": 2021}
        result = enrich_one(chip)
        assert result.get("storage_type") is not None

    def test_bluetooth_by_year(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "year": 2023}
        result = enrich_one(chip)
        assert result.get("bluetooth") == "5.3"

    def test_samsung_npu(self):
        chip = {"id": "exynos2200", "name": "Exynos 2200", "vendor": "Samsung", "model": "EXYNOS 2200", "year": 2022}
        result = enrich_one(chip)
        assert result.get("npu") == "Samsung NPU"

    def test_mediatek_mt8000_npu(self):
        chip = {"id": "mt6983", "name": "Dimensity 9000", "vendor": "MediaTek", "model": "MT6983", "year": 2022}
        result = enrich_one(chip)
        assert result.get("npu") == "MediaTek APU"

    def test_model_from_name(self):
        chip = {"id": "x", "name": "SM8550", "vendor": "Qualcomm"}
        result = enrich_one(chip)
        assert result.get("model") == "SM8550"

    def test_slug_as_model_fallback(self):
        chip = {"id": "my_soc", "name": "Custom SoC", "vendor": "Unknown"}
        result = enrich_one(chip)
        assert result.get("model") == "my_soc"

    def test_clean_name_editorial(self):
        chip = {"id": "x", "name": "Snapdragon 8 Gen 1 (now available)", "vendor": "Qualcomm"}
        result = enrich_one(chip)
        assert "now" not in result.get("name", "")

    def test_year_inference_sm8xxx(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "model": "SM8450"}
        result = enrich_one(chip)
        assert result.get("year") == 2022

    def test_year_inference_sdm(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "model": "SDM865"}
        result = enrich_one(chip)
        assert result.get("year") is not None

    def test_year_inference_msm(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "model": "MSM8998"}
        result = enrich_one(chip)
        assert result.get("year") is not None

    def test_year_inference_dimensity(self):
        chip = {"id": "x", "name": "Dimensity 9200", "vendor": "MediaTek", "model": "Dimensity 9200"}
        result = enrich_one(chip)
        assert result.get("year") is not None

    def test_process_nm_from_vendor_knowledge(self):
        chip = {"id": "sm8550", "name": "Snapdragon 8 Gen 2", "vendor": "Qualcomm", "model": "SM8550", "year": 2023}
        result = enrich_one(chip)
        assert result.get("process_nm") == 4

    def test_aliases(self):
        chip = {"id": "sm8550_kalama", "name": "Snapdragon 8 Gen 2", "vendor": "Qualcomm", "model": "SM8550"}
        result = enrich_one(chip)
        assert "aliases" in result

    def test_modem_qualcomm_sm8650(self):
        chip = {"id": "sm8650", "name": "Snapdragon 8 Gen 3", "vendor": "Qualcomm", "model": "SM8650", "year": 2024}
        result = enrich_one(chip)
        assert result.get("modem") is not None

    def test_modem_qualcomm_old(self):
        chip = {"id": "sm8250", "name": "Snapdragon 865", "vendor": "Qualcomm", "model": "SM8250", "year": 2020}
        result = enrich_one(chip)
        assert result.get("modem") is not None

    def test_process_mtk_helio(self):
        chip = {"id": "mt6785", "name": "Helio G90", "vendor": "MediaTek", "model": "MT6785", "year": 2019}
        result = enrich_one(chip)
        assert result.get("process_nm") is not None

    def test_process_by_year(self):
        chip = {"id": "x", "name": "Test SoC", "vendor": "Unknown", "year": 2024}
        result = enrich_one(chip)
        assert result.get("process_nm") == 3

    def test_process_by_year_2015(self):
        chip = {"id": "x", "name": "Old SoC", "vendor": "Unknown", "year": 2015}
        result = enrich_one(chip)
        assert result.get("process_nm") == 14

    def test_gpu_by_vendor_nvidia(self):
        chip = {"id": "tegra_x1", "name": "Tegra X1", "vendor": "Nvidia", "year": 2015}
        result = enrich_one(chip)
        assert result.get("gpu") == "Nvidia GPU"

    def test_memory_clock_from_type(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "memory_type": "LPDDR5X", "year": 2023}
        result = enrich_one(chip)
        assert result.get("memory_clock") == 4266

    def test_apple_modem(self):
        chip = {"id": "apple_a16", "name": "Apple A16 Bionic", "vendor": "Apple", "year": 2022}
        result = enrich_one(chip)
        assert result.get("modem") is not None

    def test_year_inference_kirin_9000(self):
        chip = {"id": "kirin9000", "name": "Kirin 9000", "vendor": "HiSilicon", "model": "KIRIN 9000"}
        result = enrich_one(chip)
        assert result.get("year") == 2020

    def test_year_inference_kirin_810(self):
        chip = {"id": "kirin810", "name": "Kirin 810", "vendor": "HiSilicon", "model": "KIRIN 810"}
        result = enrich_one(chip)
        assert result.get("year") is not None

    def test_year_inference_exynos_2400(self):
        chip = {"id": "exynos2400", "name": "Exynos 2400", "vendor": "Samsung", "model": "EXYNOS 2400"}
        result = enrich_one(chip)
        assert result.get("year") == 2024

    def test_exynos_w92(self):
        chip = {"id": "exynos_w92", "name": "Exynos W92", "vendor": "Samsung", "model": "EXYNOS W92"}
        result = enrich_one(chip)
        assert result.get("year") == 2020

    def test_exynos_auto_v9(self):
        chip = {"id": "exynos_auto_v9", "name": "Exynos Auto V9", "vendor": "Samsung", "model": "EXYNOS AUTO V9"}
        result = enrich_one(chip)
        assert result.get("year") == 2020

    def test_empty_model_name(self):
        chip = {"id": "", "name": "Cariboo", "vendor": "Unknown"}
        result = enrich_one(chip)
        assert result.get("year") is None

    def test_intel_atom_bt(self):
        chip = {"id": "atom_z3740", "name": "Atom Z3740", "vendor": "Intel Atom", "year": 2014}
        result = enrich_one(chip)
        assert result.get("bluetooth") is not None

    def test_mediatek_mt9900_year(self):
        chip = {"id": "mt9900", "name": "Dimensity 9400", "vendor": "MediaTek", "model": "MT9900"}
        result = enrich_one(chip)
        assert result.get("year") is not None

    def test_year_inference_sm7xxx(self):
        chip = {"id": "sm7250", "name": "Snapdragon 765", "vendor": "Qualcomm", "model": "SM7250"}
        result = enrich_one(chip)
        assert result.get("year") is not None

    def test_year_inference_sm6xxx(self):
        chip = {"id": "sm6350", "name": "Snapdragon 690", "vendor": "Qualcomm", "model": "SM6350"}
        result = enrich_one(chip)
        assert result.get("year") is not None

    def test_year_inference_sm4xxx(self):
        chip = {"id": "sm4350", "name": "Snapdragon 480", "vendor": "Qualcomm", "model": "SM4350"}
        result = enrich_one(chip)
        assert result.get("year") is not None

    def test_year_inference_sm2xxx(self):
        chip = {"id": "sm2250", "name": "Snapdragon 662", "vendor": "Qualcomm", "model": "SM2250"}
        result = enrich_one(chip)
        assert result.get("year") is not None

    def test_year_inference_msm8994(self):
        chip = {"id": "msm8994", "name": "Snapdragon 810", "vendor": "Qualcomm", "model": "MSM8994"}
        result = enrich_one(chip)
        assert result.get("year") is not None

    def test_year_inference_msm8909(self):
        chip = {"id": "msm8909", "name": "Snapdragon 210", "vendor": "Qualcomm", "model": "MSM8909"}
        result = enrich_one(chip)
        assert result.get("year") is not None

    def test_year_inference_apq8074(self):
        chip = {"id": "apq8074", "name": "Snapdragon 800", "vendor": "Qualcomm", "model": "APQ8074"}
        result = enrich_one(chip)
        assert result.get("year") is not None

    def test_year_inference_ti_omap(self):
        chip = {"id": "omap4460", "name": "OMAP 4460", "vendor": "TI OMAP", "model": "OMAP 4460"}
        result = enrich_one(chip)
        assert result is not None

    def test_year_inference_broadcom(self):
        chip = {"id": "bcm2711", "name": "BCM2711", "vendor": "Broadcom", "model": "BCM2711"}
        result = enrich_one(chip)
        assert result is not None

    def test_year_inference_ingenic(self):
        chip = {"id": "jz4780", "name": "JZ4780", "vendor": "Ingenic", "model": "JZ4780"}
        result = enrich_one(chip)
        assert result is not None

    def test_year_inference_rockchip_rk(self):
        chip = {"id": "rk3288", "name": "RK3288", "vendor": "Rockchip", "model": "RK3288"}
        result = enrich_one(chip)
        assert result.get("year") is not None

    def test_year_inference_allwinner(self):
        chip = {"id": "aw_h3", "name": "H3", "vendor": "Allwinner", "model": "A83T"}
        result = enrich_one(chip)
        assert result.get("year") is not None

    def test_year_inference_amlogic(self):
        chip = {"id": "aml_s905", "name": "S905", "vendor": "Amlogic", "model": "S905"}
        result = enrich_one(chip)
        assert result.get("year") is not None

    def test_year_inference_nxp_imx(self):
        chip = {"id": "imx6", "name": "i.MX 6", "vendor": "NXP i.MX", "model": "i.MX 6"}
        result = enrich_one(chip)
        assert result.get("completeness") is not None

    def test_year_inference_xilinx(self):
        chip = {"id": "zynq", "name": "Zynq", "vendor": "Xilinx", "model": "Zynq"}
        result = enrich_one(chip)
        assert result.get("completeness") is not None

    def test_year_out_of_range_set_to_none(self):
        chip = {"id": "x", "name": "X", "vendor": "V", "year": 2030}
        result = enrich_one(chip)
        assert result.get("year") is None

    def test_completeness_score(self):
        full = {"id": "x", "name": "X", "vendor": "V", "model": "M", "year": 2020, "cores": 8, "gpu": "G", "architecture": "ARM"}
        result = enrich_one(full)
        assert result.get("completeness", 0) > 0.4

    def test_gpu_by_vendor_amd(self):
        chip = {"id": "amd_ryzen", "name": "Ryzen 7", "vendor": "Qualcomm", "year": 2023}
        result = enrich_one(chip)
        assert "gpu" in result

    def test_gpu_rockchip_mali(self):
        chip = {"id": "rk3588", "name": "RK3588", "vendor": "Rockchip", "year": 2022}
        result = enrich_one(chip)
        assert result.get("gpu") is not None

    def test_gpu_intel_atom_old(self):
        chip = {"id": "atom_z3740", "name": "Atom Z3740", "vendor": "Intel Atom", "year": 2013}
        result = enrich_one(chip)
        assert result.get("gpu") is not None

    def test_gpu_intel_atom_new(self):
        chip = {"id": "atom_x7", "name": "Atom x7-Z8700", "vendor": "Intel Atom", "year": 2018}
        result = enrich_one(chip)
        assert result.get("gpu") is not None

    def test_npu_hisilicon_kirin(self):
        chip = {"id": "kirin990", "name": "Kirin 990", "vendor": "HiSilicon", "model": "KIRIN 990", "year": 2019}
        result = enrich_one(chip)
        assert result.get("npu") == "HiSilicon NPU"

    def test_modem_qualcomm_old_sm8xxx(self):
        chip = {"id": "sm8250", "name": "Snapdragon 865", "vendor": "Qualcomm", "model": "SM8250", "year": 2020}
        result = enrich_one(chip)
        assert result.get("modem") is not None

    def test_modem_qualcomm_very_old(self):
        chip = {"id": "msm8909", "name": "Snapdragon 210", "vendor": "Qualcomm", "model": "MSM8909", "year": 2015}
        result = enrich_one(chip)
        assert result.get("modem") is not None

    def test_memory_clock_lpddr4x(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "memory_type": "LPDDR4X", "year": 2021}
        result = enrich_one(chip)
        assert result.get("memory_clock") == 2133

    def test_aliases_sm8550(self):
        chip = {"id": "sm8550", "name": "Snapdragon 8 Gen 2", "vendor": "Qualcomm", "model": "SM8550"}
        result = enrich_one(chip)
        aliases = result.get("aliases", [])
        assert "Kalama" in aliases


class TestEnrichAll:
    def test_multiple_chips(self):
        chips = [
            {"id": "a", "name": "A", "vendor": "Qualcomm"},
            {"id": "b", "name": "B", "vendor": "MediaTek"},
        ]
        results = enrich_all(chips)
        assert len(results) == 2
        assert all(c.get("completeness") is not None for c in results)

    def test_empty(self):
        assert enrich_all([]) == []


class TestYearInference:
    @pytest.mark.parametrize(
        "model,vendor,expected,note",
        [
            ("MT9999", "MediaTek", 2025, "MT>=9900"),
            ("MT9899", "MediaTek", 2024, "MT 9800-9899"),
            ("MT9200", "MediaTek", 2023, "MT 9200-9799"),
            ("MT8700", "MediaTek", 2022, "MT 8700-9199"),
            ("MT8300", "MediaTek", 2021, "MT 8300-8699"),
            ("MT8000", "MediaTek", 2020, "MT 8000-8299"),
            ("MT7900", "MediaTek", 2019, "MT 7900-7999"),
            ("MT7500", "MediaTek", 2018, "MT 7500-7899"),
            ("MT7000", "MediaTek", 2017, "MT 7000-7499"),
            ("MT6500", "MediaTek", 2016, "MT 6500-6999"),
            ("MT6000", "MediaTek", 2015, "MT 6000-6499"),
            ("MT5000", "MediaTek", 2014, "MT 5000-5999"),
            ("MT4000", "MediaTek", 2013, "MT<5000"),
            ("DIMENSITY 9400", "MediaTek", 2025, "Dim >=9400"),
            ("DIMENSITY 9300", "MediaTek", 2024, "Dim >=9200"),
            ("DIMENSITY 9000", "MediaTek", 2023, "Dim >=9000"),
            ("DIMENSITY 8400", "MediaTek", 2024, "Dim >=8300"),
            ("DIMENSITY 8200", "MediaTek", 2023, "Dim >=8200"),
            ("DIMENSITY 8100", "MediaTek", 2022, "Dim >=8000"),
            ("DIMENSITY 7200", "MediaTek", 2023, "Dim >=7200"),
            ("DIMENSITY 7000", "MediaTek", 2022, "Dim >=6000"),
            ("DIMENSITY 1200", "MediaTek", 2021, "Dim >=1100"),
            ("DIMENSITY 1000", "MediaTek", 2020, "Dim >=1000"),
            ("DIMENSITY 900", "MediaTek", 2019, "Dim >=900"),
            ("DIMENSITY 800", "MediaTek", 2018, "Dim >=800"),
            ("DIMENSITY 700", "MediaTek", 2017, "Dim >=700"),
            ("DIMENSITY 600", "MediaTek", 2016, "Dim >=600"),
            ("DIMENSITY 500", "MediaTek", 2015, "Dim >=500"),
            ("DIMENSITY 400", "MediaTek", 2014, "Dim <500"),
            ("SM8750", "Qualcomm", 2025, "SM>=8750"),
            ("SM8650", "Qualcomm", 2024, "SM 8650-8749"),
            ("SM8550", "Qualcomm", 2023, "SM 8550-8649"),
            ("SM8450", "Qualcomm", 2022, "SM 8450-8549"),
            ("SM8350", "Qualcomm", 2021, "SM 8350-8449"),
            ("SM8250", "Qualcomm", 2020, "SM 8250-8349"),
            ("SM8150", "Qualcomm", 2019, "SM 8150-8249"),
            ("SM8000", "Qualcomm", 2018, "SM 8000-8149"),
            ("SM7000", "Qualcomm", 2017, "SM 7000-7999"),
            ("SM6000", "Qualcomm", 2016, "SM 6000-6999"),
            ("SM5000", "Qualcomm", 2015, "SM 5000-5999"),
            ("SM4000", "Qualcomm", 2014, "SM 4000-4999"),
            ("SM3000", "Qualcomm", 2013, "SM 3000-3999"),
            ("SM2000", "Qualcomm", 2012, "SM 2000-2999"),
            ("SM1000", "Qualcomm", 2011, "SM<2000"),
            ("KIRIN 930", "HiSilicon", 2015, "Kirin 930-949"),
            ("KIRIN 9010", "HiSilicon", 2024, "Kirin>=9010"),
            ("KIRIN 9000", "HiSilicon", 2020, "Kirin 9000-9009"),
            ("KIRIN 8000", "HiSilicon", 2024, "Kirin 8000-8999"),
            ("KIRIN 990", "HiSilicon", 2019, "Kirin 990-989"),
            ("KIRIN 980", "HiSilicon", 2018, "Kirin 980-989"),
            ("KIRIN 970", "HiSilicon", 2017, "Kirin 970-979"),
            ("KIRIN 960", "HiSilicon", 2016, "Kirin 960-969"),
            ("KIRIN 950", "HiSilicon", 2015, "Kirin 950-959"),
            ("KIRIN 920", "HiSilicon", 2014, "Kirin 920-929"),
            ("KIRIN 800", "HiSilicon", 2018, "Kirin 800-919"),
            ("KIRIN 700", "HiSilicon", 2018, "Kirin 700-799"),
            ("KIRIN 600", "HiSilicon", 2015, "Kirin 600-699"),
            ("KIRIN 300", "HiSilicon", 2013, "Kirin<600"),
            ("EXYNOS 2500", "Samsung", 2025, "Exynos>=2500"),
            ("EXYNOS 2400", "Samsung", 2024, "Exynos 2400-2499"),
            ("EXYNOS 2200", "Samsung", 2022, "Exynos 2200-2399"),
            ("EXYNOS 2100", "Samsung", 2021, "Exynos 2100-2199"),
            ("EXYNOS 2000", "Samsung", 2020, "Exynos 2000-2099"),
            ("EXYNOS 1580", "Samsung", 2025, "Exynos 1580-1999"),
            ("EXYNOS 1480", "Samsung", 2024, "Exynos 1480-1579"),
            ("EXYNOS 1380", "Samsung", 2023, "Exynos 1380-1479"),
            ("EXYNOS 1280", "Samsung", 2022, "Exynos 1280-1379"),
            ("EXYNOS 1080", "Samsung", 2020, "Exynos 1080-1279"),
            ("EXYNOS 990", "Samsung", 2020, "Exynos 3-digit >=990"),
            ("EXYNOS 850", "Samsung", 2020, "Exynos 3-digit >=850"),
            ("EXYNOS 440", "Samsung", 2015, "Exynos 3-digit <850"),
        ],
    )
    def test_year_inference(self, model, vendor, expected, note):
        chip = {"id": "x", "name": "X", "vendor": vendor, "model": model}
        result = enrich_one(chip)
        assert result.get("year") == expected, f"{note}: expected {expected}, got {result.get('year')}"

    def test_snapdragon_x_elite(self):
        chip = {"id": "x", "name": "Snapdragon X Elite", "vendor": "Qualcomm", "model": "SNAPDRAGON X ELITE"}
        result = enrich_one(chip)
        assert result.get("year") == 2024

    def test_snapdragon_x_plus(self):
        chip = {"id": "x", "name": "Snapdragon X Plus", "vendor": "Qualcomm", "model": "SNAPDRAGON X PLUS"}
        result = enrich_one(chip)
        assert result.get("year") == 2024

    def test_snapdragon_x2(self):
        chip = {"id": "x", "name": "Snapdragon X2", "vendor": "Qualcomm", "model": "SNAPDRAGON X 2"}
        result = enrich_one(chip)
        assert result.get("year") == 2025

    def test_snapdragon_gen(self):
        chip = {"id": "x", "name": "Snapdragon 8 Gen 1", "vendor": "Qualcomm", "model": "SNAPDRAGON 8 GEN 1"}
        result = enrich_one(chip)
        assert result.get("year") == 2022

    def test_snapdragon_7_gen(self):
        chip = {"id": "x", "name": "Snapdragon 7 Gen 1", "vendor": "Qualcomm", "model": "SNAPDRAGON 7 GEN 1"}
        result = enrich_one(chip)
        assert result.get("year") == 2021

    def test_rk_year(self):
        chip = {"id": "rk3288", "name": "RK3288", "vendor": "Rockchip", "model": "RK3288"}
        result = enrich_one(chip)
        assert result.get("year") == 2008 + (3288 - 2000) // 200

    def test_allwinner_a80_year(self):
        chip = {"id": "aw_h3", "name": "A80", "vendor": "Allwinner", "model": "A80"}
        result = enrich_one(chip)
        assert result.get("year") == 2025

    def test_allwinner_h33_year(self):
        chip = {"id": "aw_h3", "name": "H33", "vendor": "Allwinner", "model": "H33"}
        result = enrich_one(chip)
        assert result.get("year") is not None

    def test_allwinner_h700_year(self):
        chip = {"id": "aw_h700", "name": "H700", "vendor": "Allwinner", "model": "H700"}
        result = enrich_one(chip)
        assert result.get("year") is not None

    def test_allwinner_h600_year(self):
        chip = {"id": "aw_h600", "name": "H600", "vendor": "Allwinner", "model": "H600"}
        result = enrich_one(chip)
        assert result.get("year") is not None

    def test_allwinner_h500_year(self):
        chip = {"id": "aw_h500", "name": "H500", "vendor": "Allwinner", "model": "H500"}
        result = enrich_one(chip)
        assert result.get("year") is not None

    def test_allwinner_h300_year(self):
        chip = {"id": "aw_h300", "name": "H300", "vendor": "Allwinner", "model": "H300"}
        result = enrich_one(chip)
        assert result.get("year") is not None

    def test_allwinner_f100_year(self):
        chip = {"id": "aw_f100", "name": "F100", "vendor": "Allwinner", "model": "F100"}
        result = enrich_one(chip)
        assert result.get("year") is not None

    def test_allwinner_a17_year(self):
        chip = {"id": "aw_a17", "name": "A17", "vendor": "Allwinner", "model": "A17"}
        result = enrich_one(chip)
        assert result.get("year") == 2024

    def test_allwinner_a16_year(self):
        chip = {"id": "aw_a16", "name": "A16", "vendor": "Allwinner", "model": "A16"}
        result = enrich_one(chip)
        assert result.get("year") == 2023

    def test_allwinner_a15_year(self):
        chip = {"id": "aw_a15", "name": "A15", "vendor": "Allwinner", "model": "A15"}
        result = enrich_one(chip)
        assert result.get("year") == 2022

    def test_allwinner_a14_year(self):
        chip = {"id": "aw_a14", "name": "A14", "vendor": "Allwinner", "model": "A14"}
        result = enrich_one(chip)
        assert result.get("year") == 2020

    def test_allwinner_a12_year(self):
        chip = {"id": "aw_a12", "name": "A12", "vendor": "Allwinner", "model": "A12"}
        result = enrich_one(chip)
        assert result.get("year") == 2018

    def test_allwinner_a11_year(self):
        chip = {"id": "aw_a11", "name": "A11", "vendor": "Allwinner", "model": "A11"}
        result = enrich_one(chip)
        assert result.get("year") == 2017

    def test_allwinner_a9_year(self):
        chip = {"id": "aw_a9", "name": "A9", "vendor": "Allwinner", "model": "A9"}
        result = enrich_one(chip)
        assert result.get("year") == 2015

    def test_allwinner_a8_year(self):
        chip = {"id": "aw_a8", "name": "A8", "vendor": "Allwinner", "model": "A8"}
        result = enrich_one(chip)
        assert result.get("year") == 2014

    def test_allwinner_a7_year(self):
        chip = {"id": "aw_a7", "name": "A7", "vendor": "Allwinner", "model": "A7"}
        result = enrich_one(chip)
        assert result.get("year") == 2013

    def test_allwinner_a5_year(self):
        chip = {"id": "aw_a5", "name": "A5", "vendor": "Allwinner", "model": "A5"}
        result = enrich_one(chip)
        assert result.get("year") == 2011

    def test_allwinner_m4_year(self):
        chip = {"id": "aw_m4", "name": "M4", "vendor": "Allwinner", "model": "M4"}
        result = enrich_one(chip)
        assert result.get("year") == 2025

    def test_allwinner_m3_year(self):
        chip = {"id": "aw_m3", "name": "M3", "vendor": "Allwinner", "model": "M3"}
        result = enrich_one(chip)
        assert result.get("year") == 2023

    def test_allwinner_m2_year(self):
        chip = {"id": "aw_m2", "name": "M2", "vendor": "Allwinner", "model": "M2"}
        result = enrich_one(chip)
        assert result.get("year") == 2022

    def test_allwinner_m1_year(self):
        chip = {"id": "aw_m1", "name": "M1", "vendor": "Allwinner", "model": "M1"}
        result = enrich_one(chip)
        assert result.get("year") == 2020

    def test_allwinner_r40_year(self):
        chip = {"id": "aw_r40", "name": "R40", "vendor": "Allwinner", "model": "R40"}
        result = enrich_one(chip)
        assert result.get("year") is not None

    def test_allwinner_a100_year(self):
        chip = {"id": "aw_a100", "name": "A100", "vendor": "Allwinner", "model": "A100"}
        result = enrich_one(chip)
        assert result.get("year") is not None

    def test_allwinner_a100t_year(self):
        chip = {"id": "aw_a100t", "name": "A100T", "vendor": "Allwinner", "model": "A100T"}
        result = enrich_one(chip)
        assert result.get("year") == 2014

    def test_allwinner_a40t_year(self):
        chip = {"id": "aw_a40t", "name": "A40T", "vendor": "Allwinner", "model": "A40T"}
        result = enrich_one(chip)
        assert result.get("year") == 2015

    def test_allwinner_a20t_year(self):
        chip = {"id": "aw_a20t", "name": "A20T", "vendor": "Allwinner", "model": "A20T"}
        result = enrich_one(chip)
        assert result.get("year") == 2012

    def test_allwinner_a10t_year(self):
        chip = {"id": "aw_a10t", "name": "A10T", "vendor": "Allwinner", "model": "A10T"}
        result = enrich_one(chip)
        assert result.get("year") == 2011

    def test_allwinner_a05t_year(self):
        chip = {"id": "aw_a05t", "name": "A05T", "vendor": "Allwinner", "model": "A05T"}
        result = enrich_one(chip)
        assert result.get("year") == 2012

    def test_nvidia_tegra_year(self):
        chip = {"id": "tegra4", "name": "Tegra 4", "vendor": "Nvidia", "model": "TEGRA 4"}
        result = enrich_one(chip)
        assert result.get("year") == 2012

    def test_nvidia_x1_year(self):
        chip = {"id": "tegra_x1", "name": "Tegra X1", "vendor": "Nvidia", "model": "T210X1"}
        result = enrich_one(chip)
        assert result.get("year") == 2015

    def test_intel_t120_year(self):
        chip = {"id": "t120", "name": "T120", "vendor": "Intel", "model": "T120"}
        result = enrich_one(chip)
        assert result.get("year") == 2020

    def test_nvidia_tex1_year(self):
        chip = {"id": "tegra_x1", "name": "Tegra X1", "vendor": "Nvidia", "model": "TEGRA X1"}
        result = enrich_one(chip)
        assert result.get("year") == 2015

    def test_intel_atom_z_year(self):
        chip = {"id": "atom_z3740", "name": "Atom Z3740", "vendor": "Intel Atom", "model": "ATOM Z3740"}
        result = enrich_one(chip)
        assert result.get("year") == 2014

    def test_intel_atom_x_year(self):
        chip = {"id": "atom_x7", "name": "Atom x7-Z8700", "vendor": "Intel Atom", "model": "ATOM X7"}
        result = enrich_one(chip)
        assert result.get("year") == 2015

    def test_g_gen_1(self):
        chip = {"id": "x", "name": "G1 GEN 2", "vendor": "Qualcomm", "model": "G1 GEN 2"}
        result = enrich_one(chip)
        assert result.get("year") == 2022

    def test_g2_gen_1(self):
        chip = {"id": "x", "name": "G2 GEN 1", "vendor": "Qualcomm", "model": "G2 GEN 1"}
        result = enrich_one(chip)
        assert result.get("year") == 2022

    def test_g3_gen_3(self):
        chip = {"id": "x", "name": "G3 GEN 3", "vendor": "Qualcomm", "model": "G3 GEN 3"}
        result = enrich_one(chip)
        assert result.get("year") == 2024

    def test_g3x_gen_2(self):
        chip = {"id": "x", "name": "G3X GEN 2", "vendor": "Qualcomm", "model": "G3X GEN 2"}
        result = enrich_one(chip)
        assert result.get("year") == 2023

    def test_microsoft_sq(self):
        chip = {"id": "sq3", "name": "Microsoft SQ3", "vendor": "Qualcomm", "model": "SQ3"}
        result = enrich_one(chip)
        assert result.get("year") == 2021

    def test_qcs_year(self):
        chip = {"id": "qcs", "name": "QCS410", "vendor": "Qualcomm", "model": "QCS410"}
        result = enrich_one(chip)
        assert result.get("year") == 2019

    def test_sc_year(self):
        chip = {"id": "sc", "name": "SC8380", "vendor": "Qualcomm", "model": "SC8380"}
        result = enrich_one(chip)
        assert result.get("year") == 2022

    def test_sa_year(self):
        chip = {"id": "sa", "name": "SA8255", "vendor": "Qualcomm", "model": "SA8255"}
        result = enrich_one(chip)
        assert result.get("year") == 2024

    def test_wear_year(self):
        chip = {"id": "w", "name": "WEAR 2100", "vendor": "Qualcomm", "model": "WEAR 2100"}
        result = enrich_one(chip)
        assert result.get("year") is not None

    def test_w_gen(self):
        chip = {"id": "w", "name": "W5+ GEN 1", "vendor": "Qualcomm", "model": "W5+ GEN 1"}
        result = enrich_one(chip)
        assert result.get("year") == 2022

    def test_xr_gen(self):
        chip = {"id": "xr", "name": "XR2 GEN 1", "vendor": "Qualcomm", "model": "XR2 GEN 1"}
        result = enrich_one(chip)
        assert result.get("year") == 2021

    def test_xr2_no_gen(self):
        chip = {"id": "xr", "name": "XR2", "vendor": "Qualcomm", "model": "XR2"}
        result = enrich_one(chip)
        assert result.get("year") == 2019

    def test_snapdragon_855(self):
        chip = {"id": "sd855", "name": "Snapdragon 855", "vendor": "Qualcomm", "model": "SNAPDRAGON 855"}
        result = enrich_one(chip)
        assert result.get("year") == 2019

    def test_qsd_year(self):
        chip = {"id": "qsd", "name": "QSD8250", "vendor": "Qualcomm", "model": "QSD8250"}
        result = enrich_one(chip)
        assert result.get("year") == 2009

    def test_sw_year(self):
        chip = {"id": "sw", "name": "SW5100", "vendor": "Qualcomm", "model": "SW5100"}
        result = enrich_one(chip)
        assert result.get("year") == 2020

    def test_ce_year(self):
        chip = {"id": "ce", "name": "CE6410", "vendor": "Qualcomm", "model": "CE6410"}
        result = enrich_one(chip)
        assert result.get("year") == 2014

    def test_omap_year(self):
        chip = {"id": "omap", "name": "OMAP4460", "vendor": "TI OMAP", "model": "OMAP4460"}
        result = enrich_one(chip)
        assert result.get("year") is not None

    def test_amlogic_year(self):
        chip = {"id": "aml", "name": "S928", "vendor": "Amlogic", "model": "S928"}
        result = enrich_one(chip)
        assert result.get("year") == 2020

    def test_amlogic_t_year(self):
        chip = {"id": "aml_t", "name": "T920", "vendor": "Amlogic", "model": "T920"}
        result = enrich_one(chip)
        assert result.get("year") == 2018

    def test_kompanio_year(self):
        chip = {"id": "komp", "name": "Kompanio 1300", "vendor": "MediaTek", "model": "KOMPANIO 1300"}
        result = enrich_one(chip)
        assert result.get("year") == 2022

    def test_atom_dn_year(self):
        chip = {"id": "atom_d", "name": "Atom D2500", "vendor": "Intel Atom", "model": "ATOM D2500"}
        result = enrich_one(chip)
        assert result.get("year") == 2012

    def test_ingenic_jz_year(self):
        chip = {"id": "jz", "name": "JZ4780", "vendor": "Ingenic", "model": "JZ4780"}
        result = enrich_one(chip)
        assert result.get("year") == 2009

    def test_thor_year(self):
        chip = {"id": "thor", "name": "THOR", "vendor": "Qualcomm", "model": "THOR"}
        result = enrich_one(chip)
        assert result.get("year") == 2025

    def test_f1_year(self):
        chip = {"id": "f1c", "name": "F1C200", "vendor": "Allwinner", "model": "F1C200"}
        result = enrich_one(chip)
        assert result.get("year") == 2016

    def test_aiot_i_year(self):
        chip = {"id": "aiot", "name": "AIOT I300", "vendor": "Qualcomm", "model": "AIOT I300"}
        result = enrich_one(chip)
        assert result.get("year") == 2023

    def test_sp_year(self):
        chip = {"id": "sp", "name": "SP9860", "vendor": "Spreadtrum", "model": "SP9860"}
        result = enrich_one(chip)
        assert result.get("year") is not None

    def test_ums_year(self):
        chip = {"id": "ums", "name": "UMS9620", "vendor": "Qualcomm", "model": "UMS9620"}
        result = enrich_one(chip)
        assert result.get("year") == 2021

    def test_k3v2_year(self):
        chip = {"id": "k3v2", "name": "K3V2", "vendor": "HiSilicon", "model": "K3V2"}
        result = enrich_one(chip)
        assert result.get("year") == 2012

    def test_k3v2e_year(self):
        chip = {"id": "k3v2e", "name": "K3V2E", "vendor": "HiSilicon", "model": "K3V2E"}
        result = enrich_one(chip)
        assert result.get("year") == 2013

    def test_kirin_t92_year(self):
        chip = {"id": "t92", "name": "KIRIN T92", "vendor": "HiSilicon", "model": "KIRIN T92"}
        result = enrich_one(chip)
        assert result.get("year") == 2025

    def test_broadcom_bcm_year(self):
        chip = {"id": "bcm", "name": "BCM2711", "vendor": "Broadcom", "model": "BCM2711"}
        result = enrich_one(chip)
        assert result is not None

    def test_realtek_year(self):
        chip = {"id": "rtl", "name": "RTD1295", "vendor": "Realtek", "model": "RTD1295"}
        result = enrich_one(chip)
        assert result is not None

    def test_renesas_r_car_year(self):
        chip = {"id": "r8a", "name": "R8A7795", "vendor": "Renesas", "model": "R8A7795"}
        result = enrich_one(chip)
        assert result is not None

    def test_stmicro_year(self):
        chip = {"id": "stm", "name": "STM32MP157", "vendor": "STMicroelectronics", "model": "STM32MP157"}
        result = enrich_one(chip)
        assert result is not None

    def test_microchip_sama_year(self):
        chip = {"id": "sama", "name": "SAMA5D4", "vendor": "Microchip", "model": "SAMA5D4"}
        result = enrich_one(chip)
        assert result is not None

    def test_marvell_armada_year(self):
        chip = {"id": "armada", "name": "ARMADA A38X", "vendor": "Marvell", "model": "ARMADA A38X"}
        result = enrich_one(chip)
        assert result is not None

    def test_actions_ats_year(self):
        chip = {"id": "ats", "name": "ATS3903", "vendor": "Actions", "model": "ATS3903"}
        result = enrich_one(chip)
        assert result is not None

    def test_allwinner_a10_year(self):
        chip = {"id": "aw_a10", "name": "A10", "vendor": "Allwinner", "model": "A10"}
        result = enrich_one(chip)
        assert result.get("year") == 2016

    def test_allwinner_a13_year(self):
        chip = {"id": "aw_a13", "name": "A13", "vendor": "Allwinner", "model": "A13"}
        result = enrich_one(chip)
        assert result.get("year") == 2019

    def test_apq9000_year(self):
        chip = {"id": "apq", "name": "APQ9000", "vendor": "Qualcomm", "model": "APQ9000"}
        result = enrich_one(chip)
        assert result.get("year") == 2018

    def test_apq8998_year(self):
        chip = {"id": "apq", "name": "APQ8998", "vendor": "Qualcomm", "model": "APQ8998"}
        result = enrich_one(chip)
        assert result.get("year") == 2017

    def test_apq8996_year(self):
        chip = {"id": "apq", "name": "APQ8996", "vendor": "Qualcomm", "model": "APQ8996"}
        result = enrich_one(chip)
        assert result.get("year") == 2016

    def test_apq8995_year(self):
        chip = {"id": "apq", "name": "APQ8995", "vendor": "Qualcomm", "model": "APQ8995"}
        result = enrich_one(chip)
        assert result.get("year") == 2015

    def test_apq8974_year(self):
        chip = {"id": "apq", "name": "APQ8974", "vendor": "Qualcomm", "model": "APQ8974"}
        result = enrich_one(chip)
        assert result.get("year") == 2013

    def test_apq8960_year(self):
        chip = {"id": "apq", "name": "APQ8960", "vendor": "Qualcomm", "model": "APQ8960"}
        result = enrich_one(chip)
        assert result.get("year") == 2012

    def test_apq8900_year(self):
        chip = {"id": "apq", "name": "APQ8900", "vendor": "Qualcomm", "model": "APQ8900"}
        result = enrich_one(chip)
        assert result.get("year") == 2011

    def test_apq8200_year(self):
        chip = {"id": "apq", "name": "APQ8200", "vendor": "Qualcomm", "model": "APQ8200"}
        result = enrich_one(chip)
        assert result.get("year") == 2010

    def test_apq7600_year(self):
        chip = {"id": "apq", "name": "APQ7600", "vendor": "Qualcomm", "model": "APQ7600"}
        result = enrich_one(chip)
        assert result.get("year") == 2009

    def test_apq7200_year(self):
        chip = {"id": "apq", "name": "APQ7200", "vendor": "Qualcomm", "model": "APQ7200"}
        result = enrich_one(chip)
        assert result.get("year") == 2008

    def test_apq7000_year(self):
        chip = {"id": "apq", "name": "APQ7000", "vendor": "Qualcomm", "model": "APQ7000"}
        result = enrich_one(chip)
        assert result.get("year") == 2007

    def test_exynos_1000_year(self):
        chip = {"id": "ex1000", "name": "Exynos 1000", "vendor": "Samsung", "model": "EXYNOS 1000"}
        result = enrich_one(chip)
        assert result.get("year") == 2005

    def test_sc8280_year(self):
        chip = {"id": "sc", "name": "SC8280", "vendor": "Qualcomm", "model": "SC8280"}
        result = enrich_one(chip)
        assert result.get("year") == 2021

    def test_sc8180_year(self):
        chip = {"id": "sc", "name": "SC8180", "vendor": "Qualcomm", "model": "SC8180"}
        result = enrich_one(chip)
        assert result.get("year") == 2019

    def test_sc7280_year(self):
        chip = {"id": "sc", "name": "SC7280", "vendor": "Qualcomm", "model": "SC7280"}
        result = enrich_one(chip)
        assert result.get("year") == 2021

    def test_sc7180_year(self):
        chip = {"id": "sc", "name": "SC7180", "vendor": "Qualcomm", "model": "SC7180"}
        result = enrich_one(chip)
        assert result.get("year") == 2020

    def test_sc6000_year(self):
        chip = {"id": "sc", "name": "SC6000", "vendor": "Qualcomm", "model": "SC6000"}
        result = enrich_one(chip)
        assert result.get("year") == 2018

    def test_sa8295_year(self):
        chip = {"id": "sa", "name": "SA8295", "vendor": "Qualcomm", "model": "SA8295"}
        result = enrich_one(chip)
        assert result.get("year") == 2021

    def test_sa8195_year(self):
        chip = {"id": "sa", "name": "SA8195", "vendor": "Qualcomm", "model": "SA8195"}
        result = enrich_one(chip)
        assert result.get("year") == 2019

    def test_sa6155_year(self):
        chip = {"id": "sa", "name": "SA6155", "vendor": "Qualcomm", "model": "SA6155"}
        result = enrich_one(chip)
        assert result.get("year") == 2019

    def test_sa6149_year(self):
        chip = {"id": "sa", "name": "SA6149", "vendor": "Qualcomm", "model": "SA6149"}
        result = enrich_one(chip)
        assert result.get("year") == 2018

    def test_sd855_year(self):
        chip = {"id": "sd", "name": "Snapdragon 855", "vendor": "Qualcomm", "model": "SNAPDRAGON 855"}
        result = enrich_one(chip)
        assert result.get("year") == 2019

    def test_sd845_year(self):
        chip = {"id": "sd", "name": "Snapdragon 845", "vendor": "Qualcomm", "model": "SNAPDRAGON 845"}
        result = enrich_one(chip)
        assert result.get("year") == 2018

    def test_sd835_year(self):
        chip = {"id": "sd", "name": "Snapdragon 835", "vendor": "Qualcomm", "model": "SNAPDRAGON 835"}
        result = enrich_one(chip)
        assert result.get("year") == 2017

    def test_sd820_year(self):
        chip = {"id": "sd", "name": "Snapdragon 820", "vendor": "Qualcomm", "model": "SNAPDRAGON 820"}
        result = enrich_one(chip)
        assert result.get("year") == 2016

    def test_sd810_year(self):
        chip = {"id": "sd", "name": "Snapdragon 810", "vendor": "Qualcomm", "model": "SNAPDRAGON 810"}
        result = enrich_one(chip)
        assert result.get("year") == 2015

    def test_sd800_year(self):
        chip = {"id": "sd", "name": "Snapdragon 800", "vendor": "Qualcomm", "model": "SNAPDRAGON 800"}
        result = enrich_one(chip)
        assert result.get("year") == 2014

    def test_sd600_year(self):
        chip = {"id": "sd", "name": "Snapdragon 600", "vendor": "Qualcomm", "model": "SNAPDRAGON 600"}
        result = enrich_one(chip)
        assert result.get("year") == 2014

    def test_sd400_year(self):
        chip = {"id": "sd", "name": "Snapdragon 400", "vendor": "Qualcomm", "model": "SNAPDRAGON 400"}
        result = enrich_one(chip)
        assert result.get("year") == 2013

    def test_sd200_year(self):
        chip = {"id": "sd", "name": "Snapdragon 200", "vendor": "Qualcomm", "model": "SNAPDRAGON 200"}
        result = enrich_one(chip)
        assert result.get("year") == 2012

    def test_amlogic_s922_year(self):
        chip = {"id": "aml", "name": "S922", "vendor": "Amlogic", "model": "S922"}
        result = enrich_one(chip)
        assert result.get("year") == 2019

    def test_amlogic_s912_year(self):
        chip = {"id": "aml", "name": "S912", "vendor": "Amlogic", "model": "S912"}
        result = enrich_one(chip)
        assert result.get("year") == 2016

    def test_amlogic_s812_year(self):
        chip = {"id": "aml", "name": "S812", "vendor": "Amlogic", "model": "S812"}
        result = enrich_one(chip)
        assert result.get("year") == 2015

    def test_amlogic_s805_year(self):
        chip = {"id": "aml", "name": "S805", "vendor": "Amlogic", "model": "S805"}
        result = enrich_one(chip)
        assert result.get("year") == 2014

    def test_amlogic_s802_year(self):
        chip = {"id": "aml", "name": "S802", "vendor": "Amlogic", "model": "S802"}
        result = enrich_one(chip)
        assert result.get("year") == 2013

    def test_amlogic_s700_year(self):
        chip = {"id": "aml", "name": "S700", "vendor": "Amlogic", "model": "S700"}
        result = enrich_one(chip)
        assert result.get("year") == 2012

    def test_amlogic_t960_year(self):
        chip = {"id": "aml", "name": "T960", "vendor": "Amlogic", "model": "T960"}
        result = enrich_one(chip)
        assert result.get("year") == 2016

    def test_amlogic_t950_year(self):
        chip = {"id": "aml", "name": "T950", "vendor": "Amlogic", "model": "T950"}
        result = enrich_one(chip)
        assert result.get("year") == 2015

    def test_amlogic_t920_year(self):
        chip = {"id": "aml", "name": "T920", "vendor": "Amlogic", "model": "T920"}
        result = enrich_one(chip)
        assert result.get("year") == 2018

    def test_amlogic_t910_year(self):
        chip = {"id": "aml", "name": "T910", "vendor": "Amlogic", "model": "T910"}
        result = enrich_one(chip)
        assert result.get("year") == 2014

    def test_kompanio_500_year(self):
        chip = {"id": "komp", "name": "Kompanio 500", "vendor": "MediaTek", "model": "KOMPANIO 500"}
        result = enrich_one(chip)
        assert result.get("year") == 2021

    def test_kompanio_300_year(self):
        chip = {"id": "komp", "name": "Kompanio 300", "vendor": "MediaTek", "model": "KOMPANIO 300"}
        result = enrich_one(chip)
        assert result.get("year") == 2020

    def test_kirin_t91_year(self):
        chip = {"id": "t91", "name": "KIRIN T91", "vendor": "HiSilicon", "model": "KIRIN T91"}
        result = enrich_one(chip)
        assert result.get("year") == 2024

    def test_kirin_t90_year(self):
        chip = {"id": "t90", "name": "KIRIN T90", "vendor": "HiSilicon", "model": "KIRIN T90"}
        result = enrich_one(chip)
        assert result.get("year") == 2023

    def test_kirin_t80_year(self):
        chip = {"id": "t80", "name": "KIRIN T80", "vendor": "HiSilicon", "model": "KIRIN T80"}
        result = enrich_one(chip)
        assert result.get("year") == 2020

    def test_g3_gen_1_year(self):
        chip = {"id": "g3", "name": "G3 GEN 1", "vendor": "Qualcomm", "model": "G3 GEN 1"}
        result = enrich_one(chip)
        assert result.get("year") == 2021

    def test_g3x_gen_1_year(self):
        chip = {"id": "g3x", "name": "G3X GEN 1", "vendor": "Qualcomm", "model": "G3X GEN 1"}
        result = enrich_one(chip)
        assert result.get("year") == 2021

    def test_xr2_year(self):
        chip = {"id": "xr2", "name": "XR2", "vendor": "Qualcomm", "model": "XR2"}
        result = enrich_one(chip)
        assert result.get("year") == 2019

    def test_xr1_year(self):
        chip = {"id": "xr1", "name": "XR1", "vendor": "Qualcomm", "model": "XR1"}
        result = enrich_one(chip)
        assert result.get("year") == 2018

    def test_wear_2100_year(self):
        chip = {"id": "w", "name": "WEAR 2100", "vendor": "Qualcomm", "model": "WEAR 2100"}
        result = enrich_one(chip)
        assert result.get("year") == 2020

    def test_npu_qualcomm_vendor(self):
        chip = {"id": "x", "name": "Snapdragon SM8250", "vendor": "Qualcomm", "model": "SM8250", "year": 2020}
        result = enrich_one(chip)
        assert result.get("npu") is not None


class TestGPUInference:
    def test_gpu_qualcomm_fallback(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "year": 2022}
        result = enrich_one(chip)
        assert result.get("gpu") == "Adreno GPU"

    def test_gpu_samsung_fallback(self):
        chip = {"id": "x", "name": "Exynos", "vendor": "Samsung", "year": 2020}
        result = enrich_one(chip)
        assert result.get("gpu") == "Mali GPU"

    def test_gpu_hisilicon_fallback(self):
        chip = {"id": "x", "name": "Kirin", "vendor": "HiSilicon", "year": 2020}
        result = enrich_one(chip)
        assert result.get("gpu") == "Mali GPU"

    def test_gpu_unisoc_fallback(self):
        chip = {"id": "x", "name": "Unisoc", "vendor": "Unisoc", "year": 2020}
        result = enrich_one(chip)
        assert result.get("gpu") == "Mali GPU"

    def test_gpu_mediatek_fallback(self):
        chip = {"id": "x", "name": "MTK", "vendor": "MediaTek", "year": 2020}
        result = enrich_one(chip)
        assert result.get("gpu") == "Mali GPU"

    def test_gpu_nxp_imx(self):
        chip = {"id": "x", "name": "i.MX 8", "vendor": "NXP i.MX", "year": 2020}
        result = enrich_one(chip)
        assert result.get("gpu") is not None

    def test_gpu_xilinx(self):
        chip = {"id": "x", "name": "Zynq", "vendor": "Xilinx", "year": 2020}
        result = enrich_one(chip)
        assert result.get("gpu") is not None

    def test_gpu_ti_omap(self):
        chip = {"id": "x", "name": "OMAP", "vendor": "TI OMAP", "year": 2012}
        result = enrich_one(chip)
        assert result.get("gpu") == "PowerVR SGX"

    def test_gpu_ingenic_old(self):
        chip = {"id": "x", "name": "JZ", "vendor": "Ingenic", "year": 2013}
        result = enrich_one(chip)
        assert result.get("gpu") == "GC400"

    def test_gpu_ingenic_new(self):
        chip = {"id": "x", "name": "JZ", "vendor": "Ingenic", "year": 2015}
        result = enrich_one(chip)
        assert result.get("gpu") == "GC800"

    def test_gpu_allwinner_old(self):
        chip = {"id": "x", "name": "A", "vendor": "Allwinner", "year": 2013}
        result = enrich_one(chip)
        assert result.get("gpu") is not None

    def test_gpu_amlogic_old(self):
        chip = {"id": "x", "name": "S", "vendor": "Amlogic", "year": 2015}
        result = enrich_one(chip)
        assert result.get("gpu") is not None

    def test_gpu_rockchip_old(self):
        chip = {"id": "x", "name": "RK", "vendor": "Rockchip", "year": 2013}
        result = enrich_one(chip)
        assert result.get("gpu") is not None


class TestModemInference:
    def test_modem_qualcomm_gen3(self):
        chip = {"id": "x", "name": "Snapdragon 8 Gen 3", "vendor": "Qualcomm", "model": "SNAPDRAGON 8 GEN 3", "year": 2024}
        result = enrich_one(chip)
        assert "5G" in (result.get("modem") or "")

    def test_modem_qualcomm_old_gen(self):
        chip = {"id": "x", "name": "Snapdragon 8 Gen 1", "vendor": "Qualcomm", "model": "SNAPDRAGON 8 GEN 1", "year": 2022}
        result = enrich_one(chip)
        assert result.get("modem") is not None

    def test_modem_qualcomm_4g(self):
        chip = {"id": "x", "name": "Snapdragon", "vendor": "Qualcomm", "year": 2015}
        result = enrich_one(chip)
        assert "4G" in (result.get("modem") or "")

    def test_modem_mediatek_5g(self):
        chip = {"id": "x", "name": "Dimensity", "vendor": "MediaTek", "model": "DIMENSITY 9000", "year": 2022}
        result = enrich_one(chip)
        assert "5G" in (result.get("modem") or "")

    def test_modem_mediatek_4g(self):
        chip = {"id": "x", "name": "MT6785", "vendor": "MediaTek", "model": "MT6785", "year": 2018}
        result = enrich_one(chip)
        assert "4G" in (result.get("modem") or "")

    def test_modem_samsung_4g(self):
        chip = {"id": "x", "name": "Exynos", "vendor": "Samsung", "model": "EXYNOS 5433", "year": 2016}
        result = enrich_one(chip)
        assert "4G" in (result.get("modem") or "")

    def test_modem_hisilicon_balong_5g(self):
        chip = {"id": "x", "name": "Kirin", "vendor": "HiSilicon", "model": "KIRIN 9000", "year": 2020}
        result = enrich_one(chip)
        assert "5G" in (result.get("modem") or "")

    def test_modem_hisilicon_balong_4g(self):
        chip = {"id": "x", "name": "Kirin", "vendor": "HiSilicon", "model": "KIRIN 930", "year": 2016}
        result = enrich_one(chip)
        assert "4G" in (result.get("modem") or "")


class TestNPUInference:
    def test_npu_qualcomm_sm6(self):
        chip = {"id": "x", "name": "Snapdragon 6 Gen 1", "vendor": "Qualcomm", "model": "SM6450", "year": 2023}
        result = enrich_one(chip)
        assert result.get("npu") is not None

    def test_npu_mediatek_mt_below_8000(self):
        chip = {"id": "mt6785", "name": "Helio G90", "vendor": "MediaTek", "model": "MT6785", "year": 2020}
        result = enrich_one(chip)
        assert "Helio" not in (result.get("model", ""))  # not Dimensity, not MT>=8000


class TestMemoryInference:
    def test_memory_type_by_year_2023(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "year": 2023}
        result = enrich_one(chip)
        assert result.get("memory_type") == "LPDDR5X"

    def test_memory_type_by_year_2019(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "year": 2019}
        result = enrich_one(chip)
        assert result.get("memory_type") == "LPDDR4X"

    def test_memory_type_by_year_2016(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "year": 2016}
        result = enrich_one(chip)
        assert result.get("memory_type") == "LPDDR4"

    def test_memory_type_by_year_2014(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "year": 2014}
        result = enrich_one(chip)
        assert result.get("memory_type") == "LPDDR3"

    def test_memory_type_by_year_2012(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "year": 2012}
        result = enrich_one(chip)
        assert result.get("memory_type") == "LPDDR2"

    def test_memory_type_by_year_2005(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "year": 2005}
        result = enrich_one(chip)
        assert result.get("memory_type") == "LPDDR"

    def test_storage_type_by_year_2021(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "year": 2021}
        result = enrich_one(chip)
        assert result.get("storage_type") == "UFS 3.1"

    def test_storage_type_by_year_2019(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "year": 2019}
        result = enrich_one(chip)
        assert result.get("storage_type") == "UFS 3.0"

    def test_storage_type_by_year_2017(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "year": 2017}
        result = enrich_one(chip)
        assert result.get("storage_type") == "UFS 2.1"

    def test_storage_type_by_year_2015(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "year": 2015}
        result = enrich_one(chip)
        assert result.get("storage_type") == "UFS 2.0"

    def test_storage_type_by_year_2014(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "year": 2014}
        result = enrich_one(chip)
        assert result.get("storage_type") == "eMMC 5.0"

    def test_memory_clock_lpddr5(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "memory_type": "LPDDR5", "year": 2021}
        result = enrich_one(chip)
        assert result.get("memory_clock") == 3200

    def test_memory_clock_lpddr4(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "memory_type": "LPDDR4", "year": 2020}
        result = enrich_one(chip)
        assert result.get("memory_clock") == 1600

    def test_memory_clock_lpddr3(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "memory_type": "LPDDR3", "year": 2016}
        result = enrich_one(chip)
        assert result.get("memory_clock") == 800

    def test_memory_clock_lpddr2(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "memory_type": "LPDDR2", "year": 2012}
        result = enrich_one(chip)
        assert result.get("memory_clock") == 533

    def test_memory_clock_lpddr(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "memory_type": "LPDDR", "year": 2005}
        result = enrich_one(chip)
        assert result.get("memory_clock") == 400

    def test_memory_bus_lpddr4x(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "memory_type": "LPDDR4X", "year": 2020}
        result = enrich_one(chip)
        assert result.get("memory_bus") == 64

    def test_memory_bus_lpddr5x(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "memory_type": "LPDDR5X", "year": 2023}
        result = enrich_one(chip)
        assert result.get("memory_bus") == 64

    def test_memory_bus_lpddr2(self):
        chip = {"id": "x", "name": "X", "vendor": "Qualcomm", "memory_type": "LPDDR2", "year": 2012}
        result = enrich_one(chip)
        assert result.get("memory_bus") == 32


class TestWriteVendorFile:
    def test_write_new_vendor(self, tmp_path):
        chips = [{"id": "chip1", "name": "Test Chip", "vendor": "VendorX", "model": "VC1"}]
        with patch("soc_db.common.DATA_DIR", tmp_path), patch("soc_db.common.VENDOR_FILES", {"VendorX": "vendorx.json"}):
            write_vendor_file("VendorX", chips)
        fpath = tmp_path / "vendorx.json"
        assert fpath.exists()
        data = json.loads(fpath.read_text())
        assert len(data) == 1
        assert data[0]["id"] == "chip1"

    def test_merge_existing(self, tmp_path):
        existing = [{"id": "chip1", "name": "Test Chip", "vendor": "VendorX", "model": "VC1"}]
        (tmp_path / "vendorx.json").write_text(json.dumps(existing))
        new_chips = [{"id": "chip1", "name": "Test Chip", "vendor": "VendorX", "model": "VC1", "cores": 8}]
        with patch("soc_db.common.DATA_DIR", tmp_path), patch("soc_db.common.VENDOR_FILES", {"VendorX": "vendorx.json"}):
            write_vendor_file("VendorX", new_chips)
        data = json.loads((tmp_path / "vendorx.json").read_text())
        assert len(data) == 1
        assert data[0].get("cores") == 8

    def test_merge_adds_new_chip(self, tmp_path):
        existing = [{"id": "chip1", "name": "Old Chip", "vendor": "VendorX", "model": "OC1"}]
        (tmp_path / "vendorx.json").write_text(json.dumps(existing))
        new_chips = [
            {"id": "chip2", "name": "New Chip", "vendor": "VendorX", "model": "NC1"},
        ]
        with patch("soc_db.common.DATA_DIR", tmp_path), patch("soc_db.common.VENDOR_FILES", {"VendorX": "vendorx.json"}):
            write_vendor_file("VendorX", new_chips)
        data = json.loads((tmp_path / "vendorx.json").read_text())
        assert len(data) == 2

    def test_unknown_vendor(self, tmp_path, caplog):
        chips = [{"id": "x", "name": "X", "vendor": "NoSuch"}]
        with patch("soc_db.common.DATA_DIR", tmp_path):
            write_vendor_file("NoSuch", chips)
        assert "Unknown vendor" in caplog.text

    def test_corrupt_existing_file(self, tmp_path):
        (tmp_path / "vendorx.json").write_text("not valid json{{{")
        chips = [{"id": "chip1", "name": "Test Chip", "vendor": "VendorX", "model": "VC1"}]
        with patch("soc_db.common.DATA_DIR", tmp_path), patch("soc_db.common.VENDOR_FILES", {"VendorX": "vendorx.json"}):
            write_vendor_file("VendorX", chips)
        data = json.loads((tmp_path / "vendorx.json").read_text())
        assert len(data) == 1

    def test_name_model_diff(self, tmp_path):
        existing = [{"id": "oc1", "name": "Old Chip", "vendor": "VendorX", "model": "OC1"}]
        (tmp_path / "vendorx.json").write_text(json.dumps(existing))
        new_chips = [{"id": "oc1", "name": "New Chip Name", "vendor": "VendorX", "model": "OC1"}]
        with patch("soc_db.common.DATA_DIR", tmp_path), patch("soc_db.common.VENDOR_FILES", {"VendorX": "vendorx.json"}):
            write_vendor_file("VendorX", new_chips)
        data = json.loads((tmp_path / "vendorx.json").read_text())
        assert data[0]["name"] == "New Chip Name"

    def test_slug_change(self, tmp_path):
        existing = [{"id": "chip1", "name": "Test Chip", "vendor": "VendorX", "model": "VC1"}]
        (tmp_path / "vendorx.json").write_text(json.dumps(existing))
        new_chips = [{"id": "chip1", "name": "Renamed Chip", "vendor": "VendorX", "model": "VC1"}]
        with patch("soc_db.common.DATA_DIR", tmp_path), patch("soc_db.common.VENDOR_FILES", {"VendorX": "vendorx.json"}):
            write_vendor_file("VendorX", new_chips)
        data = json.loads((tmp_path / "vendorx.json").read_text())
        assert data[0]["id"] == "renamed_chip_vc1"

    def test_stale_removal(self, tmp_path):
        existing = [{"id": "stale", "name": "Mali GPU", "vendor": "VendorX", "model": "MG1", "completeness": 0.1}]
        (tmp_path / "vendorx.json").write_text(json.dumps(existing))
        new_chips = [{"id": "chip1", "name": "New Chip", "vendor": "VendorX", "model": "VC1"}]
        with patch("soc_db.common.DATA_DIR", tmp_path), patch("soc_db.common.VENDOR_FILES", {"VendorX": "vendorx.json"}):
            write_vendor_file("VendorX", new_chips)
        data = json.loads((tmp_path / "vendorx.json").read_text())
        ids = [c["id"] for c in data]
        assert "stale" not in ids

    def test_name_model_stale(self, tmp_path):
        existing = [
            {"id": "keep", "name": "Keep Chip", "vendor": "VendorX", "model": "KC1"},
            {"id": "dup", "name": "keep", "vendor": "VendorX", "model": "KC1", "completeness": 0.1},
        ]
        (tmp_path / "vendorx.json").write_text(json.dumps(existing))
        new_chips = [{"id": "keep", "name": "Keep Chip", "vendor": "VendorX", "model": "KC1"}]
        with patch("soc_db.common.DATA_DIR", tmp_path), patch("soc_db.common.VENDOR_FILES", {"VendorX": "vendorx.json"}):
            write_vendor_file("VendorX", new_chips)
        data = json.loads((tmp_path / "vendorx.json").read_text())
        assert len(data) == 1


class TestRealData:
    """Test enrichment against actual data files."""

    @pytest.mark.parametrize(
        "vendor_file",
        [
            "qualcomm.json",
            "mediatek.json",
            "exynos.json",
            "kirin.json",
            "apple.json",
            "intel_atom.json",
            "rockchip.json",
            "allwinner.json",
            "amlogic.json",
            "nvidia.json",
            "ti_omap.json",
            "ingenic.json",
            "broadcom.json",
            "nxp_imx.json",
            "realtek.json",
            "renesas.json",
            "stmicro.json",
            "unisoc.json",
            "tensor.json",
            "xilinx.json",
            "marvell.json",
            "actions.json",
            "microchip.json",
        ],
    )
    def test_load_and_enrich(self, vendor_file):
        path = DATA_DIR / vendor_file
        if not path.exists():
            pytest.skip(f"{vendor_file} not found")
        with open(path) as f:
            chips = json.load(f)
        assert len(chips) > 0
        results = enrich_all(chips)
        assert len(results) == len(chips)
        for c in results:
            assert c.get("completeness") is not None
            assert c.get("updated") is not None
            assert c.get("vendor") is not None
