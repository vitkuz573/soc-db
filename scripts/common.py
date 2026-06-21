"""Shared utilities for SoC scrapers."""

import hashlib
import json
import re
import sys
import time
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_DIR = Path("/tmp/soc-db-cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
USER_AGENT = "SOC-DB/1.0 (+https://github.com/vitkuz573/soc-db)"


def fetch(url: str, ttl: int = 86400) -> str:
    key = hashlib.md5(url.encode()).hexdigest()
    cache_file = CACHE_DIR / key
    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < ttl:
            return cache_file.read_text("utf-8")
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=30) as resp:
        data = resp.read().decode("utf-8")
    cache_file.write_text(data, "utf-8")
    time.sleep(1)
    return data


def extract_int(text: str) -> int | None:
    if not text:
        return None
    m = re.search(r"\d+", text)
    return int(m.group()) if m else None


def extract_freq(text: str) -> str | None:
    if not text:
        return None
    m = re.search(r"[\d.]+[\s]*(?:MHz|GHz)", text, re.IGNORECASE)
    if m:
        return m.group().strip()
    m2 = re.search(r"(?:up to\s*)?([\d.]+)\s*(?:GHz|MHz)", text, re.IGNORECASE)
    return f"{m2.group(1)} {m2.group(2)}" if m2 else None


def extract_process(text: str) -> str | None:
    if not text:
        return None
    m = re.search(r"(\d+)\s*nm", text, re.IGNORECASE)
    return m.group(0) if m else None


def clean(text: str | None) -> str | None:
    if not text:
        return None
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\[\w+\]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def slug(name: str, model: str = "") -> str:
    s = name.lower().replace("+", "p").replace("®", "").replace("-", "_")
    s = re.sub(r"[^a-z0-9_ ]", "", s)
    parts = [p for p in s.split() if p]
    skip = {"with", "and", "the", "for", "integrated", "support",
            "using", "based", "cores", "ghz", "mhz", "kryo", "cortex"}
    parts = [p for p in parts if p not in skip]
    base = "_".join(parts[:6]) if parts else "chip"
    if model:
        m = re.sub(r"[^a-z0-9]", "", model.lower()).strip()
        if m and m not in base:
            base = f"{base}_{m}"
    base = re.sub(r"_+", "_", base).strip("_")
    return base or "unknown"


def _match_existing(chip: dict, existing: dict) -> str | None:
    """Find existing entry by id or by model number."""
    cid = chip.get("id", "")
    if cid in existing:
        return cid
    model = chip.get("model", "").strip().upper()
    if model:
        for eid, ec in existing.items():
            if ec.get("model", "").strip().upper() == model:
                return eid
    name = chip.get("name", "").lower().strip()
    if name:
        for eid, ec in existing.items():
            if ec.get("name", "").lower().strip() == name:
                return eid
    return None


def write_vendor_file(vendor: str, chips: list[dict]) -> None:
    vfile = VENDOR_FILES.get(vendor)
    if not vfile:
        print(f"  Unknown vendor: {vendor}")
        return
    fpath = DATA_DIR / vfile
    existing = {}
    if fpath.exists():
        try:
            for c in json.loads(fpath.read_text("utf-8")):
                existing[c["id"]] = c
        except json.JSONDecodeError:
            pass
    added = updated = merged = 0
    for chip in chips:
        match_id = _match_existing(chip, existing)
        if match_id:
            old = existing[match_id]
            # Only copy fields that old is missing (prefer existing data)
            for k, v in chip.items():
                if k not in old or old[k] in (None, "", [], 0, 0.0):
                    if v not in (None, "", [], 0, 0.0):
                        old[k] = v
            updated += 1
        else:
            existing[chip["id"]] = dict(chip)
            added += 1
    output = sorted(existing.values(), key=lambda x: (x.get("year", 9999), x["name"]))
    output = enrich_all(output)
    fpath.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", "utf-8")
    print(f"  {vfile}: {len(output)} entries ({added} new, {updated} updated)")


