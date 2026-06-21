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
    added = updated = 0
    for chip in chips:
        cid = chip["id"]
        if cid in existing:
            existing[cid].update(chip)
            updated += 1
        else:
            existing[cid] = chip
            added += 1
    output = sorted(existing.values(), key=lambda x: (x.get("year", 9999), x["name"]))
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
    "clock_max": 3, "modem": 2, "npu": 2, "wifi": 2, "bluetooth": 2,
    "display_max": 2, "camera_max": 2,
}

VENDOR_KNOWLEDGE = {
    "Qualcomm": {"architecture": "ARMv8",
        "process_map": {"sm8750": 3, "sm8650": 4, "sm8550": 4, "sm8475": 4, "sm8450": 4, "sm8350": 5, "sm8250": 7, "sm8150": 7, "sm7250": 8, "sm7150": 8, "sm6350": 8, "sdm845": 10, "sdm835": 10, "sdm820": 14, "sdm660": 14, "sdm636": 14, "sdm632": 14, "sdm630": 14, "sdm625": 14, "msm8998": 10, "msm8996": 14, "msm8994": 20, "msm8992": 20, "msm8940": 28, "msm8937": 28, "msm8917": 28},
        "gpu_map": {"sm8750": "Adreno 830", "sm8650": "Adreno 750", "sm8550": "Adreno 740", "sm8475": "Adreno 730", "sm8450": "Adreno 730", "sm8350": "Adreno 660", "sm8250": "Adreno 650", "sm8150": "Adreno 640", "sm7250": "Adreno 620", "sm7150": "Adreno 618}},
    "MediaTek": {"architecture": "ARMv8", "process_map": {"mt6983": 4, "mt6985": 4, "mt6991": 4, "mt6893": 6, "mt6895": 6, "mt6877": 6, "mt6879": 6, "mt6833": 7, "mt6853": 7, "mt6785": 12, "mt6779": 12}},
    "Apple": {"architecture": "ARMv8"},
    "Samsung": {"architecture": "ARMv8"},
    "HiSilicon": {"architecture": "ARMv8"},
    "Google": {"architecture": "ARMv8"},
    "Rockchip": {"architecture": "ARMv8"},
    "Allwinner": {"architecture": "ARMv8"},
    "Amlogic": {"architecture": "ARMv8"},
}


def _has(chip: dict, field: str) -> bool:
    v = chip.get(field)
    return v is not None and v != "" and v != [] and v != 0 and v != 0.0


def enrich_one(chip: dict) -> dict:
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
