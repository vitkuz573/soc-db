#!/usr/bin/env python3
"""Enrich SoC data: completeness scoring, vendor knowledge, field sources."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

FIELD_GROUPS = {
    "identity": ["id", "name", "vendor", "model", "aliases", "codename", "description"],
    "core": ["architecture", "isa", "cores", "threads", "cluster_config", "clock_max", "clock_mid", "clock_min", "max_freq", "cache"],
    "process": ["process_nm", "process_name", "process", "tdp"],
    "gpu": ["gpu", "gpu_clock", "gpu_api", "gpu_tflops"],
    "memory": ["memory_type", "memory_max", "memory_clock", "memory_bus", "memory_bandwidth", "storage_type"],
    "ai": ["npu", "ai_ops"],
    "modem": ["modem", "modem_dl", "modem_ul", "cellular"],
    "media": ["video_decode", "video_encode", "display_max", "camera_max", "isps", "video_capture"],
    "connectivity": ["wifi", "bluetooth", "usb", "navigation", "charging"],
    "lifecycle": ["year", "announced", "revision", "status"],
    "provenance": ["completeness", "sources", "updated", "datasheet_url", "wikipedia_url", "wikidata_id", "linux_dt_compatible"],
    "metadata": ["devices", "alternative_names", "parent", "tags", "rating", "benchmarks"],
}

FIELD_WEIGHTS = {
    "name": 5, "vendor": 5, "model": 5, "architecture": 4, "cores": 4,
    "process_nm": 3, "gpu": 3, "memory_type": 2, "year": 3,
    "clock_max": 3, "modem": 2, "npu": 2, "wifi": 2, "bluetooth": 2,
    "display_max": 2, "camera_max": 2, "video_decode": 2, "video_encode": 2,
}

VENDOR_KNOWLEDGE = {
    "Qualcomm": {
        "architecture": "ARMv8",
        "process_map": {
            "sm8750": 3, "sm8650": 4, "sm8550": 4, "sm8475": 4, "sm8450": 4,
            "sm8350": 5, "sm8250": 7, "sm8150": 7, "sm7250": 8, "sm7150": 8,
            "sm6350": 8, "sdm845": 10, "sdm835": 10, "sdm820": 14,
            "sdm660": 14, "sdm636": 14, "sdm632": 14, "sdm630": 14, "sdm625": 14,
            "msm8998": 10, "msm8996": 14, "msm8994": 20, "msm8992": 20,
            "msm8940": 28, "msm8937": 28, "msm8917": 28,
        },
        "gpu_map": {
            "sm8750": "Adreno 830", "sm8650": "Adreno 750", "sm8550": "Adreno 740",
            "sm8475": "Adreno 730", "sm8450": "Adreno 730", "sm8350": "Adreno 660",
            "sm8250": "Adreno 650", "sm8150": "Adreno 640",
            "sm7250": "Adreno 620", "sm7150": "Adreno 618",
        },
    },
    "MediaTek": {"architecture": "ARMv8", "process_map": {"mt6983": 4, "mt6985": 4, "mt6991": 4, "mt6893": 6, "mt6895": 6, "mt6877": 6, "mt6879": 6, "mt6833": 7, "mt6853": 7, "mt6785": 12, "mt6779": 12}},
    "Apple": {"architecture": "ARMv8"},
    "Samsung": {"architecture": "ARMv8"},
    "HiSilicon": {"architecture": "ARMv8"},
    "Google": {"architecture": "ARMv8"},
    "Rockchip": {"architecture": "ARMv8"},
    "Allwinner": {"architecture": "ARMv8"},
    "Amlogic": {"architecture": "ARMv8"},
}


def _has(chip, field):
    v = chip.get(field)
    return v is not None and v != "" and v != [] and v != 0


def enrich(chips):
    for chip in chips:
        if not chip.get("model"):
            chip["model"] = chip.get("name", chip.get("id", "unknown"))
        vk = VENDOR_KNOWLEDGE.get(chip.get("vendor", ""), {})
        model_upper = chip.get("model", "").upper()
        if not chip.get("architecture") and vk.get("architecture"):
            chip["architecture"] = vk["architecture"]
        if not chip.get("process_nm") and vk.get("process_map"):
            for key, nm in vk["process_map"].items():
                if key.upper() in model_upper:
                    chip["process_nm"] = nm
                    chip["process_name"] = f"{nm}nm"
                    break
        if not chip.get("gpu") and vk.get("gpu_map"):
            for key, gpu_name in vk["gpu_map"].items():
                if key.upper() in model_upper:
                    chip["gpu"] = gpu_name
                    break
        if not chip.get("aliases"):
            aliases = set()
            name = chip.get("name", "")
            model = chip.get("model", "")
            if name and model and model not in name:
                aliases.add(f"{name} ({model})")
            codenames = {"SM8250": ["Kona"], "SM8350": ["Lahaina"], "SM8450": ["Waipio"], "SM8475": ["Waipio"], "SM8550": ["Kalama"], "SM8650": ["Pineapple"], "SM8750": ["Pineapple"]}
            for key, alist in codenames.items():
                if key.upper() in model_upper:
                    for a in alist:
                        aliases.add(a)
            if aliases:
                chip["aliases"] = sorted(aliases)
        w_total = sum(FIELD_WEIGHTS.get(f, 1) for _, flist in FIELD_GROUPS.items() for f in flist)
        w_filled = sum(FIELD_WEIGHTS.get(f, 1) for _, flist in FIELD_GROUPS.items() for f in flist if _has(chip, f))
        chip["completeness"] = round(w_filled / max(w_total, 1), 4)
        if not chip.get("sources"):
            chip["sources"] = {}
        chip["updated"] = "2026-06-21"
    return chips


def main():
    for fpath in sorted(DATA_DIR.glob("*.json")):
        if fpath.name == "index.json":
            continue
        chips = json.loads(fpath.read_text("utf-8"))
        enrich(chips)
        fpath.write_text(json.dumps(chips, indent=2, ensure_ascii=False) + "\n", "utf-8")
        avg = sum(c.get("completeness", 0) for c in chips) / max(len(chips), 1)
        print(f"  {fpath.name}: {len(chips)} entries, completeness {avg:.3f}")


if __name__ == "__main__":
    main()