VENDOR_FILES = {
    "Qualcomm": "qualcomm.json",
    "MediaTek": "mediatek.json",
    "Samsung": "exynos.json",
    "HiSilicon": "kirin.json",
    "Google": "tensor.json",
    "Apple": "apple.json",
    "Rockchip": "rockchip.json",
    "Allwinner": "allwinner.json",
    "Amlogic": "amlogic.json",
    "Nvidia": "nvidia.json",
    "TI OMAP": "ti_omap.json",
    "Intel Atom": "intel_atom.json",
    "Ingenic": "ingenic.json",
    "NXP i.MX": "nxp_imx.json",
    "Actions": "actions.json",
    "Broadcom": "broadcom.json",
    "Marvell": "marvell.json",
    "Realtek": "realtek.json",
    "Unisoc": "unisoc.json",
    "Renesas": "renesas.json",
    "STMicroelectronics": "stmicro.json",
    "Microchip": "microchip.json",
    "Xilinx": "xilinx.json",
}


def extract_model(text: str) -> str | None:
    patterns = [
        r'\b(SM\d{3,}|SDM\d{3,}|MSM\d{3,}|APQ\d{3,}|SC\d{4}|QCS\d{3})\b',
        r'\b(MT\d{4,})\b',
        r'\b(Exynos\s*\d{4,})\b',
        r'\b(Kirin\s*\d{3,})\b',
        r'\b(GS\d{3})\b',
        r'\b(RK\d{3,})\b',
        r'\b(OMAP\d{4,})\b',
        r'\b(AM\d{3,}|DM\d{3,})\b',
        r'\b(APL\w+|T\d{4})\b',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).upper()
    return None


def merge_chips(a: dict, b: dict) -> dict:
    merged = dict(a)
    for k, v in b.items():
        if v not in (None, "", 0, []):
            merged[k] = v
    return merged


# --- Enterprise enrichment ---

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
    "clock_max": 3, "clock_min": 2, "modem": 2, "npu": 2,
    "wifi": 2, "bluetooth": 2, "memory_clock": 2, "memory_bus": 2,
    "display_max": 2, "camera_max": 2, "charging": 2,
    "cluster_config": 2, "video_decode": 1, "storage_type": 1,
}

