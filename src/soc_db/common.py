"""Shared utilities for SoC scrapers."""

import hashlib
import json
import logging
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
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
        data: str = resp.read().decode("utf-8")
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
    text = re.sub(r"\[\s*\w+\s*\]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s*\(now\s+[^)]*?\)", "", text)
    return text or None


def slug(name: str, model: str = "") -> str:
    s = name.lower().replace("+", "p").replace("®", "").replace("-", "_")
    s = re.sub(r"[^a-z0-9_ ]", "", s)
    parts = [p for p in s.split() if p]
    skip = {"with", "and", "the", "for", "integrated", "support", "using", "based", "cores", "ghz", "mhz", "kryo", "cortex"}
    parts = [p for p in parts if p not in skip]
    base = "_".join(parts[:6]) if parts else "chip"
    if model:
        m = re.sub(r"[^a-z0-9]", "", model.lower()).strip()
        if m and m not in base:
            base = f"{base}_{m}"
    base = re.sub(r"_+", "_", base).strip("_")
    return base or "unknown"


def _match_existing(chip: dict[str, Any], existing: dict[str, Any]) -> str | None:
    cid: str = chip.get("id", "")
    if cid in existing:
        return cid
    model: str = chip.get("model", "").strip().upper()
    if model:
        for eid, ec in existing.items():
            ec_model: str = ec.get("model", "").strip().upper()
            if ec_model == model:
                return eid
    name: str = chip.get("name", "").lower().strip()
    if name:
        for eid, ec in existing.items():
            ec_name: str = ec.get("name", "").lower().strip()
            if ec_name == name:
                return eid
    return None


def write_vendor_file(vendor: str, chips: list[dict[str, Any]]) -> None:
    vfile = VENDOR_FILES.get(vendor)
    if not vfile:
        logger.warning("Unknown vendor: %s", vendor)
        return
    fpath = DATA_DIR / vfile
    existing = {}
    if fpath.exists():
        try:
            for c in json.loads(fpath.read_text("utf-8")):
                existing[c["id"]] = c
        except json.JSONDecodeError:
            pass
    matched_ids = set()
    added = updated = removed = 0
    for chip in chips:
        match_id = _match_existing(chip, existing)
        if match_id:
            matched_ids.add(match_id)
            old = existing[match_id]
            for k in ("name", "model"):
                if chip.get(k) and chip[k] != old.get(k):
                    old[k] = chip[k]
            new_id = slug(old.get("name", ""), old.get("model", ""))
            if new_id != match_id and new_id not in existing:
                old["id"] = new_id
                existing[new_id] = old
                del existing[match_id]
                matched_ids.remove(match_id)
                matched_ids.add(new_id)
                match_id = new_id
            for k, v in chip.items():
                if k in ("name", "model"):
                    continue
                if (k not in old or old[k] in (None, "", [], 0, 0.0)) and v not in (None, "", [], 0, 0.0):
                    old[k] = v
            updated += 1
        else:
            cid = chip["id"]
            existing[cid] = dict(chip)
            matched_ids.add(cid)
            added += 1
    stale = set()
    for eid, ec in existing.items():
        if eid not in matched_ids and (ec.get("completeness", 1) < 0.28 or ec.get("name", "").lower().startswith(("mali ", "adreno ", "powervr "))):
            stale.add(eid)
    matched_models: dict[str, list[str]] = defaultdict(list)
    for eid in matched_ids:
        ec = existing.get(eid, {})
        m = ec.get("model", "").strip().upper()
        if m:
            matched_models[m].append(ec.get("name", "").lower())
    for eid in list(existing.keys()):
        if eid not in matched_ids:
            ec = existing[eid]
            m = ec.get("model", "").strip().upper()
            if m and m in matched_models:
                ename = ec.get("name", "").lower()
                for mname in matched_models[m]:
                    if ename and (ename in mname or mname in ename or any(w in ename and w in mname for w in ename.split() if len(w) > 2)):
                        stale.add(eid)
                        break
    for eid in stale:
        del existing[eid]
        removed += 1
    output = sorted(existing.values(), key=lambda x: (x.get("year", 9999), x["name"]))
    output = enrich_all(output)
    fpath.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", "utf-8")
    logger.info("%s: %d entries (%d new, %d updated, %d pruned)", vfile, len(output), added, updated, removed)


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
        r"\b(SM\d{3,}|SDM\d{3,}|MSM\d{3,}|APQ\d{3,}|SC\d{4}|QCS\d{3})\b",
        r"\b(MT\d{4,})\b",
        r"\b(Exynos\s*\d{4,})\b",
        r"\b(Kirin\s*\d{3,})\b",
        r"\b(GS\d{3})\b",
        r"\b(RK\d{3,})\b",
        r"\b(OMAP\d{4,})\b",
        r"\b(AM\d{3,}|DM\d{3,})\b",
        r"\b(APL\w+|T\d{4})\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).upper()
    return None


def merge_chips(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    merged = dict(a)
    for k, v in b.items():
        if v not in (None, "", 0, []):
            merged[k] = v
    return merged


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
    "name": 5,
    "vendor": 5,
    "model": 5,
    "architecture": 4,
    "cores": 4,
    "process_nm": 3,
    "gpu": 3,
    "memory_type": 2,
    "year": 3,
    "clock_max": 3,
    "clock_min": 2,
    "modem": 2,
    "npu": 2,
    "wifi": 2,
    "bluetooth": 2,
    "memory_clock": 2,
    "memory_bus": 2,
    "display_max": 2,
    "camera_max": 2,
    "charging": 2,
    "cluster_config": 2,
    "video_decode": 1,
    "storage_type": 1,
}

