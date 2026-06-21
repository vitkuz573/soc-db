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