VENDOR_KNOWLEDGE = {
    "Qualcomm": {
        "architecture": "ARMv8",
        "process_map": {
            "sm8750": 3, "sm8735": 3, "sm8675": 3, "sm8650": 4, "sm8635": 4,
            "sm8550": 4, "sm8475": 4, "sm8450": 4, "sm8350": 5, "sm8325": 5,
            "sm8250": 7, "sm8150": 7, "sm7450": 8, "sm7350": 8, "sm7325": 8,
            "sm7315": 8, "sm7275": 8, "sm7250": 8, "sm7225": 8, "sm7150": 8,
            "sm7125": 8, "sm7115": 8, "sm6450": 4, "sm6375": 6, "sm6365": 8,
            "sm6350": 8, "sm6250": 8, "sm6235": 8, "sm6225": 6, "sm6115": 11,
            "sm4350": 8, "sm4325": 8, "sm4250": 11, "sm4125": 11,
            "sdm9860": 7, "sdm985": 7, "sdm980": 7, "sdm875": 7,
            "sdm865": 7, "sdm860": 7, "sdm855": 7, "sdm850": 10,
            "sdm845": 10, "sdm840": 10, "sdm835": 10, "sdm830": 10,
            "sdm820": 14, "sdm821": 14,
            "sdm670": 10, "sdm665": 11, "sdm660": 14, "sdm650": 14,
            "sdm636": 14, "sdm632": 14, "sdm630": 14, "sdm625": 14,
            "sdm615": 28, "sdm610": 28, "sdm608": 28, "sdm600": 28,
            "sdm450": 28, "sdm439": 28, "sdm435": 28, "sdm430": 28,
            "sdm429": 28, "sdm425": 28, "sdm412": 28, "sdm410": 28,
            "msm8998": 10, "msm8996": 14, "msm8994": 20, "msm8992": 20,
            "msm8953": 14, "msm8952": 28, "msm8940": 28, "msm8937": 28,
            "msm8917": 28, "msm8909": 28,
            "qcm6490": 6, "qcm5430": 6, "qcm4290": 8, "qcm2290": 11,
            "qcs6490": 6, "qcs5430": 6, "qcs4290": 8, "qcs2290": 11,
            "qcs410": 10, "qcs404": 28, "qcs603": 28, "qcs605": 14,
        },
        "gpu_map": {
            "sm8750": "Adreno 830", "sm8735": "Adreno 830",
            "sm8675": "Adreno 830", "sm8650": "Adreno 750",
            "sm8635": "Adreno 750", "sm8550": "Adreno 740",
            "sm8475": "Adreno 730", "sm8450": "Adreno 730",
            "sm8350": "Adreno 660", "sm8325": "Adreno 660",
            "sm8250": "Adreno 650", "sm8150": "Adreno 640",
            "sm7250": "Adreno 620", "sm7225": "Adreno 619",
            "sm7150": "Adreno 618", "sm7125": "Adreno 618",
            "sm7115": "Adreno 618", "sm7350": "Adreno 619",
            "sm7325": "Adreno 619", "sm7315": "Adreno 619",
            "sm7275": "Adreno 619", "sm7450": "Adreno 620",
            "sm6350": "Adreno 619", "sm6250": "Adreno 619",
            "sm6225": "Adreno 619",             "sm6235": "Adreno 619",
            "sm6450": "Adreno 643", "sm6375": "Adreno 643",
            "sm6365": "Adreno 613", "sm6115": "Adreno 610",
            "sm4350": "Adreno 619", "sm4325": "Adreno 619",
            "sm4250": "Adreno 610", "sm4125": "Adreno 610",
            "sdm865": "Adreno 650", "sdm860": "Adreno 650",
            "sdm855": "Adreno 640", "sdm850": "Adreno 630",
            "sdm845": "Adreno 630", "sdm840": "Adreno 630",
            "sdm835": "Adreno 540", "sdm830": "Adreno 540",
            "sdm820": "Adreno 530", "sdm821": "Adreno 530",
            "sdm670": "Adreno 615", "sdm665": "Adreno 610",
            "sdm660": "Adreno 512", "sdm650": "Adreno 510",
            "sdm636": "Adreno 509", "sdm632": "Adreno 506",
            "sdm630": "Adreno 508", "sdm625": "Adreno 506",
            "sdm450": "Adreno 506", "sdm439": "Adreno 505",
            "sdm435": "Adreno 505", "sdm430": "Adreno 505",
            "sdm429": "Adreno 504", "sdm425": "Adreno 308",
            "sdm412": "Adreno 306", "sdm410": "Adreno 306",
            "msm8998": "Adreno 540", "msm8996": "Adreno 530",
            "msm8994": "Adreno 430", "msm8992": "Adreno 418",
            "msm8953": "Adreno 506", "qcm6490": "Adreno 643",
        },
    },
    "MediaTek": {
        "architecture": "ARMv8",
        "process_map": {
            "mt6991": 3, "mt6989": 3, "mt6985": 4, "mt6983": 4,
            "mt6899": 3, "mt6897": 4, "mt6895": 6, "mt6893": 6, "mt6891": 6,
            "mt6889": 7, "mt6885": 7, "mt6883": 7, "mt6881": 7,
            "mt6879": 6, "mt6877": 6, "mt6875": 6, "mt6873": 6,
            "mt6855": 6, "mt6853": 7, "mt6835": 6, "mt6833": 7,
            "mt6797": 20, "mt6795": 20,
            "mt6789": 6, "mt6785": 12, "mt6781": 6,
            "mt6779": 12, "mt6771": 12, "mt6768": 12, "mt6765": 12,
            "mt6757": 20, "mt6755": 28, "mt6753": 28, "mt6752": 28, "mt6750": 28,
            "mt6739": 28, "mt6737": 28, "mt6735": 28,
        },
        "gpu_map": {
            "mt6991": "Immortalis-G925", "mt6989": "Immortalis-G720",
            "mt6985": "Immortalis-G715", "mt6983": "Mali-G710",
            "mt6899": "Immortalis-G925", "mt6897": "Mali-G720",
            "mt6895": "Mali-G710", "mt6893": "Mali-G77",
            "mt6889": "Mali-G77", "mt6885": "Mali-G77",
            "mt6883": "Mali-G57", "mt6879": "Mali-G68",
            "mt6877": "Mali-G68", "mt6875": "Mali-G57",
            "mt6855": "Mali-G57", "mt6853": "Mali-G57",
            "mt6835": "Mali-G57", "mt6833": "Mali-G57",
            "mt6789": "Mali-G68", "mt6785": "Mali-G76",
            "mt6781": "Mali-G68", "mt6779": "Mali-G76",
            "mt6771": "Mali-G72",
        },
    },
    "Apple": {"architecture": "ARMv8"},
    "Samsung": {
        "architecture": "ARMv8",
        "process_map": {
            "exynos 2200": 4, "exynos 2100": 5, "exynos 990": 7,
            "exynos 9825": 7, "exynos 9820": 8, "exynos 9810": 10,
            "exynos 8895": 10, "exynos 8890": 14, "exynos 7420": 14,
            "exynos 5433": 20, "exynos 5422": 28, "exynos 5410": 28,
            "exynos 9611": 10, "exynos 9610": 10, "exynos 9609": 10,
            "exynos 7885": 14, "exynos 7872": 14,
        },
        "gpu_map": {
            "exynos 2200": "Xclipse 920", "exynos 2100": "Mali-G78",
            "exynos 990": "Mali-G77", "exynos 9825": "Mali-G76",
            "exynos 9820": "Mali-G76", "exynos 9810": "Mali-G72",
            "exynos 8895": "Mali-G71", "exynos 8890": "Mali-T880",
            "exynos 7420": "Mali-T760", "exynos 9611": "Mali-G72",
            "exynos 9610": "Mali-G72", "exynos 7885": "Mali-G71",
        },
    },
    "HiSilicon": {
        "architecture": "ARMv8",
        "process_map": {
            "kirin 9000": 5, "kirin 9000e": 5, "kirin 990": 7,
            "kirin 990 5g": 7, "kirin 980": 7, "kirin 970": 10,
            "kirin 960": 16, "kirin 955": 16, "kirin 950": 16,
            "kirin 935": 28, "kirin 930": 28, "kirin 920": 28,
            "kirin 710": 12, "kirin 810": 7, "kirin 820": 7,
            "kirin 985": 7, "kirin 990e": 7,
        },
        "gpu_map": {
            "kirin 9000": "Mali-G78", "kirin 9000e": "Mali-G78",
            "kirin 990": "Mali-G76", "kirin 990 5g": "Mali-G76",
            "kirin 980": "Mali-G76", "kirin 970": "Mali-G72",
            "kirin 960": "Mali-G71", "kirin 955": "Mali-T880",
            "kirin 950": "Mali-T880", "kirin 710": "Mali-G51",
            "kirin 810": "Mali-G52", "kirin 820": "Mali-G57",
            "kirin 985": "Mali-G77",
        },
    },
    "Google": {"architecture": "ARMv8"},
    "Rockchip": {"architecture": "ARMv8"},
    "Allwinner": {"architecture": "ARMv8"},
    "Amlogic": {"architecture": "ARMv8"},
}