VENDOR_KNOWLEDGE: dict[str, dict[str, Any]] = {
    "Qualcomm": {
        "architecture": "ARMv8",
        "process_map": {
            "sm8750": 3,
            "sm8735": 3,
            "sm8675": 3,
            "sm8650": 4,
            "sm8635": 4,
            "sm8550": 4,
            "sm8475": 4,
            "sm8450": 4,
            "sm8350": 5,
            "sm8325": 5,
            "sm8250": 7,
            "sm8150": 7,
            "sm7450": 8,
            "sm7350": 8,
            "sm7325": 8,
            "sm7315": 8,
            "sm7275": 8,
            "sm7250": 8,
            "sm7225": 8,
            "sm7150": 8,
            "sm7125": 8,
            "sm7115": 8,
            "sm6450": 4,
            "sm6375": 6,
            "sm6365": 8,
            "sm6350": 8,
            "sm6250": 8,
            "sm6235": 8,
            "sm6225": 6,
            "sm6115": 11,
            "sm4350": 8,
            "sm4325": 8,
            "sm4250": 11,
            "sm4125": 11,
            "sdm9860": 7,
            "sdm985": 7,
            "sdm980": 7,
            "sdm875": 7,
            "sdm865": 7,
            "sdm860": 7,
            "sdm855": 7,
            "sdm850": 10,
            "sdm845": 10,
            "sdm840": 10,
            "sdm835": 10,
            "sdm830": 10,
            "sdm820": 14,
            "sdm821": 14,
            "sdm670": 10,
            "sdm665": 11,
            "sdm660": 14,
            "sdm650": 14,
            "sdm636": 14,
            "sdm632": 14,
            "sdm630": 14,
            "sdm625": 14,
            "sdm615": 28,
            "sdm610": 28,
            "sdm608": 28,
            "sdm600": 28,
            "sdm450": 28,
            "sdm439": 28,
            "sdm435": 28,
            "sdm430": 28,
            "sdm429": 28,
            "sdm425": 28,
            "sdm412": 28,
            "sdm410": 28,
            "msm8998": 10,
            "msm8996": 14,
            "msm8994": 20,
            "msm8992": 20,
            "msm8953": 14,
            "msm8952": 28,
            "msm8940": 28,
            "msm8937": 28,
            "msm8917": 28,
            "msm8909": 28,
            "qcm6490": 6,
            "qcm5430": 6,
            "qcm4290": 8,
            "qcm2290": 11,
            "qcs6490": 6,
            "qcs5430": 6,
            "qcs4290": 8,
            "qcs2290": 11,
            "qcs410": 10,
            "qcs404": 28,
            "qcs603": 28,
            "qcs605": 14,
        },
        "gpu_map": {
            "sm8750": "Adreno 830",
            "sm8735": "Adreno 830",
            "sm8675": "Adreno 830",
            "sm8650": "Adreno 750",
            "sm8635": "Adreno 750",
            "sm8550": "Adreno 740",
            "sm8475": "Adreno 730",
            "sm8450": "Adreno 730",
            "sm8350": "Adreno 660",
            "sm8325": "Adreno 660",
            "sm8250": "Adreno 650",
            "sm8150": "Adreno 640",
            "sm7250": "Adreno 620",
            "sm7225": "Adreno 619",
            "sm7150": "Adreno 618",
            "sm7125": "Adreno 618",
            "sm7115": "Adreno 618",
            "sm7350": "Adreno 619",
            "sm7325": "Adreno 619",
            "sm7315": "Adreno 619",
            "sm7275": "Adreno 619",
            "sm7450": "Adreno 620",
            "sm6350": "Adreno 619",
            "sm6250": "Adreno 619",
            "sm6225": "Adreno 619",
            "sm6235": "Adreno 619",
            "sm6450": "Adreno 643",
            "sm6375": "Adreno 643",
            "sm6365": "Adreno 613",
            "sm6115": "Adreno 610",
            "sm4350": "Adreno 619",
            "sm4325": "Adreno 619",
            "sm4250": "Adreno 610",
            "sm4125": "Adreno 610",
            "sdm865": "Adreno 650",
            "sdm860": "Adreno 650",
            "sdm855": "Adreno 640",
            "sdm850": "Adreno 630",
            "sdm845": "Adreno 630",
            "sdm840": "Adreno 630",
            "sdm835": "Adreno 540",
            "sdm830": "Adreno 540",
            "sdm820": "Adreno 530",
            "sdm821": "Adreno 530",
            "sdm670": "Adreno 615",
            "sdm665": "Adreno 610",
            "sdm660": "Adreno 512",
            "sdm650": "Adreno 510",
            "sdm636": "Adreno 509",
            "sdm632": "Adreno 506",
            "sdm630": "Adreno 508",
            "sdm625": "Adreno 506",
            "sdm450": "Adreno 506",
            "sdm439": "Adreno 505",
            "sdm435": "Adreno 505",
            "sdm430": "Adreno 505",
            "sdm429": "Adreno 504",
            "sdm425": "Adreno 308",
            "sdm412": "Adreno 306",
            "sdm410": "Adreno 306",
            "msm8998": "Adreno 540",
            "msm8996": "Adreno 530",
            "msm8994": "Adreno 430",
            "msm8992": "Adreno 418",
            "msm8953": "Adreno 506",
            "qcm6490": "Adreno 643",
        },
    },
    "MediaTek": {
        "architecture": "ARMv8",
        "process_map": {
            "mt6991": 3,
            "mt6989": 3,
            "mt6985": 4,
            "mt6983": 4,
            "mt6899": 3,
            "mt6897": 4,
            "mt6895": 6,
            "mt6893": 6,
            "mt6891": 6,
            "mt6889": 7,
            "mt6885": 7,
            "mt6883": 7,
            "mt6881": 7,
            "mt6879": 6,
            "mt6877": 6,
            "mt6875": 6,
            "mt6873": 6,
            "mt6855": 6,
            "mt6853": 7,
            "mt6835": 6,
            "mt6833": 7,
            "mt6797": 20,
            "mt6795": 20,
            "mt6789": 6,
            "mt6785": 12,
            "mt6781": 6,
            "mt6779": 12,
            "mt6771": 12,
            "mt6768": 12,
            "mt6765": 12,
            "mt6757": 20,
            "mt6755": 28,
            "mt6753": 28,
            "mt6752": 28,
            "mt6750": 28,
            "mt6739": 28,
            "mt6737": 28,
            "mt6735": 28,
        },
        "gpu_map": {
            "mt6991": "Immortalis-G925",
            "mt6989": "Immortalis-G720",
            "mt6985": "Immortalis-G715",
            "mt6983": "Mali-G710",
            "mt6899": "Immortalis-G925",
            "mt6897": "Mali-G720",
            "mt6895": "Mali-G710",
            "mt6893": "Mali-G77",
            "mt6889": "Mali-G77",
            "mt6885": "Mali-G77",
            "mt6883": "Mali-G57",
            "mt6879": "Mali-G68",
            "mt6877": "Mali-G68",
            "mt6875": "Mali-G57",
            "mt6855": "Mali-G57",
            "mt6853": "Mali-G57",
            "mt6835": "Mali-G57",
            "mt6833": "Mali-G57",
            "mt6789": "Mali-G68",
            "mt6785": "Mali-G76",
            "mt6781": "Mali-G68",
            "mt6779": "Mali-G76",
            "mt6771": "Mali-G72",
        },
    },
    "Apple": {"architecture": "ARMv8"},
    "Samsung": {
        "architecture": "ARMv8",
        "process_map": {
            "exynos 2200": 4,
            "exynos 2100": 5,
            "exynos 990": 7,
            "exynos 9825": 7,
            "exynos 9820": 8,
            "exynos 9810": 10,
            "exynos 8895": 10,
            "exynos 8890": 14,
            "exynos 7420": 14,
            "exynos 5433": 20,
            "exynos 5422": 28,
            "exynos 5410": 28,
            "exynos 9611": 10,
            "exynos 9610": 10,
            "exynos 9609": 10,
            "exynos 7885": 14,
            "exynos 7872": 14,
        },
        "gpu_map": {
            "exynos 2200": "Xclipse 920",
            "exynos 2100": "Mali-G78",
            "exynos 990": "Mali-G77",
            "exynos 9825": "Mali-G76",
            "exynos 9820": "Mali-G76",
            "exynos 9810": "Mali-G72",
            "exynos 8895": "Mali-G71",
            "exynos 8890": "Mali-T880",
            "exynos 7420": "Mali-T760",
            "exynos 9611": "Mali-G72",
            "exynos 9610": "Mali-G72",
            "exynos 7885": "Mali-G71",
        },
    },
    "HiSilicon": {
        "architecture": "ARMv8",
        "process_map": {
            "kirin 9000": 5,
            "kirin 9000e": 5,
            "kirin 990": 7,
            "kirin 990 5g": 7,
            "kirin 980": 7,
            "kirin 970": 10,
            "kirin 960": 16,
            "kirin 955": 16,
            "kirin 950": 16,
            "kirin 935": 28,
            "kirin 930": 28,
            "kirin 920": 28,
            "kirin 710": 12,
            "kirin 810": 7,
            "kirin 820": 7,
            "kirin 985": 7,
            "kirin 990e": 7,
        },
        "gpu_map": {
            "kirin 9000": "Mali-G78",
            "kirin 9000e": "Mali-G78",
            "kirin 990": "Mali-G76",
            "kirin 990 5g": "Mali-G76",
            "kirin 980": "Mali-G76",
            "kirin 970": "Mali-G72",
            "kirin 960": "Mali-G71",
            "kirin 955": "Mali-T880",
            "kirin 950": "Mali-T880",
            "kirin 710": "Mali-G51",
            "kirin 810": "Mali-G52",
            "kirin 820": "Mali-G57",
            "kirin 985": "Mali-G77",
        },
    },
    "Google": {"architecture": "ARMv8"},
    "Rockchip": {"architecture": "ARMv8"},
    "Allwinner": {"architecture": "ARMv8"},
    "Amlogic": {"architecture": "ARMv8"},
}


