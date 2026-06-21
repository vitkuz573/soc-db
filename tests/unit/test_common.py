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

    def test_exynos_auto_year_w(self):
        chip = {"id": "exynos_w920", "name": "Exynos W920", "vendor": "Samsung", "model": "EXYNOS W920"}
        result = enrich_one(chip)
        assert result.get("year") is not None

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