def _has(chip: dict, field: str) -> bool:
    v = chip.get(field)
    return v is not None and v != "" and v != [] and v != 0 and v != 0.0


MEMORY_CLOCK_FROM_TYPE = {
    "LPDDR5X": 4266,
    "LPDDR5T": 4800,
    "LPDDR5": 3200,
    "LPDDR4X": 2133,
    "LPDDR4": 1600,
    "LPDDR3": 800,
    "DDR5": 4800,
    "DDR4": 2400,
    "DDR3": 1333,
}


def enrich_one(chip: dict) -> dict:
    if not chip.get("model"):
        chip["model"] = chip.get("name", chip.get("id", "unknown"))
    vk = VENDOR_KNOWLEDGE.get(chip.get("vendor", ""), {})
    model_upper = chip.get("model", "").upper()
    # Infer memory_clock from memory_type
    if not chip.get("memory_clock") and chip.get("memory_type"):
        for mtype, clock in MEMORY_CLOCK_FROM_TYPE.items():
            if mtype in chip["memory_type"].upper():
                chip["memory_clock"] = clock
                break
    # Infer memory_bus from brand/architecture
    if not chip.get("memory_bus"):
        if chip.get("memory_type") in ("LPDDR5X", "LPDDR5"):
            chip["memory_bus"] = 64
        elif chip.get("memory_type") in ("LPDDR4X", "LPDDR4"):
            chip["memory_bus"] = 64
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
        for key, alist in {"SM8250": ["Kona"], "SM8350": ["Lahaina"], "SM8450": ["Waipio"], "SM8475": ["Waipio"], "SM8550": ["Kalama"], "SM8650": ["Pineapple"], "SM8750": ["Pineapple"]}.items():
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
    return chip


def enrich_all(chips: list[dict]) -> list[dict]:
    return [enrich_one(c) for c in chips]