def _has(chip: dict[str, Any], field: str) -> bool:
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


def enrich_one(chip: dict[str, Any]) -> dict[str, Any]:
    ann = re.compile(r"\s*\(now\s+[^)]*?\)")
    for k in ("name", "model"):
        if chip.get(k):
            cleaned = ann.sub("", chip[k]).strip()
            if cleaned != chip[k]:
                chip[k] = cleaned
    if not chip.get("model"):
        name = chip.get("name", "")
        if re.match(r"^[A-Za-z0-9][A-Za-z0-9/\-.\s]{1,30}$", name) and re.search(r"\d", name):
            chip["model"] = name
        else:
            chip["model"] = chip.get("id", "unknown")
    vk = VENDOR_KNOWLEDGE.get(chip.get("vendor", ""), {})
    model_upper = chip.get("model", "").upper()
    if not chip.get("memory_clock") and chip.get("memory_type"):
        for mtype, clock in MEMORY_CLOCK_FROM_TYPE.items():
            if mtype in chip["memory_type"].upper():
                chip["memory_clock"] = clock
                break
    if not chip.get("memory_bus") and chip.get("memory_type") in ("LPDDR5X", "LPDDR5", "LPDDR4X", "LPDDR4"):
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
    y_chk = chip.get("year")
    if y_chk and (y_chk < 2003 or y_chk > 2026):
        chip["year"] = None
    year = chip.get("year")
    if not year:
        for f_text in (chip.get("model", "").upper(), chip.get("name", "").upper()):
            if not f_text:
                continue
            m = re.search(r"MT(\d{4})", f_text)
            if m:
                mt_val = int(m.group(1))
                if mt_val >= 9900:
                    year = 2025
                elif mt_val >= 9800:
                    year = 2024
                elif mt_val >= 9200:
                    year = 2023
                elif mt_val >= 8700:
                    year = 2022
                elif mt_val >= 8300:
                    year = 2021
                elif mt_val >= 8000:
                    year = 2020
                elif mt_val >= 7900:
                    year = 2019
                elif mt_val >= 7500:
                    year = 2018
                elif mt_val >= 7000:
                    year = 2017
                elif mt_val >= 6500:
                    year = 2016
                elif mt_val >= 6000:
                    year = 2015
                elif mt_val >= 5000:
                    year = 2014
                else:
                    year = 2013
                break
            m = re.search(r"(?:DIMENSITY|HELIO)\s*(\d{3,4})", f_text)
            if m:
                d = int(m.group(1))
                if d >= 9400:
                    year = 2025
                elif d >= 9300 or d >= 9200:
                    year = 2024
                elif d >= 9000:
                    year = 2023
                elif d >= 8400 or d >= 8300:
                    year = 2024
                elif d >= 8200:
                    year = 2023
                elif d >= 8100 or d >= 8000:
                    year = 2022
                elif d >= 7200:
                    year = 2023
                elif d >= 7000 or d >= 6000:
                    year = 2022
                elif d >= 1200 or d >= 1100:
                    year = 2021
                elif d >= 1000:
                    year = 2020
                elif d >= 900:
                    year = 2019
                elif d >= 800:
                    year = 2018
                elif d >= 700:
                    year = 2017
                elif d >= 600:
                    year = 2016
                elif d >= 500:
                    year = 2015
                else:
                    year = 2014
                break
            m = re.search(r"KIRIN\s*(\d{3,4})", f_text)
            if m:
                kirin = int(m.group(1))
                if kirin >= 9010:
                    year = 2024
                elif kirin >= 9000:
                    year = 2020
                elif kirin >= 8000:
                    year = 2024
                elif kirin >= 990:
                    year = 2019
                elif kirin >= 980:
                    year = 2018
                elif kirin >= 970:
                    year = 2017
                elif kirin >= 960:
                    year = 2016
                elif kirin >= 950 or kirin >= 930:
                    year = 2015
                elif kirin >= 920 or kirin >= 900:
                    year = 2014
                elif kirin >= 800 or kirin >= 700:
                    year = 2018
                elif kirin >= 600:
                    year = 2015
                else:
                    year = 2013
                break
            m = re.search(r"(?:SM|SDM)(\d{3,4})", f_text)
            if m:
                sm = int(m.group(1))
                if sm >= 8750:
                    year = 2025
                elif sm >= 8650:
                    year = 2024
                elif sm >= 8550:
                    year = 2023
                elif sm >= 8450:
                    year = 2022
                elif sm >= 8350:
                    year = 2021
                elif sm >= 8250:
                    year = 2020
                elif sm >= 8150:
                    year = 2019
                elif sm >= 8000:
                    year = 2018
                elif sm >= 7000:
                    year = 2017
                elif sm >= 6000:
                    year = 2016
                elif sm >= 5000:
                    year = 2015
                elif sm >= 4000:
                    year = 2014
                elif sm >= 3000:
                    year = 2013
                elif sm >= 2000:
                    year = 2012
                else:
                    year = 2011
                break
            m = re.search(r"(?:MSM|APQ)(\d{4})", f_text)
            if m:
                msm = int(m.group(1))
                if msm >= 9000:
                    year = 2018
                elif msm >= 8998:
                    year = 2017
                elif msm >= 8996:
                    year = 2016
                elif msm >= 8994:
                    year = 2015
                elif msm >= 8974:
                    year = 2013
                elif msm >= 8960:
                    year = 2012
                elif msm >= 8900:
                    year = 2011
                elif msm >= 8200:
                    year = 2010
                elif msm >= 7600:
                    year = 2009
                elif msm >= 7200:
                    year = 2008
                else:
                    year = 2007
                break
            m = re.search(r"EXYNOS", f_text)
            if m:
                all_nums = re.findall(r"(\d{4})", f_text[m.end() :])
                if all_nums:
                    ex = int(all_nums[0])
                    if ex >= 2500:
                        year = 2025
                    elif ex >= 2400:
                        year = 2024
                    elif ex >= 2200:
                        year = 2022
                    elif ex >= 2100:
                        year = 2021
                    elif ex >= 2000:
                        year = 2020
                    elif ex >= 1580:
                        year = 2025
                    elif ex >= 1480:
                        year = 2024
                    elif ex >= 1380:
                        year = 2023
                    elif ex >= 1280:
                        year = 2022
                    elif ex >= 1080:
                        year = 2020
                    elif ex >= 9900:
                        year = 2024
                    elif ex >= 9800:
                        year = 2023
                    elif ex >= 9700:
                        year = 2022
                    elif ex >= 9600:
                        year = 2021
                    elif ex >= 9500:
                        year = 2020
                    elif ex >= 9000:
                        year = 2016
                    elif ex >= 8000:
                        year = 2015
                    elif ex >= 7000:
                        year = 2014
                    elif ex >= 5000:
                        year = 2012
                    elif ex >= 4000:
                        year = 2011
                    elif ex >= 3000:
                        year = 2010
                    elif ex >= 2000:
                        year = 2007
                    else:
                        year = 2005
                    break
                all_3 = re.findall(r"(\d{3})", f_text[m.end() :])
                if all_3:
                    ex3 = int(all_3[0])
                    year = 2020 if ex3 >= 990 or ex3 >= 980 or ex3 >= 880 or ex3 >= 850 else 2015
                    break
                m_w = re.search(r"EXYNOS\s+W(\d+)", f_text)
                if m_w:
                    w = int(m_w.group(1))
                    if w >= 1000 or w >= 930:
                        year = 2023
                    elif w >= 920:
                        year = 2021
                    else:
                        year = 2020
                    break
                m_a = re.search(r"EXYNOS\s+AUTO\s*V(\d+)", f_text)
                if m_a:
                    av = int(m_a.group(1))
                    if av >= 920:
                        year = 2023
                    elif av >= 90:
                        year = 2020
                    elif av >= 70:
                        year = 2019
                    elif av >= 9:
                        year = 2020
                    else:
                        year = 2018
                    break
            m = re.search(r"SNAPDRAGON\s*X\s*(?:ELITE|PLUS)", f_text)
            if m and not re.search(r"X\s*2", f_text):
                year = 2024
                break
            m = re.search(r"SNAPDRAGON\s*X\s*2", f_text)
            if m:
                year = 2025
                break
            m = re.search(r"SNAPDRAGON\s*(\d+)\s*GEN\s*(\d+)", f_text)
            if m:
                series = int(m.group(1))
                gen = int(m.group(2))
                year = 2021 + gen if series >= 8 else 2020 + gen
                break
            m = re.search(r"RK(\d{4})", f_text)
            if m:
                rk = int(m.group(1))
                year = 2008 + (rk - 2000) // 200
                break
            m = re.search(r"\b([AM])(\d+)\b", f_text)
            if m:
                prefix = m.group(1)
                num = int(m.group(2))
                if prefix == "A":
                    if num >= 18:
                        year = 2025
                    elif num == 17:
                        year = 2024
                    elif num == 16:
                        year = 2023
                    elif num == 15:
                        year = 2022
                    elif num == 14:
                        year = 2020
                    elif num == 13:
                        year = 2019
                    elif num == 12:
                        year = 2018
                    elif num == 11:
                        year = 2017
                    elif num == 10:
                        year = 2016
                    elif num == 9:
                        year = 2015
                    elif num == 8:
                        year = 2014
                    elif num == 7:
                        year = 2013
                    else:
                        year = 2011 + num - 5
                elif prefix == "M":
                    if num >= 4:
                        year = 2025
                    elif num == 3:
                        year = 2023
                    elif num == 2:
                        year = 2022
                    elif num == 1:
                        year = 2020
                break
            m = re.search(r"TEGRA\s*(\d+)", f_text)
            if m:
                t = int(m.group(1))
                year = 2008 + t
                break
            m = re.search(r"\b(T[01]\d{2}|T20[0-9])\b", f_text)
            if m:
                year = 2008 + int(m.group(1)[:2])
                break
            x1_match = re.search(r"(?:TE|T)\d{3}X1", f_text)
            if x1_match:
                year = 2015
                break
            m = re.search(r"ATOM\s*(\w+)", f_text)
            if m:
                atom_name = m.group(1).upper()
                if re.search(r"Z\d{3,}", atom_name) or re.search(r"N\d{3,}", atom_name) or re.search(r"x\d{2,}", atom_name):
                    pass
            m = re.search(r"\b[xzzn]\d+", f_text, re.IGNORECASE)
            if m:
                if re.search(r"[xX]\d", f_text):
                    year = 2015
                elif re.search(r"[Zz]\d{4}", f_text):
                    year = 2014
            m = re.search(r"\bG(\d+)\s*GEN\s*(\d+)", f_text)
            if m:
                g_series = int(m.group(1))
                g_gen = int(m.group(2))
                if g_series == 1:
                    year = 2020 + g_gen
                elif g_series == 3:
                    year = 2022 + g_gen - 1 if g_gen >= 3 else 2021
                else:
                    year = 2020 + g_gen + (g_series > 1)
                break
            m = re.search(r"\bG(\d+)X\s*GEN\s*(\d+)", f_text)
            if m:
                g_gen = int(m.group(2))
                year = 2020 + g_gen if g_gen == 1 else 2021 + g_gen
                break
            m = re.search(r"MICROSOFT\s+SQ(\d+)", f_text)
            if m:
                sq = int(m.group(1))
                year = 2018 + sq
                break
            m = re.search(r"\bQCS(\d{3})\b", f_text)
            if m:
                qcs = int(m.group(1))
                year = 2015 + (qcs // 100)
                break
            m = re.search(r"\bSC(\d{4})", f_text)
            if m:
                sc = int(m.group(1))
                if sc >= 8380:
                    year = 2022
                elif sc >= 8280:
                    year = 2021
                elif sc >= 8180:
                    year = 2019
                elif sc >= 7280:
                    year = 2021
                elif sc >= 7180:
                    year = 2020
                else:
                    year = 2018
                break
            m = re.search(r"\bSA(\d{4})P?\b", f_text)
            if m:
                sa = int(m.group(1))
                if sa >= 8255:
                    year = 2024
                elif sa >= 8295:
                    year = 2021
                elif sa >= 8195 or sa >= 8155 or sa >= 6155:
                    year = 2019
                else:
                    year = 2018
                break
            m = re.search(r"WEAR\s*(\d+)", f_text)
            if m:
                wear = int(m.group(1))
                year = 2016 + (wear - 2100) // 500 if wear >= 2100 else 2018 + (wear - 2500) // 500
                year = 2020
                break
            m = re.search(r"W\d+\+?\s*GEN\s*(\d+)", f_text)
            if m:
                w_gen = int(m.group(1))
                year = 2021 + w_gen
                break
            m = re.search(r"XR(\d+)\s*(?:GEN\s*(\d+))?", f_text)
            if m:
                xr = int(m.group(1))
                xr_gen = m.group(2)
                if xr_gen:
                    year = 2020 + int(xr_gen)
                elif xr >= 2:
                    year = 2019
                else:
                    year = 2018
                break
            m = re.search(r"SNAPDRAGON\s+(\d{3})(\d?)", f_text)
            if m:
                sd_prefix = int(m.group(1))
                sd_suffix = m.group(2)
                sd_full = int(f"{sd_prefix}{sd_suffix or '0'}")
                if sd_full >= 855:
                    year = 2019
                elif sd_full >= 845:
                    year = 2018
                elif sd_full >= 835:
                    year = 2017
                elif sd_full >= 820:
                    year = 2016
                elif sd_full >= 810:
                    year = 2015
                elif sd_full >= 800 or sd_full >= 600:
                    year = 2014
                elif sd_full >= 400:
                    year = 2013
                else:
                    year = 2012
                break
            m = re.search(r"\bQSD(\d{4})\b", f_text)
            if m:
                year = 2009
                break
            m = re.search(r"\bSW(\d{4})\b", f_text)
            if m:
                sw = int(m.group(1))
                year = 2015 + (sw // 1000)
                break
            m = re.search(r"\bCE(\d{4})\b", f_text)
            if m:
                ce = int(m.group(1))
                year = 2008 + (ce // 1000)
                break
            m = re.search(r"\bOMAP(\d)\d{3}\b", f_text)
            if m:
                omap_gen = int(m.group(1))
                year = 2004 + omap_gen * 2
                break
            m = re.search(r"\b([AHFR])(\d{2,3})", f_text)
            if m:
                aw_prefix = m.group(1)
                aw_num = int(m.group(2))
                if aw_prefix == "F":
                    year = 2015 if aw_num >= 100 else 2013
                elif aw_prefix == "R":
                    year = 2012 + (aw_num // 10) if aw_num >= 40 else 2014
                elif aw_prefix == "H":
                    if aw_num >= 700:
                        year = 2018 + (aw_num - 700) // 2
                    elif aw_num >= 600:
                        year = 2015 + (aw_num - 600) // 2
                    elif aw_num >= 500:
                        year = 2017 + (aw_num - 500) // 2
                    elif aw_num >= 300:
                        year = 2014 + (aw_num - 300) // 2
                    else:
                        year = 2013
                elif aw_prefix == "A":
                    if aw_num >= 100:
                        year = 2014 + (aw_num - 100) // 10
                    elif aw_num >= 80:
                        year = 2014
                    elif aw_num >= 40:
                        year = 2015
                    elif aw_num >= 31:
                        year = 2013
                    elif aw_num >= 20 or aw_num >= 13:
                        year = 2012
                    elif aw_num >= 10:
                        year = 2011
                    else:
                        year = 2011 + aw_num // 5
                break
            m = re.search(r"\bS(\d{3})", f_text)
            if m:
                aml = int(m.group(1))
                if aml >= 928:
                    year = 2020
                elif aml >= 922:
                    year = 2019
                elif aml >= 912 or aml >= 905:
                    year = 2016
                elif aml >= 812:
                    year = 2015
                elif aml >= 805:
                    year = 2014
                elif aml >= 802:
                    year = 2013
                else:
                    year = 2012
                break
            if chip.get("vendor") == "Amlogic":
                m = re.search(r"\bT(\d{3})", f_text)
                if m:
                    aml_t = int(m.group(1))
                    if aml_t >= 920:
                        year = 2018
                    elif aml_t >= 960:
                        year = 2016
                    elif aml_t >= 950:
                        year = 2015
                    else:
                        year = 2014
                    break
            m = re.search(r"KOMPANIO\s*(\d+)", f_text)
            if m:
                komp = int(m.group(1))
                if komp >= 1300 or komp >= 1200 or komp >= 800:
                    year = 2022
                elif komp >= 500:
                    year = 2021
                else:
                    year = 2020
                break
            m = re.search(r"ATOM\s+([DN])(\d{4})", f_text)
            if m:
                atom_letter = m.group(1)
                atom_digits = int(m.group(2))
                year = 2010 + (atom_digits // 1000) if atom_letter == "D" else 2009 + (atom_digits // 500)
                break
            m = re.search(r"\bJZ(\d{4})\b", f_text, re.IGNORECASE)
            if m:
                jz = int(m.group(1))
                year = 2005 + (jz // 1000)
                break
            m = re.search(r"\bTHOR\b", f_text)
            if m:
                year = 2025
                break
            m = re.search(r"F1[CE](\d{3})", f_text)
            if m:
                f1 = int(m.group(1))
                year = 2014 + (f1 // 100)
                break
            m = re.search(r"AIOT\s*[Ii](\d{3})", f_text)
            if m:
                year = 2020 + (int(m.group(1)) // 100)
                break
            m = re.search(r"\bSP(\d{4})\b", f_text)
            if m:
                sp = int(m.group(1))
                year = 2010 + (sp - 9000) // 100
                break
            m = re.search(r"\bUMS(\d{4})\b", f_text)
            if m:
                ums = int(m.group(1))
                year = 2018 + ((ums - 9000) // 200)
                break
            m = re.search(r"\bK3V2", f_text)
            if m:
                year = 2012
                if "K3V2E" in f_text:
                    year = 2013
                break
            m = re.search(r"\bT(\d{2,3})", f_text)
            if m and "KIRIN" in f_text:
                kt = int(m.group(1))
                if kt >= 92:
                    year = 2025
                elif kt >= 91:
                    year = 2024
                elif kt >= 90:
                    year = 2023
                elif kt >= 80:
                    year = 2020
                break
            if year:
                break
    if year:
        chip["year"] = year
    yr = chip.get("year")
    if not chip.get("process_nm") and yr:
        proc_by_year = [
            (2024, 3),
            (2023, 4),
            (2021, 5),
            (2019, 7),
            (2017, 10),
            (2015, 14),
            (2013, 20),
            (2011, 28),
            (2009, 40),
            (0, 65),
        ]
        for yr_proc, nm in proc_by_year:
            if yr >= yr_proc:
                chip["process_nm"] = nm
                chip["process_name"] = f"{nm}nm"
                break
    yr = chip.get("year")
    if not chip.get("memory_type") and yr:
        mem_by_year = [
            (2023, "LPDDR5X"),
            (2021, "LPDDR5"),
            (2019, "LPDDR4X"),
            (2016, "LPDDR4"),
            (2014, "LPDDR3"),
            (2012, "LPDDR2"),
            (0, "LPDDR"),
        ]
        for yr_mem, mt_name in mem_by_year:
            if yr >= yr_mem:
                chip["memory_type"] = mt_name
                break
    yr = chip.get("year")
    if not chip.get("storage_type") and yr:
        st_by_year = [
            (2021, "UFS 3.1"),
            (2019, "UFS 3.0"),
            (2017, "UFS 2.1"),
            (2015, "UFS 2.0"),
            (0, "eMMC 5.0"),
        ]
        for yr_st, st_name in st_by_year:
            if yr >= yr_st:
                chip["storage_type"] = st_name
                break
    mt = chip.get("memory_type", "")
    if not chip.get("memory_clock") and mt:
        clock_map = {
            "LPDDR6": 6400,
            "LPDDR5X": 4266,
            "LPDDR5": 3200,
            "LPDDR4X": 2133,
            "LPDDR4": 1600,
            "LPDDR3": 933,
            "LPDDR2": 533,
            "LPDDR": 400,
        }
        for k, v in clock_map.items():
            if mt.startswith(k):
                chip["memory_clock"] = v
                break
    if not chip.get("memory_bus") and mt:
        if mt.startswith(("LPDDR4", "LPDDR5", "LPDDR6")):
            chip["memory_bus"] = 64
        elif mt.startswith(("LPDDR3", "LPDDR2", "LPDDR")):
            chip["memory_bus"] = 32
    if not chip.get("gpu") and chip.get("year"):
        vendor = chip.get("vendor", "")
        yr = chip["year"]
        gpu_by_vendor = {
            "Allwinner": "Mali-400 MP" if yr < 2015 else "Mali-450 MP",
            "Amlogic": "Mali-450 MP" if yr < 2017 else "Mali-G31 MP2",
            "Rockchip": "Mali-400 MP" if yr < 2014 else "Mali-T760 MP4" if yr < 2017 else "Mali-G52 MP2",
            "Nvidia": "Nvidia GPU",
            "Intel Atom": "Intel HD Graphics",
            "TI OMAP": "PowerVR SGX",
            "Ingenic": "GC400" if yr < 2014 else "GC800",
            "Actions": "Mali-400 MP",
        }
        if vendor in gpu_by_vendor:
            chip["gpu"] = gpu_by_vendor[vendor]
        elif vendor == "MediaTek":
            chip["gpu"] = "Mali GPU"
        elif vendor == "Qualcomm":
            chip["gpu"] = "Adreno GPU"
        elif vendor == "Samsung" or vendor == "HiSilicon" or vendor == "Unisoc":
            chip["gpu"] = "Mali GPU"
        elif vendor == "NXP i.MX":
            chip["gpu"] = "Vivante GC"
        elif vendor == "Xilinx":
            chip["gpu"] = "Mali GPU"
    if not chip.get("npu") and yr and yr >= 2017:
        vendor = chip.get("vendor", "")
        model_u = chip.get("model", "").upper()
        name_u = chip.get("name", "").upper()
        vk_npu = vk.get("npu_map", {})
        for key, npu_name in vk_npu.items():
            if key.upper() in model_u or key.upper() in name_u:
                chip["npu"] = npu_name
                break
        else:
            if vendor == "Apple" and chip["year"] >= 2017:
                chip["npu"] = "Neural Engine"
            elif vendor == "Qualcomm":
                if any(x in model_u for x in ("SM8", "SM7", "SDM8", "SDM7")) or any(x in model_u for x in ("SM6", "SDM6")):
                    chip["npu"] = "Hexagon NPU"
            elif vendor == "MediaTek":
                if "DIMENSITY" in model_u or "DIMENSITY" in name_u:
                    chip["npu"] = "MediaTek APU"
                elif re.search(r"MT\d{4}", model_u):
                    mt_m = re.search(r"MT(\d{4})", model_u)
                    if mt_m and int(mt_m.group(1)) >= 8000:
                        chip["npu"] = "MediaTek APU"
            elif vendor == "Samsung" and re.search(r"EXYNOS\s*(21|22|24|25)", model_u):
                chip["npu"] = "Samsung NPU"
            elif vendor == "HiSilicon" and re.search(r"KIRIN\s*(9|8|7)", model_u):
                chip["npu"] = "HiSilicon NPU"
    if not chip.get("modem") and chip.get("year"):
        vendor = chip.get("vendor", "")
        model_u = chip.get("model", "").upper()
        name_u = chip.get("name", "").upper()
        yr = chip["year"]
        if vendor == "Qualcomm":
            sm_match = re.search(r"(SM|SDM)(\d{4})", model_u)
            if sm_match:
                sm_num = int(sm_match.group(2))
                modem_map = {8750: "X80", 8650: "X75", 8550: "X70", 8450: "X65", 8350: "X60", 8250: "X55", 8150: "X50", 8000: "X24"}
                for num, modem_name in modem_map.items():
                    if sm_num >= num:
                        chip["modem"] = f"Snapdragon {modem_name} 5G"
                        break
            gen_match = re.search(r"SNAPDRAGON\s*(\d+)\s*GEN\s*(\d+)", model_u)
            if gen_match and not chip.get("modem"):
                gen_num = int(gen_match.group(2))
                if int(gen_match.group(1)) >= 8:
                    modem_by_gen = {3: "X70", 2: "X65", 1: "X60"}
                    if gen_num in modem_by_gen:
                        chip["modem"] = f"Snapdragon {modem_by_gen[gen_num]} 5G"
            if not chip.get("modem") and chip["year"] >= 2019:
                chip["modem"] = "Snapdragon 5G"
            elif not chip.get("modem") and chip["year"] >= 2013:
                chip["modem"] = "Snapdragon 4G LTE"
        elif vendor == "MediaTek":
            if re.search(r"DIMENSITY", model_u) or re.search(r"MT\d{4}", model_u):
                if chip["year"] >= 2020:
                    chip["modem"] = "MediaTek 5G"
                elif chip["year"] >= 2015:
                    chip["modem"] = "MediaTek 4G LTE"
        elif vendor == "Samsung" and re.search(r"EXYNOS", model_u):
            if chip["year"] >= 2020:
                chip["modem"] = "Exynos 5G"
            elif chip["year"] >= 2014:
                chip["modem"] = "Exynos 4G LTE"
        elif vendor == "Apple" and chip["year"] >= 2019:
            chip["modem"] = "Apple 5G"
        elif vendor == "HiSilicon" and re.search(r"KIRIN", model_u):
            if chip["year"] >= 2019:
                chip["modem"] = "Balong 5G"
            elif chip["year"] >= 2014:
                chip["modem"] = "Balong 4G LTE"
    yr = chip.get("year")
    if not chip.get("wifi") and yr:
        wifi_by_year = [
            (2025, "Wi-Fi 7"),
            (2023, "Wi-Fi 7"),
            (2021, "Wi-Fi 6E"),
            (2019, "Wi-Fi 6"),
            (2015, "Wi-Fi 5"),
            (2010, "Wi-Fi 4"),
            (2005, "Wi-Fi 3"),
            (0, "Wi-Fi 2"),
        ]
        for yr_wifi, w_name in wifi_by_year:
            if yr >= yr_wifi:
                chip["wifi"] = w_name
                break
    if not chip.get("bluetooth") and yr:
        bt_by_year = [
            (2025, "5.4"),
            (2023, "5.3"),
            (2021, "5.2"),
            (2019, "5.0"),
            (2017, "4.2"),
            (2015, "4.1"),
            (2012, "4.0"),
            (2010, "3.0"),
            (2007, "2.1"),
            (0, "2.0"),
        ]
        for yr_bt, b_name in bt_by_year:
            if yr >= yr_bt:
                chip["bluetooth"] = b_name
                break
    if not chip.get("aliases"):
        aliases = set()
        name = chip.get("name", "")
        model = chip.get("model", "")
        if name and model and model not in name:
            aliases.add(f"{name} ({model})")
        codenames = {
            "SM8250": ["Kona"],
            "SM8350": ["Lahaina"],
            "SM8450": ["Waipio"],
            "SM8475": ["Waipio"],
            "SM8550": ["Kalama"],
            "SM8650": ["Pineapple"],
            "SM8750": ["Pineapple"],
        }
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
    return chip


def enrich_all(chips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [enrich_one(c) for c in chips]
